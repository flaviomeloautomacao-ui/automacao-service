"""Serviço de domínio — constrói o payload LLM para um único equipamento.

Transforma um ``EquipmentContext`` (dados determinísticos já agrupados)
em um ``EquipmentLLMInput`` pronto para ser serializado e enviado ao LLM.

Contrato de referência: ``docs/equipment_llm_contract.md``, §2 & §5.1.

──────────────────────────────────────────────────────────────────────
 RESPONSABILIDADES
──────────────────────────────────────────────────────────────────────

 1. Mapear campos de ``EquipmentContext`` → ``EquipmentLLMInput``.
 2. Injetar ``normas_aplicaveis`` vindas do profile config (externo).
 3. Aplicar **todas** as validações de input (IV-01 … IV-09).
 4. Aplicar limites de tamanho (§5.1): truncar strings longas,
    limitar arrays a 15 itens, total JSON ≤ 8 000 chars.
 5. Filtrar strings vazias ou ruidosas.
 6. Retornar ``None`` quando o equipamento é inválido (log + skip).
 7. Aceitar e repassar trechos opcionais de contexto externo
    (``normative_context``, ``literature_context``) para o
    ``EquipmentLLMInput`` — futuramente populados via RAG/retrieval.

 **NÃO** faz: chamadas de rede, acesso a banco, geração de texto.
──────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from app.domain.entities import (
    EquipmentContext,
    EquipmentLLMInput,
    LiteratureExcerpt,
    NormativeExcerpt,
    ResidualRiskClassification,
    RiskClassification,
)

# ---------------------------------------------------------------------------
# Constantes — limites do contrato (§5.1)
# ---------------------------------------------------------------------------

_MAX_NAME_LEN = 200
_MAX_DESC_LEN = 500
_MAX_ITEM_LEN = 300
_MAX_ARRAY_ITEMS = 15
_MAX_TOTAL_JSON_CHARS = 8_000

# Valores válidos de severidade/risco (IV-05 / IV-06)
_VALID_SEVERIDADES: set[str] = {
    "Baixa",
    "Baixo",
    "Média",
    "Médio",
    "Média para Alta",
    "Alta",
    "Alto",
    "Muito Alta",
    "Muito Alto",
}

_VALID_RISCOS: set[str] = {
    "Baixo",
    "Baixa",
    "Médio",
    "Média",
    "Alto",
    "Alta",
    "Muito Alto",
    "Muito Alta",
}

# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------


def _truncate(text: str, max_len: int) -> str:
    """Trunca ``text`` a ``max_len`` caracteres, adicionando '…' se cortado."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _clean_list(items: list[str], *, max_items: int, max_item_len: int) -> list[str]:
    """Filtra, trunca e limita uma lista de strings.

    - Remove strings vazias após trim.
    - Trunca itens individuais a ``max_item_len``.
    - Mantém no máximo ``max_items`` itens.
    - Preserva a ordem original.
    """
    cleaned: list[str] = []
    for item in items:
        stripped = item.strip()
        if not stripped:
            continue
        cleaned.append(_truncate(stripped, max_item_len))
        if len(cleaned) >= max_items:
            break
    return cleaned


def _normalize_severity(value: str) -> str | None:
    """Retorna a severidade com capitalização canônica, ou None se inválida."""
    lookup = value.strip().lower()
    for canonical in _VALID_SEVERIDADES:
        if canonical.lower() == lookup:
            return canonical
    return None


def _normalize_risk(value: str) -> str | None:
    """Retorna o risco com capitalização canônica, ou None se inválido."""
    lookup = value.strip().lower()
    for canonical in _VALID_RISCOS:
        if canonical.lower() == lookup:
            return canonical
    return None


def _estimate_json_size(payload: dict[str, Any]) -> int:
    """Estimativa rápida do tamanho JSON serializado."""
    return len(json.dumps(payload, ensure_ascii=False))


def _shrink_to_budget(payload: dict[str, Any], budget: int) -> dict[str, Any]:
    """Trunca iterativamente os arrays mais longos até caber no budget.

    Estratégia: remove o último item do array mais longo, um de cada vez.
    Se mesmo assim exceder, trunca os itens mais longos com '[truncado]'.
    """
    # Campos-alvo para shrink (em ordem de prioridade de corte)
    _SHRINKABLE_FIELDS = [
        "medidas_preventivas_existentes",
        "medidas_a_implementar",
        "consequencias_potenciais",
        "causas_possiveis",
        "identificacao_dos_perigos",
    ]

    # Fase 1: remover itens do final dos arrays shrinkable
    for _ in range(50):  # safety limit
        size = _estimate_json_size(payload)
        if size <= budget:
            return payload

        # Encontra o array shrinkable mais longo
        longest_field = None
        longest_len = 0
        for field in _SHRINKABLE_FIELDS:
            arr = payload.get(field, [])
            if len(arr) > longest_len:
                longest_len = len(arr)
                longest_field = field

        if longest_field is None or longest_len <= 1:
            break

        payload[longest_field] = payload[longest_field][:-1]

    # Fase 2: truncar texto dos itens se ainda excede
    for _ in range(20):
        size = _estimate_json_size(payload)
        if size <= budget:
            return payload

        for field in _SHRINKABLE_FIELDS:
            arr = payload.get(field, [])
            for i, item in enumerate(arr):
                if len(item) > 100:
                    arr[i] = item[:97] + "…"

    return payload


# ---------------------------------------------------------------------------
# Função pública
# ---------------------------------------------------------------------------


def build_equipment_prompt_context(
    equipment_context: EquipmentContext,
    normas_aplicaveis: list[str],
    *,
    normative_context: list[NormativeExcerpt] | None = None,
    literature_context: list[LiteratureExcerpt] | None = None,
) -> EquipmentLLMInput | None:
    """Transforma um ``EquipmentContext`` no payload LLM validado.

    Aplica todas as validações de input (IV-01 … IV-09) e limites de
    tamanho (§5.1) do contrato ``equipment_llm_contract.md``.

    Args:
        equipment_context: Contexto já agrupado de um equipamento
            (produzido por ``build_equipment_contexts``).
        normas_aplicaveis: Lista de normas do profile config
            (e.g. ``get_profile_config(profile)["normas_principais"]``).
        normative_context: Trechos normativos recuperados por RAG/retrieval.
            Opcional — quando fornecido, os trechos são anexados ao
            ``EquipmentLLMInput`` e aparecem no prompt do LLM.
            Não implementar retrieval ainda; apenas passar adiante.
        literature_context: Trechos de literatura técnica recuperados.
            Mesmo comportamento de ``normative_context``.

    Returns:
        ``EquipmentLLMInput`` pronto para serialização, ou ``None``
        se o equipamento não atende os critérios mínimos (logado como
        warning).

    Example::

        from app.adapters.llm.prompts import get_profile_config

        cfg = get_profile_config("dust")
        ctx = equipment_contexts[0]
        llm_input = build_equipment_prompt_context(
            ctx, cfg["normas_principais"]
        )
        if llm_input:
            payload = llm_input.model_dump(mode="json")
    """
    eq = equipment_context
    eq_name = eq.equipment_name

    # ── IV-01: equipment_name não-vazio ───────────────────────────
    name = eq_name.strip()
    if not name:
        logger.warning("IV-01 | equipment_name vazio — equipamento ignorado")
        return None

    # ── IV-07: normas_aplicaveis ≥ 1 ─────────────────────────────
    normas = _clean_list(
        normas_aplicaveis,
        max_items=_MAX_ARRAY_ITEMS,
        max_item_len=_MAX_ITEM_LEN,
    )
    if not normas:
        logger.warning(
            "IV-07 | normas_aplicaveis vazio para '{}' — equipamento ignorado",
            name,
        )
        return None

    # ── IV-02: identificacao_dos_perigos ≥ 1 ─────────────────────
    perigos = _clean_list(
        list(eq.identificacao_dos_perigos),
        max_items=_MAX_ARRAY_ITEMS,
        max_item_len=_MAX_ITEM_LEN,
    )
    if not perigos:
        logger.warning(
            "IV-02 | identificacao_dos_perigos vazio para '{}' — equipamento ignorado",
            name,
        )
        return None

    # ── IV-03: causas_possiveis ≥ 1 ──────────────────────────────
    causas = _clean_list(
        list(eq.causas_possiveis),
        max_items=_MAX_ARRAY_ITEMS,
        max_item_len=_MAX_ITEM_LEN,
    )
    if not causas:
        logger.warning(
            "IV-03 | causas_possiveis vazio para '{}' — equipamento ignorado",
            name,
        )
        return None

    # ── IV-04: consequencias_potenciais ≥ 1 ──────────────────────
    consequencias = _clean_list(
        list(eq.consequencias_potenciais),
        max_items=_MAX_ARRAY_ITEMS,
        max_item_len=_MAX_ITEM_LEN,
    )
    if not consequencias:
        logger.warning(
            "IV-04 | consequencias_potenciais vazio para '{}' — equipamento ignorado",
            name,
        )
        return None

    # ── IV-05: categoria_severidade válida ────────────────────────
    sev_normalized = _normalize_severity(
        eq.classificacao_do_risco.categoria_severidade
    )
    if sev_normalized is None:
        logger.warning(
            "IV-05 | categoria_severidade inválida '{}' para '{}' — equipamento ignorado",
            eq.classificacao_do_risco.categoria_severidade,
            name,
        )
        return None

    # ── IV-06: categoria_probabilidade válido ─────────────────────
    risco_normalized = _normalize_risk(
        eq.classificacao_do_risco.categoria_probabilidade
    )
    if risco_normalized is None:
        logger.warning(
            "IV-06 | categoria_probabilidade inválido '{}' para '{}' — equipamento ignorado",
            eq.classificacao_do_risco.categoria_probabilidade,
            name,
        )
        return None

    # ── IV-06b: classificacao_risco válido ───────────────────
    classif_normalized = _normalize_risk(
        eq.classificacao_do_risco.classificacao_risco
    )
    if classif_normalized is None:
        logger.warning(
            "IV-06b | classificacao_risco inválido '{}' para '{}' — equipamento ignorado",
            eq.classificacao_do_risco.classificacao_risco,
            name,
        )
        return None

    # ── IV-08: filtrar strings vazias (já coberto por _clean_list) ─

    # ── Limites §5.1: truncar strings longas ──────────────────────
    name_trunc = _truncate(name, _MAX_NAME_LEN)
    desc_trunc = _truncate(
        (eq.descricao_da_operacao or "Não informado").strip() or "Não informado",
        _MAX_DESC_LEN,
    )

    medidas_existentes = _clean_list(
        list(eq.medidas_preventivas_existentes),
        max_items=_MAX_ARRAY_ITEMS,
        max_item_len=_MAX_ITEM_LEN,
    )
    medidas_implementar = _clean_list(
        list(eq.medidas_a_implementar),
        max_items=_MAX_ARRAY_ITEMS,
        max_item_len=_MAX_ITEM_LEN,
    )

    # ── IV-09: total JSON ≤ 8000 chars ───────────────────────────
    payload_dict: dict[str, Any] = {
        "equipment_name": name_trunc,
        "descricao_da_operacao": desc_trunc,
        "identificacao_dos_perigos": perigos,
        "causas_possiveis": causas,
        "consequencias_potenciais": consequencias,
        "classificacao_do_risco": {
            "categoria_severidade": sev_normalized,
            "categoria_probabilidade": risco_normalized,
            "classificacao_risco": classif_normalized,
        },
        "medidas_preventivas_existentes": medidas_existentes,
        "medidas_a_implementar": medidas_implementar,
        "normas_aplicaveis": normas,
    }

    json_size = _estimate_json_size(payload_dict)
    if json_size > _MAX_TOTAL_JSON_CHARS:
        logger.info(
            "IV-09 | JSON size {} > {} para '{}' — aplicando shrink",
            json_size,
            _MAX_TOTAL_JSON_CHARS,
            name,
        )
        payload_dict = _shrink_to_budget(payload_dict, _MAX_TOTAL_JSON_CHARS)

    # ── Construir o modelo Pydantic (validação final) ─────────────
    # Preparar bloco residual (V3) se disponível
    residual_risk = None
    if eq.classificacao_risco_residual is not None:
        residual_risk = ResidualRiskClassification(
            categoria_severidade=eq.classificacao_risco_residual.categoria_severidade,
            categoria_probabilidade=eq.classificacao_risco_residual.categoria_probabilidade,
            classificacao_risco=eq.classificacao_risco_residual.classificacao_risco,
        )

    try:
        llm_input = EquipmentLLMInput(
            equipment_name=payload_dict["equipment_name"],
            descricao_da_operacao=payload_dict["descricao_da_operacao"],
            identificacao_dos_perigos=payload_dict["identificacao_dos_perigos"],
            causas_possiveis=payload_dict["causas_possiveis"],
            consequencias_potenciais=payload_dict["consequencias_potenciais"],
            classificacao_do_risco=RiskClassification(
                categoria_severidade=payload_dict["classificacao_do_risco"][
                    "categoria_severidade"
                ],
                categoria_probabilidade=payload_dict["classificacao_do_risco"][
                    "categoria_probabilidade"
                ],
                classificacao_risco=payload_dict["classificacao_do_risco"][
                    "classificacao_risco"
                ],
            ),
            classificacao_risco_residual=residual_risk,
            medidas_preventivas_existentes=payload_dict[
                "medidas_preventivas_existentes"
            ],
            medidas_a_implementar=payload_dict["medidas_a_implementar"],
            normas_aplicaveis=payload_dict["normas_aplicaveis"],
            normative_context=normative_context or [],
            literature_context=literature_context or [],
        )
    except Exception:
        logger.exception(
            "Falha ao construir EquipmentLLMInput para '{}' — equipamento ignorado",
            name,
        )
        return None

    logger.debug(
        "EquipmentLLMInput construído para '{}' | perigos={} | normas={} | json_chars={}",
        name_trunc,
        len(perigos),
        len(normas),
        _estimate_json_size(payload_dict),
    )

    return llm_input


# ---------------------------------------------------------------------------
# Batch helper
# ---------------------------------------------------------------------------


def build_all_equipment_prompt_contexts(
    equipment_contexts: list[EquipmentContext],
    normas_aplicaveis: list[str],
    *,
    normative_contexts: dict[str, list[NormativeExcerpt]] | None = None,
    literature_contexts: dict[str, list[LiteratureExcerpt]] | None = None,
) -> list[EquipmentLLMInput]:
    """Constrói payloads LLM para todos os equipamentos de uma vez.

    Equipamentos inválidos são silenciosamente ignorados (logados como
    warning). A ordem de saída preserva a ordem dos ``equipment_contexts``
    válidos.

    Args:
        equipment_contexts: Lista de contextos (de ``build_equipment_contexts``).
        normas_aplicaveis: Normas do profile config.
        normative_contexts: Mapa ``equipment_name → trechos normativos``.
            Opcional — quando fornecido, os trechos correspondentes são
            anexados ao ``EquipmentLLMInput`` de cada equipamento.
            Chaves não encontradas são ignoradas.
        literature_contexts: Mapa ``equipment_name → trechos de literatura``.
            Mesmo comportamento de ``normative_contexts``.

    Returns:
        Lista de ``EquipmentLLMInput`` válidos, prontos para serialização.
    """
    norm_map = {k.strip().lower(): v for k, v in (normative_contexts or {}).items()}
    lit_map = {k.strip().lower(): v for k, v in (literature_contexts or {}).items()}
    results: list[EquipmentLLMInput] = []

    for ctx in equipment_contexts:
        eq_name = ctx.equipment_name
        normalized_name = eq_name.strip().lower()
        norm_ctx = norm_map.get(normalized_name)
        lit_ctx = lit_map.get(normalized_name)

        if norm_map and norm_ctx is None:
            logger.warning(
                "RAG | norm_map lookup miss | equip='{}' | chaves_disponíveis={}",
                eq_name,
                list(norm_map.keys())[:5],
            )

        llm_input = build_equipment_prompt_context(
            ctx,
            normas_aplicaveis,
            normative_context=norm_ctx,
            literature_context=lit_ctx,
        )
        if llm_input is not None:
            results.append(llm_input)

    logger.info(
        "Prompt contexts construídos | input={} | válidos={} | descartados={}",
        len(equipment_contexts),
        len(results),
        len(equipment_contexts) - len(results),
    )

    return results
