"""Prompts LLM — Classificação de Áreas v2."""

from __future__ import annotations

from typing import Any

from app.adapters.llm.prompts import get_profile_config
from app.domain.entities.area_classification import AreaClassificationContext


def build_area_system_prompt(profile: str = "areas") -> str:
    cfg = get_profile_config(profile)
    normas_text = "\n".join(f"  - {item}" for item in cfg["normas_principais"][:6])
    return (
        "Você é um engenheiro eletricista sênior, especializado em "
        "classificação de áreas com atmosferas explosivas conforme as normas "
        "ABNT NBR IEC 60079-10-1 e ABNT NBR IEC 60079-10-2.\n\n"
        f"Normas principais:\n{normas_text}\n\n"
        "Responda apenas com JSON válido. Não recalcule zonas ou extensões. "
        "Use apenas o contexto fornecido e redija texto técnico formal."
    )


def build_area_system_prompt_retry(profile: str = "areas") -> str:
    return (
        build_area_system_prompt(profile)
        + "\nATENÇÃO: responda exclusivamente com JSON puro."
    )


def build_area_global_user_prompt(
    *,
    company_metadata: dict[str, Any] | None,
    area_contexts: list[AreaClassificationContext],
    profile: str = "areas",
) -> str:
    cfg = get_profile_config(profile)
    company = company_metadata or {}
    substancias = sorted({item for ctx in area_contexts for item in ctx.substancias if item})
    areas = [ctx.area_local for ctx in area_contexts]
    observacoes = (
        company.get("observacoes_gerais_prompt")
        or company.get("observacoes_gerais")
        or ""
    ).strip()

    observacoes_section = (
        f"\nObservações complementares do cliente:\n{observacoes}\n"
        if observacoes
        else ""
    )

    # Agrega trechos normativos únicos recuperados via RAG (top N)
    seen: set[str] = set()
    aggregated_norms: list[str] = []
    for ctx in area_contexts:
        for excerpt in ctx.normative_context:
            key = excerpt.strip()
            if not key or key in seen:
                continue
            seen.add(key)
            aggregated_norms.append(excerpt)
            if len(aggregated_norms) >= 8:
                break
        if len(aggregated_norms) >= 8:
            break

    normative_section = (
        "\nContexto normativo recuperado (use como base — não invente referências):\n"
        + "\n".join(f"• {item}" for item in aggregated_norms)
        + "\n"
        if aggregated_norms
        else ""
    )

    return f"""Gere as seções globais de um relatório de Classificação de Áreas.

Cliente: {company.get("razao_social") or "—"}
Unidade: {company.get("site") or "—"}
Local vistoriado: {company.get("local_vistoriado") or "—"}
Data da avaliação: {company.get("data_avaliacao") or "—"}
Áreas avaliadas: {", ".join(areas) or "—"}
Substâncias avaliadas: {", ".join(substancias) or "—"}
Total de áreas: {len(area_contexts)}
Total de fontes de liberação: {sum(len(ctx.fontes_liberacao) for ctx in area_contexts)}
Normas de referência:
{chr(10).join(f"• {item}" for item in cfg["normas_principais"])}
{observacoes_section}{normative_section}
Responda com este JSON:
{{
  "introducao": "...",
  "escopo": "...",
  "consideracoes_gerais": "...",
  "metodologia": "...",
  "recomendacoes": "...",
  "conclusao": "..."
}}"""


def build_area_per_area_user_prompt(
    ctx: AreaClassificationContext,
    *,
    profile: str = "areas",
) -> str:
    cfg = get_profile_config(profile)
    fontes_texto = "\n".join(
        (
            f"  {index}. Fonte: {fonte.descricao} | Substância: {fonte.substancia} | "
            f"Tag: {fonte.tag_referencia or '—'} | Zona: {fonte.zona} | Extensão: {fonte.extensao} | "
            f"Ventilação: {fonte.ventilacao_tipo} / {fonte.ventilacao_grau} / {fonte.ventilacao_disponibilidade} | "
            f"Grupo/Classe: {fonte.grupo or '—'} / {fonte.classe_temperatura or '—'} | EPL: {fonte.epl or '—'} | "
            f"Observações: {fonte.observacoes or '—'}"
        )
        for index, fonte in enumerate(ctx.fontes_liberacao, start=1)
    )

    normative_section = (
        "\nContexto normativo recuperado (use como base — não invente referências):\n"
        + "\n".join(f"• {item}" for item in ctx.normative_context[:6])
        + "\n"
        if ctx.normative_context
        else ""
    )

    return f"""Gere a análise técnica da área/local abaixo.

Área/local: {ctx.area_local}
Tags de referência: {", ".join(ctx.tag_referencias) or "—"}
Substâncias: {", ".join(ctx.substancias) or "—"}
Grupo predominante: {ctx.grupo or "—"}
Classe de temperatura: {ctx.classe_temperatura or "—"}
EPL predominante: {ctx.epl or "—"}
Notas operacionais: {ctx.operational_notes or "—"}
Premissas de ventilação: {ctx.ventilation_premises or "—"}

Fontes de liberação:
{fontes_texto or "  —"}

Documentos de referência:
{chr(10).join(f"• {item['title']} ({item.get('document_code') or 'sem código'})" for item in ctx.reference_documents) or "• —"}

Normas de referência:
{chr(10).join(f"• {item}" for item in cfg["normas_principais"][:5])}
{normative_section}
Responda com este JSON:
{{
  "justificativa_zona": "...",
  "analise_ventilacao": "...",
  "recomendacoes_especificas": [
    {{
      "numero": 1,
      "texto": "...",
      "norma_referencia": "..."
    }}
  ]
}}"""


__all__ = [
    "build_area_system_prompt",
    "build_area_system_prompt_retry",
    "build_area_global_user_prompt",
    "build_area_per_area_user_prompt",
]
