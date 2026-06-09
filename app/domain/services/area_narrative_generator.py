"""Serviço de domínio — geração de narrativas para Classificação de Áreas.

Orquestra duas modalidades de chamada LLM:
  1. ``generate_global_narrative`` — 1 chamada para seções narrativas
     do relatório (introdução, escopo, considerações gerais, metodologia,
     recomendações, conclusão).
  2. ``generate_all_area_narratives`` — N chamadas, uma por
     equipamento/área (justificativa de zona, análise de ventilação,
     recomendações específicas).

Cada chamada implementa o ciclo: tentativa → retry com prompt reforçado
→ fallback determinístico, garantindo que **sempre** retorna output.

Análogo a ``equipment_narrative_generator`` mas adaptado ao domínio
de classificação de áreas (IEC 60079-10-1/10-2).
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from loguru import logger

from app.adapters.llm.area_prompts import (
    build_area_global_user_prompt,
    build_area_per_area_user_prompt,
    build_area_system_prompt,
    build_area_system_prompt_retry,
)
from app.domain.entities.area_classification import AreaClassificationContext
from app.domain.services.area_output_validator import (
    AreaGlobalOutput,
    AreaPerAreaOutput,
    build_global_fallback,
    build_per_area_fallback,
    validate_global_output,
    validate_per_area_output,
)


LLMCallFn = Callable[[str, str], Awaitable[str]]
LLMCallFnWithModel = Callable[[str, str, str | None], Awaitable[str]]


# ---------------------------------------------------------------------------
# Resultado de geração
# ---------------------------------------------------------------------------

class AreaNarrativeResult:
    """Resultado da geração para uma área (1 equipamento)."""

    __slots__ = ("identificacao", "output", "source", "attempts", "model_used")

    def __init__(
        self,
        identificacao: str,
        output: AreaPerAreaOutput,
        source: str,
        attempts: int,
        model_used: str = "",
    ) -> None:
        self.identificacao = identificacao
        self.output = output
        self.source = source  # "llm", "llm_retry", "fallback"
        self.attempts = attempts
        self.model_used = model_used


class AreaGlobalResult:
    """Resultado da geração das seções globais."""

    __slots__ = ("output", "source", "attempts", "model_used")

    def __init__(
        self,
        output: AreaGlobalOutput,
        source: str,
        attempts: int,
        model_used: str = "",
    ) -> None:
        self.output = output
        self.source = source
        self.attempts = attempts
        self.model_used = model_used


# ---------------------------------------------------------------------------
# Helper: chamada LLM com fallback de assinatura
# ---------------------------------------------------------------------------

async def _do_llm_call(
    llm_call: LLMCallFn | LLMCallFnWithModel,
    system: str,
    user: str,
    model_override: str | None,
) -> str:
    if model_override is not None:
        try:
            return await llm_call(system, user, model_override)  # type: ignore[call-arg]
        except TypeError:
            pass
    return await llm_call(system, user)


# ---------------------------------------------------------------------------
# Geração global (1 chamada)
# ---------------------------------------------------------------------------

async def generate_global_narrative(
    *,
    company_metadata: dict[str, Any] | None,
    area_contexts: list[AreaClassificationContext],
    llm_call: LLMCallFn | LLMCallFnWithModel,
    profile: str = "areas",
    model_override: str | None = None,
) -> AreaGlobalResult:
    """Gera as seções narrativas globais do relatório (1 chamada LLM)."""
    system_prompt = build_area_system_prompt(profile)
    user_prompt = build_area_global_user_prompt(
        company_metadata=company_metadata,
        area_contexts=area_contexts,
        profile=profile,
    )
    model_label = model_override or "default"

    # ── Attempt 1 ─────────────────────────────────────────────
    logger.info("LLM area-global | model={} | attempt=1", model_label)
    try:
        raw = await _do_llm_call(llm_call, system_prompt, user_prompt, model_override)
        result = validate_global_output(raw)
        if result.success and result.output is not None:
            logger.info("LLM area-global OK | model={} | attempt=1", model_label)
            return AreaGlobalResult(
                output=result.output, source="llm", attempts=1,
                model_used=model_override or "",
            )
        logger.warning("LLM area-global validação falhou | reason={}", result.reason)
    except Exception as exc:
        logger.warning("LLM area-global erro | attempt=1 | {}", str(exc))

    # ── Attempt 2 (retry com prompt reforçado) ────────────────
    logger.info("LLM area-global | model={} | attempt=2 (retry)", model_label)
    retry_system = build_area_system_prompt_retry(profile)
    try:
        raw_retry = await _do_llm_call(llm_call, retry_system, user_prompt, model_override)
        result_retry = validate_global_output(raw_retry)
        if result_retry.success and result_retry.output is not None:
            logger.info("LLM area-global OK (retry) | model={}", model_label)
            return AreaGlobalResult(
                output=result_retry.output, source="llm_retry", attempts=2,
                model_used=model_override or "",
            )
        logger.warning("LLM area-global retry falhou | reason={}", result_retry.reason)
    except Exception as exc:
        logger.warning("LLM area-global erro | attempt=2 | {}", str(exc))

    # ── Attempt 3: fallback ──────────────────────────────────
    logger.warning("LLM area-global usando fallback determinístico")
    return AreaGlobalResult(
        output=build_global_fallback(),
        source="fallback",
        attempts=2,
        model_used=model_override or "",
    )


# ---------------------------------------------------------------------------
# Geração per-área (N chamadas)
# ---------------------------------------------------------------------------

async def generate_area_narrative(
    ctx: AreaClassificationContext,
    llm_call: LLMCallFn | LLMCallFnWithModel,
    *,
    profile: str = "areas",
    model_override: str | None = None,
) -> AreaNarrativeResult:
    """Gera análise técnica para 1 equipamento/área."""
    system_prompt = build_area_system_prompt(profile)
    user_prompt = build_area_per_area_user_prompt(ctx, profile=profile)
    ident = ctx.identificacao
    model_label = model_override or "default"

    # ── Attempt 1 ─────────────────────────────────────────────
    logger.info("LLM area-per | id={} | model={} | attempt=1", ident, model_label)
    try:
        raw = await _do_llm_call(llm_call, system_prompt, user_prompt, model_override)
        result = validate_per_area_output(raw)
        if result.success and result.output is not None:
            logger.info("LLM area-per OK | id={} | recs={} | attempt=1",
                        ident, len(result.output.recomendacoes_especificas))
            return AreaNarrativeResult(
                identificacao=ident, output=result.output,
                source="llm", attempts=1, model_used=model_override or "",
            )
        logger.warning("LLM area-per validação falhou | id={} | reason={}",
                       ident, result.reason)
    except Exception as exc:
        logger.warning("LLM area-per erro | id={} | attempt=1 | {}", ident, str(exc))

    # ── Attempt 2 (retry) ─────────────────────────────────────
    logger.info("LLM area-per | id={} | attempt=2 (retry)", ident)
    retry_system = build_area_system_prompt_retry(profile)
    try:
        raw_retry = await _do_llm_call(llm_call, retry_system, user_prompt, model_override)
        result_retry = validate_per_area_output(raw_retry)
        if result_retry.success and result_retry.output is not None:
            logger.info("LLM area-per OK (retry) | id={}", ident)
            return AreaNarrativeResult(
                identificacao=ident, output=result_retry.output,
                source="llm_retry", attempts=2, model_used=model_override or "",
            )
        logger.warning("LLM area-per retry falhou | id={} | reason={}",
                       ident, result_retry.reason)
    except Exception as exc:
        logger.warning("LLM area-per erro | id={} | attempt=2 | {}", ident, str(exc))

    # ── Attempt 3: fallback ──────────────────────────────────
    logger.warning("LLM area-per usando fallback | id={}", ident)
    return AreaNarrativeResult(
        identificacao=ident,
        output=build_per_area_fallback(ctx),
        source="fallback",
        attempts=2,
        model_used=model_override or "",
    )


async def generate_all_area_narratives(
    area_contexts: list[AreaClassificationContext],
    llm_call: LLMCallFn | LLMCallFnWithModel,
    *,
    max_concurrency: int = 1,
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
    profile: str = "areas",
    model_router: Any | None = None,
) -> list[AreaNarrativeResult]:
    """Gera análise técnica para todas as áreas (N equipamentos)."""
    total = len(area_contexts)
    if total == 0:
        return []

    # DEVLLM mode: apenas 1ª área usa LLM
    from app.infrastructure.config import get_settings  # noqa: PLC0415
    devllm = get_settings().DEVLLM
    if devllm:
        logger.warning(
            "DEVLLM=true | Apenas a 1ª área usará LLM, "
            "as demais {} serão fallback", total - 1,
        )

    def _resolve_model(ctx: AreaClassificationContext) -> str | None:
        if model_router is None:
            return None
        # Heurística de risco: contínua → high, primária → medium, secundária → low
        graus = {f.grau for f in ctx.fontes_liberacao}
        if "Contínua" in graus:
            risco = "Alto"
        elif "Primária" in graus:
            risco = "Médio"
        else:
            risco = "Baixo"
        try:
            decision = model_router.resolve_equipment(risco)
            return decision.model
        except Exception:
            return None

    logger.info(
        "Iniciando geração per-área | total={} | concurrency={} | tiered={}",
        total, max_concurrency, model_router is not None,
    )

    if max_concurrency <= 1:
        results: list[AreaNarrativeResult] = []
        for idx, ctx in enumerate(area_contexts):
            if devllm and idx > 0:
                result = AreaNarrativeResult(
                    identificacao=ctx.identificacao,
                    output=build_per_area_fallback(ctx),
                    source="devllm_skip", attempts=0, model_used="",
                )
            else:
                model_for = _resolve_model(ctx)
                result = await generate_area_narrative(
                    ctx, llm_call, profile=profile, model_override=model_for,
                )
            results.append(result)
            if on_progress:
                await on_progress(idx + 1, total)
        return results

    # Concorrência
    semaphore = asyncio.Semaphore(max_concurrency)
    completed_count = 0
    lock = asyncio.Lock()

    async def _run(idx: int, ctx: AreaClassificationContext) -> AreaNarrativeResult:
        nonlocal completed_count
        async with semaphore:
            if devllm and idx > 0:
                result = AreaNarrativeResult(
                    identificacao=ctx.identificacao,
                    output=build_per_area_fallback(ctx),
                    source="devllm_skip", attempts=0, model_used="",
                )
            else:
                model_for = _resolve_model(ctx)
                result = await generate_area_narrative(
                    ctx, llm_call, profile=profile, model_override=model_for,
                )
            async with lock:
                completed_count += 1
                if on_progress:
                    await on_progress(completed_count, total)
            return result

    tasks = [_run(idx, ctx) for idx, ctx in enumerate(area_contexts)]
    results = await asyncio.gather(*tasks)
    return list(results)


__all__ = [
    "AreaNarrativeResult",
    "AreaGlobalResult",
    "generate_global_narrative",
    "generate_area_narrative",
    "generate_all_area_narratives",
]
