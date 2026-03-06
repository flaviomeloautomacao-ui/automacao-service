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


def _sha256(data: bytes) -> str:
    """Calcula o hash SHA-256 de um bloco de bytes.

    Args:
        data: conteúdo binário.

    Returns:
        String hexadecimal do digest.
    """
    return hashlib.sha256(data).hexdigest()


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

        # 5) Gera seções narrativas via LLM
        llm_sections = await self._generate_llm_sections(rows_dicts, company_metadata)

        # 5.5) Normaliza seções LLM (converte listas em HTML p/ template)
        llm_sections_html = self._normalize_llm_sections(llm_sections)

        # 6 + 7) Renderiza HTML e gera PDF
        pdf_bytes = self._render_pdf(rows_dicts, llm_sections_html, company_metadata)

        # 8 + 9) Armazena PDF e persiste metadados do relatório
        report_id, pdf_url = await self._store_report(
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
    ) -> dict[str, Any]:
        """Etapa 5 — gera seções narrativas via LLM.

        Returns:
            Dicionário com seções geradas (``resumo``, ``recomendacoes``, etc.).

        Raises:
            LLMError: Se a chamada ao LLM falhar.
        """
        context: dict[str, Any] = {
            "company": company_metadata or {},
            "rows": rows_dicts,
            "total_rows": len(rows_dicts),
        }

        logger.info("Gerando seções via LLM | linhas_de_risco={}", len(rows_dicts))
        sections = await self._llm.generate_sections(context)
        logger.info("Seções LLM geradas com sucesso")
        return sections

    @staticmethod
    def _normalize_llm_sections(sections: dict[str, Any]) -> dict[str, str]:
        """Converte valores de lista retornados pelo LLM em strings HTML.

        O template Jinja2 usa ``{{ section | safe }}`` e espera strings HTML.
        O LLM retorna listas para ``recomendacoes`` e ``justificativas``,
        que precisam ser convertidas em ``<ul>`` HTML.

        Args:
            sections: Dicionário cru retornado pelo LLM.

        Returns:
            Dicionário com todos os valores como strings HTML.
        """
        result: dict[str, str] = {}
        for key, value in sections.items():
            if isinstance(value, list):
                items_html = "".join(f"<li>{item}</li>" for item in value)
                result[key] = f"<ul>{items_html}</ul>"
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
    ) -> bytes:
        """Etapas 6 + 7 — renderiza template HTML e converte em PDF.

        Returns:
            Bytes do PDF gerado.

        Raises:
            TemplateError: Se a renderização falhar.
        """
        metadata: dict[str, Any] = {
            "data_geracao": datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC"),
        }
        if company_metadata:
            metadata.update(company_metadata)

        logger.info("Renderizando HTML + PDF | total_linhas={}", len(rows_dicts))

        # Importação local para uso do método render_html + render
        from app.adapters.pdf.renderer import WeasyPdfRenderer  # noqa: PLC0415

        if isinstance(self._pdf_renderer, WeasyPdfRenderer):
            # Usa o método de conveniência que combina render_html + render
            pdf_bytes = self._pdf_renderer.render_report(
                metadata=metadata,
                rows=rows_dicts,
                llm_sections=llm_sections,
            )
        else:
            # Fallback genérico via PdfRendererPort
            from jinja2 import Environment, FileSystemLoader, select_autoescape  # noqa: PLC0415
            from pathlib import Path  # noqa: PLC0415

            tpl_dir = Path(__file__).resolve().parents[2] / "adapters" / "pdf" / "templates"
            env = Environment(
                loader=FileSystemLoader(str(tpl_dir)),
                autoescape=select_autoescape(["html"]),
            )
            template = env.get_template("report.html")
            html = template.render(
                metadata=metadata,
                rows=rows_dicts,
                llm_sections=llm_sections,
            )
            pdf_bytes = self._pdf_renderer.render(html)

        logger.info("PDF gerado | size={} bytes", len(pdf_bytes))
        return pdf_bytes

    async def _store_report(
        self,
        *,
        draft_id: str,
        pdf_bytes: bytes,
    ) -> tuple[str, str]:
        """Etapas 8 + 9 — armazena PDF e persiste metadados do relatório.

        Returns:
            Tupla ``(report_id, pdf_url)``.
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

        return created_id, pdf_url
