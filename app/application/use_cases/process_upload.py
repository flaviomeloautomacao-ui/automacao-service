"""Caso de uso principal — processa upload de planilha e gera laudo PDF.

Orquestra todo o pipeline:

1. Persiste metadados do upload + armazena arquivo no storage.
2. Faz parsing da planilha em linhas de risco.
3. Valida regras determinísticas.
4. Cria rascunho (draft) no banco.
5. Gera seções narrativas via LLM.
6. Renderiza template HTML (Jinja2) + CSS.
7. Converte HTML em PDF (WeasyPrint).
8. Armazena PDF no storage.
9. Persiste metadados do relatório gerado.

Retorna dicionário com ``upload_id``, ``draft_id``, ``report_id`` e ``pdf_url``.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from app.adapters.storage.paths import (
    report_pdf_path,
    upload_original_path,
)
from app.adapters.llm.prompts import get_profile_config
from app.domain.errors import (
    DBError,
    LLMError,
    StorageError,
    TemplateError,
    ValidationError,
)
from app.domain.ports import (
    LLMPort,
    PdfRendererPort,
    ReportRepositoryPort,
    SpreadsheetParserPort,
    SpreadsheetValidatorPort,
    StoragePort,
)

import re as _re

from app.domain.services.text_utils import split_field as _split_field, append_unique as _append_unique


def _sha256(data: bytes) -> str:
    """Calcula o hash SHA-256 de um bloco de bytes.

    Args:
        data: conteúdo binário.

    Returns:
        String hexadecimal do digest.
    """
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Helpers — agrupamento de equipamentos
# ---------------------------------------------------------------------------


def group_rows_by_equipment(rows_dicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Agrupa linhas de risco por nome de equipamento.

    Cada equipamento único recebe um dict com listas de perigos, causas,
    consequências, medidas, etc. — pronto para o template Jinja2.

    Args:
        rows_dicts: Lista de dicts (``MachineRiskRow.model_dump()``).

    Returns:
        Lista de dicts, um por equipamento, na ordem de aparição.
    """
    from collections import OrderedDict

    groups: OrderedDict[str, dict[str, Any]] = OrderedDict()

    for row in rows_dicts:
        name = (row.get("equipamento") or "Equipamento N/I").strip()
        if name not in groups:
            groups[name] = {
                "nome": name,
                "descricao": "",
                "perigos": [],
                "causas": [],
                "consequencias": [],
                "severidade": "",
                "risco": "",
                "medidas_existentes": [],
                "medidas_implementar": [],
                "observacoes": [],
                "riscos_desc": [],
            }

        g = groups[name]

        # Descrição: manter a mais longa (primeira não vazia)
        desc = (row.get("descricao_equipamento") or "").strip()
        if desc and (not g["descricao"] or len(desc) > len(g["descricao"])):
            g["descricao"] = desc

        # Severidade / risco: manter primeiro valor não vazio
        sev = (row.get("categoria_severidade") or "").strip()
        if sev and not g["severidade"]:
            g["severidade"] = sev
        risco = (row.get("categoria_risco") or "").strip()
        if risco and not g["risco"]:
            g["risco"] = risco

        # Campos multivalorados — split e append
        _append_unique(g["perigos"], _split_field(row.get("perigo")))
        _append_unique(g["causas"], _split_field(row.get("causas")))
        _append_unique(g["consequencias"], _split_field(row.get("consequencias")))
        _append_unique(g["medidas_existentes"], _split_field(row.get("medidas_existentes")))
        _append_unique(g["medidas_implementar"], _split_field(row.get("medidas_implementar")))
        _append_unique(g["riscos_desc"], _split_field(row.get("riscos")))

        obs = (row.get("observacoes") or "").strip()
        if obs and obs not in g["observacoes"]:
            g["observacoes"].append(obs)

    result: list[dict[str, Any]] = []
    for idx, (_, grp) in enumerate(groups.items(), 1):
        grp["index"] = idx
        result.append(grp)
    return result


class ProcessUploadUseCase:
    """Caso de uso: recebe planilha, valida, gera laudo e devolve PDF.

    Todas as dependências são injetadas via construtor, respeitando
    os contratos definidos nas portas do domínio.

    Args:
        repository: Persistência de uploads, drafts e relatórios.
        storage: Object-storage para arquivos e PDFs.
        parser: Parser de planilhas XLSX / CSV.
        validator: Validação determinística de linhas de risco.
        llm: Cliente LLM para geração de seções narrativas.
        pdf_renderer: Renderizador HTML → PDF.
        bucket: Nome do bucket no storage.
    """

    def __init__(
        self,
        *,
        repository: ReportRepositoryPort,
        storage: StoragePort,
        parser: SpreadsheetParserPort,
        validator: SpreadsheetValidatorPort,
        llm: LLMPort,
        pdf_renderer: PdfRendererPort,
        bucket: str = "documents",
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._parser = parser
        self._validator = validator
        self._llm = llm
        self._pdf_renderer = pdf_renderer
        self._bucket = bucket

    # ------------------------------------------------------------------
    # Método público
    # ------------------------------------------------------------------

    async def execute(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str,
        profile: str | None = None,
        company_metadata: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        """Executa o pipeline completo de processamento de upload.

        Args:
            file_bytes: Conteúdo binário da planilha enviada.
            filename: Nome original do arquivo.
            content_type: MIME type do arquivo (ex.: ``application/vnd.openxmlformats-...``).
            company_metadata: Dados opcionais da empresa (razao_social, cnpj, etc.)
                que serão usados no template e no contexto LLM.

        Returns:
            Dicionário com:
                - ``upload_id``: UUID do upload persistido.
                - ``draft_id``: UUID do rascunho normalizado.
                - ``report_id``: UUID do relatório PDF gerado.
                - ``pdf_url``: URL assinada para download do PDF.

        Raises:
            ValidationError: Se a planilha for inválida.
            StorageError: Se houver falha no object-storage.
            DBError: Se houver falha de persistência.
            LLMError: Se a geração de seções via LLM falhar.
            TemplateError: Se a renderização HTML/PDF falhar.
        """
        # 1) Persiste upload + armazena arquivo cru no storage
        upload_id = await self._persist_upload(file_bytes, filename, content_type)

        # 2) Parse da planilha
        rows = self._parse_spreadsheet(file_bytes, filename)

        # 3) Validação determinística
        self._validate_rows(rows)

        # 4) Cria draft no banco
        rows_dicts = [row.model_dump(mode="json") for row in rows]
        draft_id = await self._create_draft(upload_id, rows_dicts)

        # 4.5) Agrupa equipamentos para análise individual
        grouped_equipment = group_rows_by_equipment(rows_dicts)
        logger.info(
            "Equipamentos agrupados | total_equipamentos={}",
            len(grouped_equipment),
        )

        # 5) Gera seções narrativas via LLM
        llm_sections = await self._generate_llm_sections(
            rows_dicts, company_metadata, profile=profile, grouped_equipment=grouped_equipment,
        )

        # 5.5) Normaliza seções LLM (converte texto em HTML p/ template)
        llm_sections_html = self._normalize_llm_sections(llm_sections)

        # 6 + 7) Renderiza HTML e gera PDF
        pdf_bytes = self._render_pdf(
            rows_dicts, llm_sections_html, company_metadata,
            profile=profile, grouped_equipment=grouped_equipment,
        )

        # 8 + 9) Armazena PDF e persiste metadados do relatório
        report_id, pdf_url, pdf_path = await self._store_report(
            draft_id=draft_id,
            pdf_bytes=pdf_bytes,
        )

        logger.info(
            "Pipeline concluído | upload_id={} | draft_id={} | report_id={}",
            upload_id,
            draft_id,
            report_id,
        )

        return {
            "upload_id": upload_id,
            "draft_id": draft_id,
            "report_id": report_id,
            "pdf_url": pdf_url,
            "pdf_path": pdf_path,
        }

    # ------------------------------------------------------------------
    # Etapas internas
    # ------------------------------------------------------------------

    async def _persist_upload(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str,
    ) -> str:
        """Etapa 1 — persiste metadados e armazena arquivo no storage.

        Returns:
            UUID do upload.
        """
        # Gerar upload_id antecipadamente para compor o path
        upload_id = str(uuid.uuid4())
        storage_path = upload_original_path(upload_id, filename)

        logger.info(
            "Armazenando upload | filename={} | size={} bytes",
            filename,
            len(file_bytes),
        )

        await self._storage.put_bytes(
            self._bucket,
            storage_path,
            file_bytes,
            content_type=content_type,
        )

        created_id = await self._repository.create_upload(
            filename=filename,
            content_type=content_type,
            size_bytes=len(file_bytes),
            storage_path=storage_path,
        )

        logger.info("Upload persistido | upload_id={}", created_id)
        return created_id

    def _parse_spreadsheet(
        self,
        file_bytes: bytes,
        filename: str,
    ) -> list:
        """Etapa 2 — converte bytes da planilha em linhas de risco.

        Returns:
            Lista de ``MachineRiskRow``.

        Raises:
            ValidationError: Se o formato/conteúdo for inválido.
        """
        logger.info("Parseando planilha | filename={}", filename)
        rows = self._parser.parse(file_bytes, filename)
        logger.info("Planilha parseada | total_linhas={}", len(rows))
        return rows

    def _validate_rows(self, rows: list) -> None:
        """Etapa 3 — valida regras determinísticas.

        Raises:
            ValidationError: Se alguma regra de negócio for violada.
        """
        logger.info("Validando {} linha(s) da planilha", len(rows))
        self._validator.validate(rows)
        logger.info("Validação concluída sem erros")

    async def _create_draft(
        self,
        upload_id: str,
        rows_dicts: list[dict[str, Any]],
    ) -> str:
        """Etapa 4 — cria rascunho normalizado no banco.

        Returns:
            UUID do draft.
        """
        metadata: dict[str, Any] = {
            "total_rows": len(rows_dicts),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        draft_id = await self._repository.create_draft(
            upload_id=upload_id,
            metadata=metadata,
            rows_json=rows_dicts,
        )

        logger.info("Draft criado | draft_id={} | upload_id={}", draft_id, upload_id)
        return draft_id

    async def _generate_llm_sections(
        self,
        rows_dicts: list[dict[str, Any]],
        company_metadata: dict[str, Any] | None = None,
        *,
        profile: str | None = None,
        grouped_equipment: list[dict[str, Any]] | None = None,
        model_override: str | None = None,
    ) -> dict[str, Any]:
        """Etapa 5 — gera seções narrativas via LLM.

        Args:
            model_override: Modelo específico para esta chamada (CP-01).
                Se ``None``, usa o modelo padrão do client.

        Returns:
            Dicionário com seções geradas (``introducao``, ``metodologia``,
            ``conclusao``, e opcionalmente ``materiais``).

        Raises:
            LLMError: Se a chamada ao LLM falhar.
        """
        context: dict[str, Any] = {
            "company": company_metadata or {},
            "rows": rows_dicts,
            "total_rows": len(rows_dicts),
            "profile": profile,
            "grouped_equipment": grouped_equipment or [],
        }

        logger.info(
            "Gerando seções via LLM | profile={} | model={} | linhas_de_risco={}",
            profile or "default",
            model_override or "default",
            len(rows_dicts),
        )

        # Setar contexto de tracking no LLM client
        if hasattr(self._llm, 'set_tracking_context'):
            self._llm.set_tracking_context(
                flow="upload",
                step="global_sections",
            )

        sections = await self._llm.generate_sections(
            context, model_override=model_override,
        )
        logger.info("Seções LLM geradas com sucesso")
        return sections

    @staticmethod
    def _normalize_llm_sections(sections: dict[str, Any]) -> dict[str, str]:
        """Normaliza valores retornados pelo LLM para uso no template.

        O template Jinja2 usa ``render_text()`` que converte ``\n\n``
        em parágrafos e bullets em listas.  Aqui apenas garantimos
        que todos os valores sejam strings.

        Args:
            sections: Dicionário cru retornado pelo LLM.

        Returns:
            Dicionário com todos os valores como strings.
        """
        result: dict[str, str] = {}
        for key, value in sections.items():
            if isinstance(value, list):
                # Converte listas legadas em texto com bullets
                result[key] = "\n".join(f"• {item}" for item in value)
            elif value is not None:
                result[key] = str(value)
            else:
                result[key] = ""
        return result

    def _render_pdf(
        self,
        rows_dicts: list[dict[str, Any]],
        llm_sections: dict[str, Any],
        company_metadata: dict[str, Any] | None = None,
        *,
        profile: str | None = None,
        grouped_equipment: list[dict[str, Any]] | None = None,
    ) -> bytes:
        """Etapas 6 + 7 — renderiza template HTML e converte em PDF.

        Returns:
            Bytes do PDF gerado.

        Raises:
            TemplateError: Se a renderização falhar.
        """
        profile_config = get_profile_config(profile)

        metadata: dict[str, Any] = {
            "data_geracao": datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC"),
        }
        if company_metadata:
            metadata.update(company_metadata)

        equipments = grouped_equipment or []

        logger.info(
            "Renderizando HTML + PDF | equipamentos={} | linhas={}",
            len(equipments),
            len(rows_dicts),
        )

        # Importação local para uso do método render_html + render
        from app.adapters.pdf.renderer import WeasyPdfRenderer  # noqa: PLC0415

        if isinstance(self._pdf_renderer, WeasyPdfRenderer):
            pdf_bytes = self._pdf_renderer.render_report(
                metadata=metadata,
                rows=rows_dicts,
                llm_sections=llm_sections,
                equipments=equipments,
                profile_config=profile_config,
            )
        else:
            # Fallback genérico via PdfRendererPort
            from app.adapters.pdf.renderer import (  # noqa: PLC0415
                _build_normas_por_equipamento,
                _clean_bullet_text,
                _format_paragraphs,
            )
            from jinja2 import Environment, FileSystemLoader, select_autoescape  # noqa: PLC0415
            from pathlib import Path  # noqa: PLC0415

            tpl_dir = Path(__file__).resolve().parents[2] / "adapters" / "pdf" / "templates"
            env = Environment(
                loader=FileSystemLoader(str(tpl_dir)),
                autoescape=select_autoescape(["html"]),
            )
            env.filters["format_paragraphs"] = _format_paragraphs
            env.filters["clean_bullet_text"] = _clean_bullet_text
            template = env.get_template("report.html")
            html = template.render(
                metadata=metadata,
                rows=rows_dicts,
                llm_sections=llm_sections,
                equipments=equipments,
                profile_config=profile_config,
                normas_por_equipamento=_build_normas_por_equipamento(equipments),
            )
            pdf_bytes = self._pdf_renderer.render(html)

        logger.info("PDF gerado | size={} bytes", len(pdf_bytes))
        return pdf_bytes

    async def _store_report(
        self,
        *,
        draft_id: str,
        pdf_bytes: bytes,
    ) -> tuple[str, str, str]:
        """Etapas 8 + 9 — armazena PDF e persiste metadados do relatório.

        Returns:
            Tupla ``(report_id, pdf_url, pdf_path)``.
        """
        report_id = str(uuid.uuid4())
        version = 1
        storage_path = report_pdf_path(report_id, version=version)
        checksum = _sha256(pdf_bytes)

        logger.info(
            "Armazenando PDF | report_id={} | path={} | checksum={}",
            report_id,
            storage_path,
            checksum[:16] + "…",
        )

        await self._storage.put_bytes(
            self._bucket,
            storage_path,
            pdf_bytes,
            content_type="application/pdf",
        )

        pdf_url = await self._storage.get_signed_url(
            self._bucket,
            storage_path,
        )

        created_id = await self._repository.create_generated(
            draft_id=draft_id,
            pdf_storage_path=storage_path,
            pdf_url=pdf_url,
            checksum=checksum,
            version=version,
        )

        logger.info(
            "Relatório persistido | report_id={} | draft_id={}",
            created_id,
            draft_id,
        )

        return created_id, pdf_url, storage_path
