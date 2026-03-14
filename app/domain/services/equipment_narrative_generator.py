"""Serviço de domínio — geração per-equipment de narrativas via LLM.

Orquestra o ciclo completo para **um** equipamento:
  1. Carrega system prompt de ``prompts/equipment_system_prompt.txt``.
  2. Constrói user prompt via ``build_equipment_user_prompt``.
  3. Chama o LLM (via callable assíncrono).
  4. Valida output (OV-01…OV-14).
  5. Retry com prompt reforçado se necessário.
  6. Fallback determinístico como última instância.

Contrato de referência: ``docs/equipment_llm_contract.md``, §9–§10.

──────────────────────────────────────────────────────────────────────
 DESIGN DECISIONS
──────────────────────────────────────────────────────────────────────

 • O gerador **não depende** diretamente de ``OpenRouterClient``.
   Em vez disso recebe um callable ``llm_call`` assíncrono com a
   assinatura ``async (system: str, user: str) -> str``.
   Isso facilita testes unitários e desacopla do transporte HTTP.

 • Suporta execução sequencial (default) e concorrente
   via ``generate_all_equipment_narratives(..., max_concurrency=3)``.

 **NÃO** faz: acesso a banco, persistência, atualização de progresso.
──────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Awaitable, Callable

from loguru import logger

from app.domain.entities import EquipmentLLMInput, EquipmentLLMOutput
from app.domain.services.equipment_output_validator import (
    ValidationResult,
    build_fallback,
    validate_llm_output,
)
from app.domain.services.equipment_user_prompt import build_equipment_user_prompt
from app.adapters.llm.prompts import get_profile_config


# ---------------------------------------------------------------------------
# Tipo do callable LLM
# ---------------------------------------------------------------------------

LLMCallFn = Callable[[str, str], Awaitable[str]]
"""async (system_prompt, user_prompt) -> raw_content"""


# ---------------------------------------------------------------------------
# System prompt (carregado uma vez por processo)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_CACHE: str | None = None
_SYSTEM_PROMPT_PROFILE_CACHE: dict[str, str] = {}


def _load_base_system_prompt() -> str:
    """Carrega o template base do system prompt de ``prompts/equipment_system_prompt.txt``.

    Cacheia em memória após a primeira leitura.
    """
    global _SYSTEM_PROMPT_CACHE  # noqa: PLW0603
    if _SYSTEM_PROMPT_CACHE is not None:
        return _SYSTEM_PROMPT_CACHE

    # Caminho relativo ao raiz do projeto Python
    prompt_path = Path(__file__).resolve().parents[3] / "prompts" / "equipment_system_prompt.txt"
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"System prompt não encontrado: {prompt_path}"
        )

    _SYSTEM_PROMPT_CACHE = prompt_path.read_text(encoding="utf-8").strip()
    logger.debug("System prompt per-equipment carregado | {} chars", len(_SYSTEM_PROMPT_CACHE))
    return _SYSTEM_PROMPT_CACHE


def _load_system_prompt(profile: str | None = None) -> str:
    """Carrega o system prompt adaptado ao perfil selecionado.

    Para o perfil 'dust' (ou None/default), usa o prompt original do arquivo.
    Para outros perfis ('gas', 'vapors'), substitui a especialização.

    Args:
        profile: Identificador do perfil ('dust', 'gas', 'vapors').

    Returns:
        System prompt completo.
    """
    effective_profile = profile if profile and profile in ("dust", "gas", "vapors") else "dust"

    if effective_profile in _SYSTEM_PROMPT_PROFILE_CACHE:
        return _SYSTEM_PROMPT_PROFILE_CACHE[effective_profile]

    base = _load_base_system_prompt()

    if effective_profile == "dust":
        _SYSTEM_PROMPT_PROFILE_CACHE[effective_profile] = base
        return base

    # For non-dust profiles, replace the DHA/dust specialization
    cfg = get_profile_config(effective_profile)
    adapted = base.replace(
        "análise de perigos por poéira combustível (DHA — Dust Hazard Analysis)",
        cfg["foco"],
    ).replace(
        "relatório técnico de DHA",
        f"relatório técnico de {cfg['label']}",
    )

    _SYSTEM_PROMPT_PROFILE_CACHE[effective_profile] = adapted
    logger.debug(
        "System prompt per-equipment adaptado para perfil '{}' | {} chars",
        effective_profile, len(adapted),
    )
    return adapted


def _build_retry_system_prompt(profile: str | None = None) -> str:
    """Constrói system prompt reforçado para retry de JSON.

    Adiciona instrução extra de formatação ao prompt original.
    """
    base = _load_system_prompt(profile)
    reinforcement = (
        "\n\n"
        "ATENÇÃO: Sua resposta anterior NÃO era JSON válido. "
        "Responda SOMENTE com um objeto JSON puro. "
        "Sem blocos de código, sem markdown, sem texto antes ou depois. "
        "Apenas o JSON conforme o formato especificado."
    )
    return base + reinforcement


# ---------------------------------------------------------------------------
# Geração per-equipment
# ---------------------------------------------------------------------------


class EquipmentGenerationResult:
    """Resultado da geração para um equipamento."""

    __slots__ = ("equipment_name", "output", "source", "attempts")

    def __init__(
        self,
        equipment_name: str,
        output: EquipmentLLMOutput,
        source: str,
        attempts: int,
    ) -> None:
        self.equipment_name = equipment_name
        self.output = output
        self.source = source  # "llm", "llm_retry", "fallback"
        self.attempts = attempts


async def generate_equipment_narrative(
    llm_input: EquipmentLLMInput,
    llm_call: LLMCallFn,
    *,
    profile: str | None = None,
) -> EquipmentGenerationResult:
    """Gera narrativas (recomendações + justificativas) para um equipamento.

    Executa o ciclo de retry conforme §9 do contrato:
      - Attempt 1: prompt padrão
      - Attempt 2 (se JSON inválido): prompt reforçado
      - Attempt 3: fallback determinístico

    Args:
        llm_input: Payload validado e bounded do equipamento.
        llm_call: Callable assíncrono ``(system, user) -> raw_content``.
        profile: Perfil de análise ('dust', 'gas', 'vapors').

    Returns:
        ``EquipmentGenerationResult`` — sempre retorna output, nunca falha.
    """
    equip = llm_input.equipment_name
    user_prompt = build_equipment_user_prompt(llm_input)
    system_prompt = _load_system_prompt(profile)

    # ── Attempt 1: chamada padrão ─────────────────────────────────
    logger.info("LLM per-equipment | equip={} | attempt=1", equip)
    try:
        raw = await llm_call(system_prompt, user_prompt)
        result = validate_llm_output(raw, llm_input)

        if result.success and result.output is not None:
            logger.info(
                "LLM per-equipment OK | equip={} | recs={} | attempt=1",
                equip, len(result.output.recomendacoes_tecnicas),
            )
            return EquipmentGenerationResult(
                equipment_name=equip,
                output=result.output,
                source="llm",
                attempts=1,
            )

        logger.warning(
            "LLM per-equipment validação falhou | equip={} | reason={} | needs_retry={}",
            equip, result.reason, result.needs_retry,
        )

        if not result.needs_retry:
            # Validação falhou sem possibilidade de retry → fallback direto
            return _make_fallback_result(llm_input, attempts=1)

    except Exception as exc:
        logger.warning(
            "LLM per-equipment erro | equip={} | attempt=1 | {}",
            equip, str(exc),
        )

    # ── Attempt 2: retry com prompt reforçado ─────────────────────
    logger.info("LLM per-equipment | equip={} | attempt=2 (retry)", equip)
    retry_system = _build_retry_system_prompt(profile)

    try:
        raw_retry = await llm_call(retry_system, user_prompt)
        result_retry = validate_llm_output(raw_retry, llm_input)

        if result_retry.success and result_retry.output is not None:
            logger.info(
                "LLM per-equipment OK (retry) | equip={} | recs={} | attempt=2",
                equip, len(result_retry.output.recomendacoes_tecnicas),
            )
            return EquipmentGenerationResult(
                equipment_name=equip,
                output=result_retry.output,
                source="llm_retry",
                attempts=2,
            )

        logger.warning(
            "LLM per-equipment retry validação falhou | equip={} | reason={}",
            equip, result_retry.reason,
        )
    except Exception as exc:
        logger.warning(
            "LLM per-equipment erro | equip={} | attempt=2 | {}",
            equip, str(exc),
        )

    # ── Attempt 3: fallback determinístico ────────────────────────
    return _make_fallback_result(llm_input, attempts=2)


async def generate_all_equipment_narratives(
    llm_inputs: list[EquipmentLLMInput],
    llm_call: LLMCallFn,
    *,
    max_concurrency: int = 1,
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
    profile: str | None = None,
) -> list[EquipmentGenerationResult]:
    """Gera narrativas para todos os equipamentos.

    Args:
        llm_inputs: Lista de inputs validados.
        llm_call: Callable LLM assíncrono.
        max_concurrency: Máximo de chamadas paralelas (default 1 = sequencial).
        on_progress: Callback opcional ``(completed, total) -> None``
            para atualização de progresso.

    Returns:
        Lista de ``EquipmentGenerationResult``, na mesma ordem dos inputs.
    """
    total = len(llm_inputs)
    if total == 0:
        return []

    # ── DEVLLM: gera LLM apenas para o 1º equipamento ────────
    from app.infrastructure.config import get_settings  # noqa: PLC0415
    devllm = get_settings().DEVLLM
    if devllm:
        logger.warning(
            "DEVLLM=true | Apenas o 1º equipamento usará LLM, "
            "os demais {} serão fallback vazio",
            total - 1,
        )

    logger.info(
        "Iniciando geração per-equipment | total={} | concurrency={}",
        total, max_concurrency,
    )

    if max_concurrency <= 1:
        # Execução sequencial
        results: list[EquipmentGenerationResult] = []
        for idx, inp in enumerate(llm_inputs):
            if devllm and idx > 0:
                result = _make_fallback_result(inp, attempts=0)
                result.source = "devllm_skip"
            else:
                result = await generate_equipment_narrative(inp, llm_call, profile=profile)
            results.append(result)
            if on_progress:
                await on_progress(idx + 1, total)
        return results

    # Execução concorrente com semáforo
    semaphore = asyncio.Semaphore(max_concurrency)
    completed_count = 0
    lock = asyncio.Lock()

    async def _generate_with_semaphore(
        idx: int,
        inp: EquipmentLLMInput,
    ) -> EquipmentGenerationResult:
        nonlocal completed_count
        async with semaphore:
            if devllm and idx > 0:
                result = _make_fallback_result(inp, attempts=0)
                result.source = "devllm_skip"
            else:
                result = await generate_equipment_narrative(inp, llm_call, profile=profile)
            async with lock:
                completed_count += 1
                if on_progress:
                    await on_progress(completed_count, total)
            return result

    tasks = [_generate_with_semaphore(idx, inp) for idx, inp in enumerate(llm_inputs)]
    results = await asyncio.gather(*tasks)

    # Manter mesma ordem dos inputs
    return list(results)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fallback_result(
    llm_input: EquipmentLLMInput,
    attempts: int,
) -> EquipmentGenerationResult:
    """Constrói resultado de fallback determinístico."""
    logger.warning(
        "Usando fallback determinístico | equip={} | attempts_feitas={}",
        llm_input.equipment_name, attempts,
    )
    output = build_fallback(llm_input)
    return EquipmentGenerationResult(
        equipment_name=llm_input.equipment_name,
        output=output,
        source="fallback",
        attempts=attempts + 1,
    )
