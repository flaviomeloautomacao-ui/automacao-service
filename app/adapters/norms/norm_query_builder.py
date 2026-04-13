"""Construtor de queries semânticas para retrieval de normas ABNT.

Monta uma query textual rica a partir do contexto do equipamento,
combinando nome, operação, perigos, causas, consequências e termos
técnicos do domínio para maximizar a relevância da busca vetorial.

Uso::

    from app.adapters.norms.norm_query_builder import build_equipment_norm_query
    from app.domain.entities import EquipmentContext

    query = build_equipment_norm_query(ctx)
"""

from __future__ import annotations

from loguru import logger

from app.domain.entities import EquipmentContext


# ---------------------------------------------------------------------------
# Termos técnicos do domínio — enriquecem a query semântica
# ---------------------------------------------------------------------------

# Termos fundamentais de DHA — SEMPRE injetados na query independente
# dos dados da planilha, pois são transversais a qualquer equipamento DHA.
_CORE_DOMAIN_TERMS: list[str] = [
    "classificação de área",
    "atmosfera explosiva",
    "fonte de ignição",
    "alívio de explosão",
    "detecção",
    "aterramento",
    "equipamentos Ex",
    "prevenção de deflagração",
]

# Termos condicionais — injetados somente se já aparecem no contexto
# do equipamento (reforço de sinal, sem adição de ruído).
_CONTEXTUAL_DOMAIN_TERMS: list[str] = [
    "poeira combustível",
    "ignição",
    "explosão",
    "deflagração",
    "ventilação",
    "exaustão",
    "segregação",
    "inspeção",
    "manutenção",
    "proteção contra incêndio",
    "integridade estrutural",
    "proteção elétrica",
]

# ---------------------------------------------------------------------------
# Tamanhos máximos de query (para evitar ruído excessivo)
# ---------------------------------------------------------------------------

_MAX_QUERY_CHARS = 2000
_MAX_LIST_ITEMS_IN_QUERY = 8


# ---------------------------------------------------------------------------
# Função pública
# ---------------------------------------------------------------------------


def build_equipment_norm_query(
    equipment_context: EquipmentContext,
    *,
    profile: str | None = None,
) -> str:
    """Monta query semântica rica para retrieval de normas ABNT.

    A query combina dados estruturados do equipamento com termos
    técnicos do domínio para maximizar a relevância da busca vetorial.
    Campos vazios são omitidos automaticamente.

    Args:
        equipment_context: Contexto completo do equipamento.
        profile: Perfil de análise (``"dust"``, ``"gas"``, ``"vapors"``).
            Usado para adicionar termos específicos do perfil.

    Returns:
        Texto de query pronto para geração de embedding.
    """
    ctx = equipment_context
    parts: list[str] = []

    # ── Identificação do equipamento ──────────────────────────────
    parts.append(f"Equipamento: {ctx.equipment_name}")

    if ctx.descricao_da_operacao and ctx.descricao_da_operacao != "Não informado":
        parts.append(f"Operação: {ctx.descricao_da_operacao}")

    # ── Perigos identificados ─────────────────────────────────────
    perigos = list(ctx.identificacao_dos_perigos)[:_MAX_LIST_ITEMS_IN_QUERY]
    if perigos:
        parts.append(f"Perigos: {', '.join(perigos)}")

    # ── Causas possíveis ──────────────────────────────────────────
    causas = list(ctx.causas_possiveis)[:_MAX_LIST_ITEMS_IN_QUERY]
    if causas:
        parts.append(f"Causas: {', '.join(causas)}")

    # ── Consequências potenciais ──────────────────────────────────
    consequencias = list(ctx.consequencias_potenciais)[:_MAX_LIST_ITEMS_IN_QUERY]
    if consequencias:
        parts.append(f"Consequências: {', '.join(consequencias)}")

    # ── Medidas existentes (opcional, para contextualizar) ────────
    medidas = list(ctx.medidas_preventivas_existentes)[:_MAX_LIST_ITEMS_IN_QUERY]
    if medidas:
        parts.append(f"Medidas existentes: {', '.join(medidas)}")

    # ── Classificação do risco ────────────────────────────────────
    risco = ctx.classificacao_do_risco
    parts.append(
        f"Classificação: severidade {risco.categoria_severidade}, "
        f"risco {risco.categoria_risco}"
    )

    # ── Termos técnicos relevantes do domínio ─────────────────────
    contexto_lower = " ".join(parts).lower()

    # 1. Termos core — sempre presentes (fundamentais para DHA)
    termos_relevantes: list[str] = list(_CORE_DOMAIN_TERMS)

    # 2. Termos contextuais — só se já aparecem nos dados do equipamento
    for t in _CONTEXTUAL_DOMAIN_TERMS:
        if t.lower() in contexto_lower and t not in termos_relevantes:
            termos_relevantes.append(t)

    # 3. Termos do perfil — gap-filling (adicionados se ausentes)
    profile_terms = _get_profile_terms(profile)
    for pt in profile_terms:
        if pt.lower() not in contexto_lower and pt not in termos_relevantes:
            termos_relevantes.append(pt)

    if termos_relevantes:
        parts.append(
            f"Termos técnicos: {', '.join(termos_relevantes[:10])}"
        )

    # ── Objetivo da busca ─────────────────────────────────────────
    parts.append(
        "Objetivo: recuperar requisitos normativos ABNT relacionados a "
        "prevenção, proteção, classificação de áreas, inspeção, "
        "integridade, controle de ignição e medidas técnicas de segurança "
        "aplicáveis a este equipamento e seus cenários de risco."
    )

    # ── Assembly e truncamento ────────────────────────────────────
    query = "\n".join(parts)

    if len(query) > _MAX_QUERY_CHARS:
        query = query[:_MAX_QUERY_CHARS - 1] + "…"
        logger.debug(
            "Query normativa truncada para {} chars | equip={}",
            _MAX_QUERY_CHARS,
            ctx.equipment_name,
        )

    logger.debug(
        "Query normativa construída | equip={} | chars={}",
        ctx.equipment_name,
        len(query),
    )

    return query


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_profile_terms(profile: str | None) -> list[str]:
    """Retorna termos técnicos específicos do perfil de análise.

    Args:
        profile: ``"dust"``, ``"gas"`` ou ``"vapors"``.

    Returns:
        Lista de termos técnicos do domínio.
    """
    if profile == "gas":
        return [
            "gases inflamáveis",
            "limite de explosividade",
            "zona classificada",
            "detecção de gás",
            "ventilação forçada",
        ]
    elif profile == "vapors":
        return [
            "vapores inflamáveis",
            "ponto de fulgor",
            "líquidos inflamáveis",
            "ventilação local",
            "contenção de derramamento",
        ]
    else:  # dust (default)
        return [
            "poeira combustível",
            "nuvem de poeira",
            "camada de poeira",
            "explosão de pó",
            "sistema de exaustão",
        ]
