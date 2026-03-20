"""Serviço de domínio — valida e sanitiza a saída do LLM per-equipment.

Implementa as regras OV-01 … OV-14 definidas em
``docs/equipment_llm_contract.md``, §4, e os limites de tamanho §5.2.

──────────────────────────────────────────────────────────────────────
 RESPONSABILIDADES
──────────────────────────────────────────────────────────────────────

 1. Parsear JSON cru da resposta do LLM.
 2. Validar estrutura (OV-01 … OV-09).
 3. Validar conteúdo (OV-10 … OV-14).
 4. Aplicar limites de tamanho §5.2.
 5. Construir fallback determinístico (§4.3).

 **NÃO** faz: chamadas de rede, acesso a banco, chamadas ao LLM.
──────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from app.domain.entities import (
    EquipmentLLMInput,
    EquipmentLLMOutput,
    JustificativaTecnica,
    RecomendacaoTecnica,
)


# ---------------------------------------------------------------------------
# Constantes §5.2
# ---------------------------------------------------------------------------

_MIN_RECS = 2
_MAX_RECS = 10
_REC_TEXT_MIN = 50
_REC_TEXT_MAX = 500
_REC_NORMA_MIN = 5
_REC_NORMA_MAX = 150
_JUST_TEXT_MIN = 80
_JUST_TEXT_MAX = 1_000
_TOTAL_OUTPUT_MAX = 15_000


# ---------------------------------------------------------------------------
# Resultado de validação
# ---------------------------------------------------------------------------


class ValidationResult:
    """Resultado da validação de output — sucesso ou falha com motivo."""

    __slots__ = ("success", "output", "reason", "needs_retry")

    def __init__(
        self,
        *,
        success: bool,
        output: EquipmentLLMOutput | None = None,
        reason: str = "",
        needs_retry: bool = False,
    ) -> None:
        self.success = success
        self.output = output
        self.reason = reason
        self.needs_retry = needs_retry


# ---------------------------------------------------------------------------
# Funções públicas
# ---------------------------------------------------------------------------


def validate_llm_output(
    raw_json: str,
    llm_input: EquipmentLLMInput,
) -> ValidationResult:
    """Valida e sanitiza a resposta crua do LLM.

    Aplica as regras OV-01 … OV-14 e limites §5.2 sequencialmente.

    Args:
        raw_json: String JSON retornada pelo LLM.
        llm_input: Input original (usado para fallback de norma e dados).

    Returns:
        ``ValidationResult`` com ``success=True`` e ``output`` preenchido
        se aprovado, ou ``success=False`` com ``reason`` e ``needs_retry``
        indicando se vale fazer retry LLM.
    """
    equip = llm_input.equipment_name

    # ── OV-01: parsear JSON ───────────────────────────────────────
    data = _parse_json(raw_json)
    if data is None:
        logger.warning("OV-01 falhou | equip={} | JSON inválido", equip)
        return ValidationResult(
            success=False,
            reason="OV-01: resposta não é JSON válido",
            needs_retry=True,
        )

    # ── OV-02: chaves obrigatórias ────────────────────────────────
    recs_raw = data.get("recomendacoes_tecnicas")
    justs_raw = data.get("justificativas_tecnicas")

    if recs_raw is None or justs_raw is None:
        missing = []
        if recs_raw is None:
            missing.append("recomendacoes_tecnicas")
        if justs_raw is None:
            missing.append("justificativas_tecnicas")
        logger.warning("OV-02 falhou | equip={} | faltam: {}", equip, missing)
        return ValidationResult(
            success=False,
            reason=f"OV-02: chaves faltantes: {missing}",
            needs_retry=True,
        )

    # ── OV-03 / OV-04: arrays de objetos ─────────────────────────
    if not isinstance(recs_raw, list) or not all(isinstance(r, dict) for r in recs_raw):
        logger.warning("OV-03 falhou | equip={}", equip)
        return ValidationResult(
            success=False,
            reason="OV-03: recomendacoes_tecnicas não é array de objetos",
            needs_retry=True,
        )
    if not isinstance(justs_raw, list) or not all(isinstance(j, dict) for j in justs_raw):
        logger.warning("OV-04 falhou | equip={}", equip)
        return ValidationResult(
            success=False,
            reason="OV-04: justificativas_tecnicas não é array de objetos",
            needs_retry=True,
        )

    # ── OV-05: igualar tamanhos ───────────────────────────────────
    min_len = min(len(recs_raw), len(justs_raw))
    if len(recs_raw) != len(justs_raw):
        logger.info(
            "OV-05 | equip={} | recs={}, justs={} → trim para {}",
            equip, len(recs_raw), len(justs_raw), min_len,
        )
    recs_raw = recs_raw[:min_len]
    justs_raw = justs_raw[:min_len]

    # ── OV-10 / OV-11: remover itens com texto vazio ─────────────
    cleaned_pairs: list[tuple[dict, dict]] = []
    for rec, jst in zip(recs_raw, justs_raw):
        rec_text = (rec.get("texto") or "").strip()
        jst_text = (jst.get("texto") or "").strip()
        if not rec_text:
            logger.info("OV-10 | equip={} | recomendação com texto vazio removida", equip)
            continue
        if not jst_text:
            logger.info("OV-11 | equip={} | justificativa com texto vazio removida", equip)
            continue
        cleaned_pairs.append((rec, jst))

    # ── OV-13: remover recomendações duplicadas ───────────────────
    seen_texts: set[str] = set()
    deduped_pairs: list[tuple[dict, dict]] = []
    for rec, jst in cleaned_pairs:
        text_key = (rec.get("texto") or "").strip().lower()
        if text_key in seen_texts:
            logger.info("OV-13 | equip={} | duplicata removida", equip)
            continue
        seen_texts.add(text_key)
        deduped_pairs.append((rec, jst))

    # ── OV-07: truncar em 10 ─────────────────────────────────────
    if len(deduped_pairs) > _MAX_RECS:
        logger.info("OV-07 | equip={} | truncando de {} para {}", equip, len(deduped_pairs), _MAX_RECS)
        deduped_pairs = deduped_pairs[:_MAX_RECS]

    # ── OV-06 / OV-14: mínimo 2 ──────────────────────────────────
    if len(deduped_pairs) < _MIN_RECS:
        logger.warning(
            "OV-06/OV-14 | equip={} | apenas {} itens após limpeza",
            equip, len(deduped_pairs),
        )
        return ValidationResult(
            success=False,
            reason=f"OV-06/OV-14: apenas {len(deduped_pairs)} recomendações após limpeza (mín {_MIN_RECS})",
            needs_retry=True,
        )

    # ── OV-08 / OV-09: renumerar sequencialmente ─────────────────
    # ── OV-12: fallback de norma_referencia (fortalecido com RAG) ─
    # ── §5.2: limites de tamanho ──────────────────────────────────
    default_norma = llm_input.normas_aplicaveis[0] if llm_input.normas_aplicaveis else ""

    # Conjunto de normas válidas: normas do profile + sources do RAG
    valid_norm_sources: set[str] = set()
    for na in llm_input.normas_aplicaveis:
        valid_norm_sources.add(na.strip().lower())
        # Adicionar variantes parciais (ex.: "ABNT NBR 16385")
        for part in na.split("—"):
            cleaned = part.strip().lower()
            if len(cleaned) >= 5:
                valid_norm_sources.add(cleaned)
    for exc in llm_input.normative_context:
        src_lower = exc.source.strip().lower()
        valid_norm_sources.add(src_lower)
        # Também aceitar sem extensão .pdf
        if src_lower.endswith(".pdf"):
            valid_norm_sources.add(src_lower[:-4].strip())

    has_normative_context = bool(llm_input.normative_context)

    final_recs: list[RecomendacaoTecnica] = []
    final_justs: list[JustificativaTecnica] = []

    for idx, (rec, jst) in enumerate(deduped_pairs, 1):
        # Texto da recomendação
        rec_text = _truncate(
            (rec.get("texto") or "").strip(),
            _REC_TEXT_MAX,
        )

        # Norma referência (OV-12 — fortalecido)
        norma = (rec.get("norma_referencia") or "").strip()
        if len(norma) < _REC_NORMA_MIN:
            norma = default_norma
        else:
            # Validar se a norma citada existe entre as fontes válidas
            norma_lower = norma.strip().lower()
            norm_is_valid = any(
                valid_src in norma_lower or norma_lower in valid_src
                for valid_src in valid_norm_sources
            )
            if not norm_is_valid and has_normative_context:
                # Fallback: usar a norma mais relevante do contexto RAG
                best_source = llm_input.normative_context[0].source
                logger.info(
                    "OV-12 | equip={} | norma inventada '{}' → fallback para '{}' (RAG)",
                    equip,
                    norma,
                    best_source,
                )
                norma = best_source
            elif not norm_is_valid:
                # Sem RAG: manter fallback para norma do perfil
                logger.info(
                    "OV-12 | equip={} | norma '{}' não reconhecida → fallback default",
                    equip,
                    norma,
                )
                norma = default_norma

        norma = _truncate(norma, _REC_NORMA_MAX)

        # Texto da justificativa
        jst_text = _truncate(
            (jst.get("texto") or "").strip(),
            _JUST_TEXT_MAX,
        )

        final_recs.append(
            RecomendacaoTecnica(numero=idx, texto=rec_text, norma_referencia=norma)
        )
        final_justs.append(
            JustificativaTecnica(numero=idx, texto=jst_text)
        )

    # ── §5.2: total output ≤ 15.000 chars ────────────────────────
    output_data = {
        "recomendacoes_tecnicas": [r.model_dump() for r in final_recs],
        "justificativas_tecnicas": [j.model_dump() for j in final_justs],
    }
    serialized = json.dumps(output_data, ensure_ascii=False)
    if len(serialized) > _TOTAL_OUTPUT_MAX:
        logger.info(
            "§5.2 | equip={} | output {} chars > {} — truncando justificativas",
            equip, len(serialized), _TOTAL_OUTPUT_MAX,
        )
        final_justs = _shrink_justificativas(final_justs, final_recs, _TOTAL_OUTPUT_MAX)

    try:
        output = EquipmentLLMOutput(
            recomendacoes_tecnicas=final_recs,
            justificativas_tecnicas=final_justs,
        )
    except Exception as exc:
        logger.error("Falha ao construir EquipmentLLMOutput | equip={} | {}", equip, exc)
        return ValidationResult(
            success=False,
            reason=f"Falha ao construir modelo: {exc}",
            needs_retry=False,
        )

    return ValidationResult(success=True, output=output)


def build_fallback(llm_input: EquipmentLLMInput) -> EquipmentLLMOutput:
    """Constrói output determinístico de fallback (§4.3).

    Usa ``medidas_a_implementar`` do input como recomendações.
    Se vazio, usa uma recomendação genérica.

    Args:
        llm_input: Input original do equipamento.

    Returns:
        ``EquipmentLLMOutput`` determinístico.
    """
    items = list(llm_input.medidas_a_implementar) or [
        "Realizar avaliação detalhada conforme normas aplicáveis"
    ]

    # Garantir mínimo de 2 itens
    if len(items) == 1:
        items.append(
            "Implementar plano de ação corretiva com cronograma de adequação"
        )

    default_norma = (
        llm_input.normas_aplicaveis[0] if llm_input.normas_aplicaveis else "Norma aplicável"
    )

    sev = llm_input.classificacao_do_risco.categoria_severidade
    risco = llm_input.classificacao_do_risco.categoria_risco
    equip_name = llm_input.equipment_name

    recs: list[RecomendacaoTecnica] = []
    justs: list[JustificativaTecnica] = []

    for i, medida in enumerate(items[:_MAX_RECS], start=1):
        recs.append(
            RecomendacaoTecnica(
                numero=i,
                texto=medida,
                norma_referencia=default_norma,
            )
        )
        justs.append(
            JustificativaTecnica(
                numero=i,
                texto=(
                    f"Recomendação baseada na análise de risco do equipamento "
                    f"{equip_name}, com severidade {sev} e risco {risco}."
                ),
            )
        )

    logger.info(
        "Fallback determinístico gerado | equip={} | recs={}",
        equip_name, len(recs),
    )

    return EquipmentLLMOutput(
        recomendacoes_tecnicas=recs,
        justificativas_tecnicas=justs,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_json(raw: str) -> dict[str, Any] | None:
    """Parseia string JSON, lidando com blocos markdown ````` ```.

    Returns:
        Dicionário ou ``None`` se inválido.
    """
    from app.domain.services.json_utils import parse_llm_json
    return parse_llm_json(raw)


def _truncate(text: str, max_len: int) -> str:
    """Trunca texto adicionando ``…`` se exceder o limite."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _shrink_justificativas(
    justs: list[JustificativaTecnica],
    recs: list[RecomendacaoTecnica],
    max_total: int,
) -> list[JustificativaTecnica]:
    """Encurta textos das justificativas proporcionalmente até caber no limite.

    Estratégia: reduz o max de cada justificativa iterativamente.
    """
    # Calcular tamanho base (recs + overhead JSON)
    recs_data = [r.model_dump() for r in recs]
    base_size = len(json.dumps({"recomendacoes_tecnicas": recs_data}, ensure_ascii=False))
    overhead = 80  # chaves, colchetes, vírgulas extras
    available = max_total - base_size - overhead

    # Distribuir igualmente entre justificativas
    per_just = max(100, available // max(len(justs), 1))

    new_justs: list[JustificativaTecnica] = []
    for j in justs:
        texto = _truncate(j.texto, per_just)
        new_justs.append(JustificativaTecnica(numero=j.numero, texto=texto))

    return new_justs
