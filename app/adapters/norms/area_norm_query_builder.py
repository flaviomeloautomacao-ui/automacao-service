"""Construtor de queries semânticas para retrieval de normas — Classificação de Áreas.

Monta uma query textual rica a partir do contexto de uma área
(``AreaClassificationContext``), combinando substâncias, fontes de
liberação, condições de ventilação, zonas, grupo IEC e classe de
temperatura com termos técnicos do domínio para maximizar a
relevância da busca vetorial na tabela ``konis_db_ClassificacaoDeAreas``.

Uso::

    from app.adapters.norms.area_norm_query_builder import build_area_norm_query

    query = build_area_norm_query(area_ctx, profile="areas")
"""

from __future__ import annotations

from loguru import logger

from app.domain.entities.area_classification import AreaClassificationContext


# ---------------------------------------------------------------------------
# Termos técnicos do domínio
# ---------------------------------------------------------------------------

# Termos fundamentais de classificação de áreas — SEMPRE injetados.
_CORE_DOMAIN_TERMS: list[str] = [
    "classificação de áreas",
    "atmosfera explosiva",
    "fonte de liberação",
    "grau de ventilação",
    "zona perigosa",
    "IEC 60079-10-1",
    "IEC 60079-10-2",
    "seleção de equipamentos Ex",
]

# Termos contextuais — injetados apenas se houver sinal nos dados.
_CONTEXTUAL_DOMAIN_TERMS: list[str] = [
    "ventilação natural",
    "ventilação artificial",
    "diluição",
    "extensão da zona",
    "ponto de fulgor",
    "temperatura de auto-ignição",
    "EPL",
    "Ex d",
    "Ex e",
    "Ex i",
    "Ex p",
    "aterramento",
    "manutenção Ex",
    "inspeção periódica IEC 60079-17",
]

# ---------------------------------------------------------------------------
# Limites
# ---------------------------------------------------------------------------

_MAX_QUERY_CHARS = 2000
_MAX_LIST_ITEMS_IN_QUERY = 8


# ---------------------------------------------------------------------------
# Função pública
# ---------------------------------------------------------------------------


def build_area_norm_query(
    area_context: AreaClassificationContext,
    *,
    profile: str | None = None,
) -> str:
    """Monta query semântica rica para retrieval de normas de classificação de áreas.

    Args:
        area_context: Contexto consolidado da área.
        profile: Perfil de análise (atualmente apenas ``"areas"``).

    Returns:
        Texto de query pronto para geração de embedding.
    """
    ctx = area_context
    parts: list[str] = []

    # ── Identificação da área ──────────────────────────────────
    parts.append(f"Área: {ctx.area_local}")

    if ctx.tag_referencias:
        tags = list(ctx.tag_referencias)[:_MAX_LIST_ITEMS_IN_QUERY]
        parts.append(f"Tags: {', '.join(tags)}")

    # ── Substâncias presentes ──────────────────────────────────
    substancias = list(ctx.substancias)[:_MAX_LIST_ITEMS_IN_QUERY]
    if substancias:
        parts.append(f"Substâncias: {', '.join(substancias)}")

    # ── Grupo / Classe Temperatura / EPL ───────────────────────
    if ctx.grupo:
        parts.append(f"Grupo IEC: {ctx.grupo}")
    if ctx.classe_temperatura:
        parts.append(f"Classe de temperatura: {ctx.classe_temperatura}")
    if ctx.epl:
        parts.append(f"EPL: {ctx.epl}")

    # ── Fontes de liberação ────────────────────────────────────
    fontes = ctx.fontes_liberacao[:_MAX_LIST_ITEMS_IN_QUERY]
    if fontes:
        descricoes = sorted({f.descricao for f in fontes if f.descricao})
        graus = sorted({f.grau for f in fontes if f.grau})
        zonas = sorted({f.zona for f in fontes if f.zona})
        ventilacoes_tipo = sorted({f.ventilacao_tipo for f in fontes if f.ventilacao_tipo})
        ventilacoes_grau = sorted({f.ventilacao_grau for f in fontes if f.ventilacao_grau})
        ventilacoes_disp = sorted(
            {f.ventilacao_disponibilidade for f in fontes if f.ventilacao_disponibilidade}
        )
        extensoes = sorted({f.extensao for f in fontes if f.extensao})

        if descricoes:
            parts.append(f"Fontes de liberação: {', '.join(descricoes)}")
        if graus:
            parts.append(f"Grau de liberação: {', '.join(graus)}")
        if zonas:
            parts.append(f"Zonas resultantes: {', '.join(zonas)}")
        if ventilacoes_tipo:
            parts.append(f"Tipo de ventilação: {', '.join(ventilacoes_tipo)}")
        if ventilacoes_grau:
            parts.append(f"Grau de ventilação: {', '.join(ventilacoes_grau)}")
        if ventilacoes_disp:
            parts.append(f"Disponibilidade da ventilação: {', '.join(ventilacoes_disp)}")
        if extensoes:
            parts.append(f"Extensão da zona: {', '.join(extensoes)}")

    # ── Premissas operacionais ─────────────────────────────────
    if ctx.operational_notes:
        parts.append(f"Notas operacionais: {ctx.operational_notes}")
    if ctx.ventilation_premises:
        parts.append(f"Premissas de ventilação: {ctx.ventilation_premises}")

    # ── Termos do domínio ──────────────────────────────────────
    parts.append("Contexto normativo: " + ", ".join(_CORE_DOMAIN_TERMS))

    base_text = " ".join(parts).lower()
    contextual_hits = [term for term in _CONTEXTUAL_DOMAIN_TERMS if term.lower() in base_text]
    if contextual_hits:
        parts.append("Termos relacionados: " + ", ".join(contextual_hits))

    query = " | ".join(parts)
    if len(query) > _MAX_QUERY_CHARS:
        query = query[:_MAX_QUERY_CHARS]
        logger.debug(
            "Area RAG query truncada a {} chars | area='{}'",
            _MAX_QUERY_CHARS,
            ctx.area_local,
        )

    return query


__all__ = ["build_area_norm_query"]
