"""Adaptador de renderização HTML → PDF usando WeasyPrint.

Implementa ``PdfRendererPort`` definido em ``app.domain.ports``.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

_MESES_PT = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
}
from weasyprint import HTML

from app.domain.errors import TemplateError

# Diretório onde ficam os templates Jinja2 (.html, .css)
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

# Quebra de parágrafo: linha em branco OU início de item enumerado ("1-", "2 -", "3)", "4.")
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n|\n(?=\s*\d+\s*[-–.\)])")
_LIST_MARKER_RE = re.compile(r"^\s*(?:[-•]\s*|\d+\s*[-–.)]\s*)+")


def _format_paragraphs(value: Any) -> Markup:
    """Converte texto com itens enumerados/quebras em parágrafos HTML.

    Regras:
        - Escapa o conteúdo (segurança contra HTML/injeção).
        - Itens enumerados (``1-``, ``2 -``, ``3)``, ``4.``) separados por
          quebra de linha simples são promovidos a parágrafos independentes.
        - Parágrafos separados por ``\\n\\n`` também viram parágrafos.

    Args:
        value: Texto bruto (tipicamente vindo da LLM).

    Returns:
        ``Markup`` seguro com cada bloco envolvido em ``<p>``.
    """
    if value is None:
        return Markup("")
    text = str(value).strip()
    if not text:
        return Markup("")
    blocks = _PARAGRAPH_SPLIT_RE.split(text)
    parts = [escape(b.strip()) for b in blocks if b.strip()]
    if not parts:
        return Markup("")
    return Markup("".join(f"<p>{p}</p>" for p in parts))


def _clean_bullet_text(value: Any) -> str:
    """Remove numeração/marcadores duplicados no início de itens de lista."""
    if value is None:
        return ""
    return _LIST_MARKER_RE.sub("", str(value)).strip()


def _build_normas_por_equipamento(
    equipments: list[dict[str, Any]],
) -> dict[str, str]:
    """Agrega as normas de referência das recomendações por equipamento.

    Usado pela tabela do Apêndice A para exibir a coluna "Base Normativa",
    já que as normas vêm das recomendações (por equipamento) e a tabela
    itera por linha de perigo.

    Args:
        equipments: Lista de equipamentos com ``recomendacoes_tecnicas``.

    Returns:
        Mapa ``{nome_equipamento: "Norma A; Norma B"}`` (normas únicas,
        preservando a ordem de aparição).
    """
    resultado: dict[str, str] = {}
    for eq in equipments:
        nome = (eq.get("nome") or "").strip()
        if not nome:
            continue
        normas: list[str] = []
        for rec in eq.get("recomendacoes_tecnicas") or []:
            norma = (rec.get("norma_referencia") or "").strip()
            if norma and norma not in normas:
                normas.append(norma)
        if normas:
            resultado[nome] = "; ".join(normas)
    return resultado




class WeasyPdfRenderer:
    """Renderiza HTML (Jinja2) em PDF via WeasyPrint.

    Implementa ``PdfRendererPort``.

    Attributes:
        _env: Ambiente Jinja2 configurado para carregar templates do disco.
    """

    def __init__(self, templates_dir: Path | None = None) -> None:
        """Inicializa o renderer.

        Args:
            templates_dir: Diretório com os templates Jinja2.
                           Se ``None``, usa o diretório padrão ``templates/``.
        """
        tpl_dir = templates_dir or _TEMPLATES_DIR
        self._env = Environment(
            loader=FileSystemLoader(str(tpl_dir)),
            autoescape=select_autoescape(["html"]),
        )
        self._env.filters["format_paragraphs"] = _format_paragraphs
        self._env.filters["clean_bullet_text"] = _clean_bullet_text
        self._base_url = str(tpl_dir)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def render_html(
        self,
        *,
        metadata: dict[str, Any],
        rows: list[dict[str, Any]],
        llm_sections: dict[str, str],
        equipments: list[dict[str, Any]] | None = None,
        profile_config: dict[str, Any] | None = None,
        template_name: str = "report.html",
    ) -> str:
        """Renderiza o template Jinja2 com os dados fornecidos.

        Args:
            metadata: Dados da empresa/unidade/responsável.
            rows: Lista de dicts representando ``MachineRiskRow``.
            llm_sections: Seções geradas pela LLM.
            equipments: Lista de equipamentos agrupados (para análise individual).
            profile_config: Configuração do perfil (título, normas, etc.).
            template_name: Nome do arquivo de template.

        Returns:
            String HTML completa.

        Raises:
            TemplateError: Se a renderização falhar.
        """
        try:
            template = self._env.get_template(template_name)
            now = datetime.now()
            mes_ano = f"{_MESES_PT[now.month]} de {now.year}"
            normas_por_equipamento = _build_normas_por_equipamento(equipments or [])
            return template.render(
                metadata=metadata,
                rows=rows,
                llm_sections=llm_sections,
                equipments=equipments or [],
                profile_config=profile_config or {},
                mes_ano=mes_ano,
                normas_por_equipamento=normas_por_equipamento,
            )
        except Exception as exc:
            raise TemplateError(
                f"Falha ao renderizar template '{template_name}': {exc}",
                detail=str(exc),
            ) from exc

    # ------------------------------------------------------------------
    # PdfRendererPort
    # ------------------------------------------------------------------

    def render(self, html: str, assets: dict[str, bytes] | None = None) -> bytes:
        """Converte HTML em bytes de PDF via WeasyPrint.

        Args:
            html: Conteúdo HTML completo a ser convertido.
            assets: Mapa opcional ``{nome_arquivo: conteúdo}`` de imagens /
                    fontes referenciadas no HTML (não utilizado diretamente
                    nesta implementação — assets são resolvidos por ``base_url``).

        Returns:
            Bytes do documento PDF gerado.

        Raises:
            TemplateError: Se a conversão falhar.
        """
        try:
            html_doc = HTML(string=html, base_url=self._base_url)
            return html_doc.write_pdf()
        except Exception as exc:
            raise TemplateError(
                f"Falha ao gerar PDF: {exc}",
                detail=str(exc),
            ) from exc

    # ------------------------------------------------------------------
    # Convenience: render template → PDF em um passo
    # ------------------------------------------------------------------

    def render_report(
        self,
        *,
        metadata: dict[str, Any],
        rows: list[dict[str, Any]],
        llm_sections: dict[str, str],
        equipments: list[dict[str, Any]] | None = None,
        profile_config: dict[str, Any] | None = None,
        template_name: str = "report.html",
        assets: dict[str, bytes] | None = None,
    ) -> bytes:
        """Renderiza template e converte diretamente em PDF.

        Combina ``render_html`` + ``render`` em uma única chamada.

        Args:
            metadata: Dados da empresa/unidade/responsável.
            rows: Lista de dicts representando ``MachineRiskRow``.
            llm_sections: Seções geradas pela LLM.
            equipments: Lista de equipamentos agrupados.
            profile_config: Configuração do perfil.
            template_name: Nome do template Jinja2.
            assets: Assets opcionais.

        Returns:
            Bytes do PDF gerado.
        """
        html = self.render_html(
            metadata=metadata,
            rows=rows,
            llm_sections=llm_sections,
            equipments=equipments,
            profile_config=profile_config,
            template_name=template_name,
        )
        return self.render(html, assets=assets)
