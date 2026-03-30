"""Testes unitários — equipment_narrative_generator.

Testa o ciclo de geração per-equipment: attempt 1, retry, fallback.
Usa mocks para o callable LLM.
"""

from __future__ import annotations

import json

import pytest

from app.domain.entities import (
    EquipmentLLMInput,
    EquipmentLLMOutput,
    RiskClassification,
)
from app.domain.services.equipment_narrative_generator import (
    EquipmentGenerationResult,
    generate_all_equipment_narratives,
    generate_equipment_narrative,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_input(name: str = "Elevador EC-01", **overrides) -> EquipmentLLMInput:
    defaults = {
        "equipment_name": name,
        "descricao_da_operacao": "Transporte de grãos",
        "identificacao_dos_perigos": ["Poeira combustível"],
        "causas_possiveis": ["Falha aspiração"],
        "consequencias_potenciais": ["Explosão"],
        "classificacao_do_risco": RiskClassification(
            categoria_severidade="Alta",
            categoria_probabilidade="Alto",
            classificacao_risco="Alto",
        ),
        "medidas_preventivas_existentes": [],
        "medidas_a_implementar": ["Instalar supressão", "Revisar ventilação"],
        "normas_aplicaveis": ["NFPA 652:2022", "NR-10"],
    }
    defaults.update(overrides)
    return EquipmentLLMInput(**defaults)


def _make_valid_json(n: int = 3) -> str:
    data = {
        "recomendacoes_tecnicas": [
            {
                "numero": i,
                "texto": f"Recomendação técnica detalhada número {i} com texto suficiente para validação completa.",
                "norma_referencia": "NFPA 652:2022, seção 8.2",
            }
            for i in range(1, n + 1)
        ],
        "justificativas_tecnicas": [
            {
                "numero": i,
                "texto": (
                    f"Justificativa número {i}. O risco Alto com severidade Alta exige ação corretiva imediata."
                ),
            }
            for i in range(1, n + 1)
        ],
    }
    return json.dumps(data, ensure_ascii=False)


# ---------------------------------------------------------------------------
# generate_equipment_narrative — attempt 1 success
# ---------------------------------------------------------------------------


class TestAttempt1Success:
    @pytest.mark.asyncio
    async def test_first_attempt_success(self):
        valid_json = _make_valid_json(3)

        async def mock_llm(system: str, user: str) -> str:
            return valid_json

        inp = _make_input()
        result = await generate_equipment_narrative(inp, mock_llm)

        assert isinstance(result, EquipmentGenerationResult)
        assert result.source == "llm"
        assert result.attempts == 1
        assert len(result.output.recomendacoes_tecnicas) == 3


# ---------------------------------------------------------------------------
# generate_equipment_narrative — retry success
# ---------------------------------------------------------------------------


class TestRetrySuccess:
    @pytest.mark.asyncio
    async def test_retry_after_invalid_json(self):
        call_count = 0
        valid_json = _make_valid_json(2)

        async def mock_llm(system: str, user: str) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "This is not JSON"
            return valid_json

        inp = _make_input()
        result = await generate_equipment_narrative(inp, mock_llm)

        assert result.source == "llm_retry"
        assert result.attempts == 2
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_after_too_few_recs(self):
        call_count = 0

        async def mock_llm(system: str, user: str) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_valid_json(1)  # Too few — only 1 rec
            return _make_valid_json(3)

        inp = _make_input()
        result = await generate_equipment_narrative(inp, mock_llm)

        assert result.source == "llm_retry"
        assert result.attempts == 2

    @pytest.mark.asyncio
    async def test_retry_prompt_contains_reinforcement(self):
        """Retry system prompt must contain reinforcement wording."""
        prompts_received: list[str] = []

        async def mock_llm(system: str, user: str) -> str:
            prompts_received.append(system)
            if len(prompts_received) == 1:
                return "not json"
            return _make_valid_json(2)

        inp = _make_input()
        await generate_equipment_narrative(inp, mock_llm)

        assert len(prompts_received) == 2
        assert "ATENÇÃO" in prompts_received[1]


# ---------------------------------------------------------------------------
# generate_equipment_narrative — fallback
# ---------------------------------------------------------------------------


class TestFallback:
    @pytest.mark.asyncio
    async def test_fallback_after_two_failures(self):
        async def mock_llm(system: str, user: str) -> str:
            return "never valid"

        inp = _make_input()
        result = await generate_equipment_narrative(inp, mock_llm)

        assert result.source == "fallback"
        assert result.attempts == 3
        assert isinstance(result.output, EquipmentLLMOutput)
        assert len(result.output.recomendacoes_tecnicas) >= 2

    @pytest.mark.asyncio
    async def test_fallback_after_exceptions(self):
        async def mock_llm(system: str, user: str) -> str:
            raise RuntimeError("API down")

        inp = _make_input()
        result = await generate_equipment_narrative(inp, mock_llm)

        assert result.source == "fallback"
        assert isinstance(result.output, EquipmentLLMOutput)

    @pytest.mark.asyncio
    async def test_fallback_uses_input_medidas(self):
        async def mock_llm(system: str, user: str) -> str:
            raise RuntimeError("timeout")

        inp = _make_input(medidas_a_implementar=["Ação A", "Ação B"])
        result = await generate_equipment_narrative(inp, mock_llm)

        assert result.source == "fallback"
        texts = [r.texto for r in result.output.recomendacoes_tecnicas]
        assert "Ação A" in texts
        assert "Ação B" in texts


# ---------------------------------------------------------------------------
# generate_all_equipment_narratives — batch
# ---------------------------------------------------------------------------


class TestBatchGeneration:
    @pytest.mark.asyncio
    async def test_empty_list(self):
        async def mock_llm(system: str, user: str) -> str:
            return _make_valid_json(2)

        results = await generate_all_equipment_narratives([], mock_llm)
        assert results == []

    @pytest.mark.asyncio
    async def test_multiple_equipments_sequential(self):
        call_count = 0

        async def mock_llm(system: str, user: str) -> str:
            nonlocal call_count
            call_count += 1
            return _make_valid_json(2)

        inputs = [_make_input(f"Equip-{i}") for i in range(3)]
        results = await generate_all_equipment_narratives(
            inputs, mock_llm, max_concurrency=1,
        )

        assert len(results) == 3
        assert call_count == 3
        assert all(r.source == "llm" for r in results)

    @pytest.mark.asyncio
    async def test_progress_callback(self):
        progress_calls: list[tuple[int, int]] = []

        async def mock_llm(system: str, user: str) -> str:
            return _make_valid_json(2)

        async def on_progress(completed: int, total: int) -> None:
            progress_calls.append((completed, total))

        inputs = [_make_input(f"Equip-{i}") for i in range(3)]
        await generate_all_equipment_narratives(
            inputs, mock_llm, max_concurrency=1, on_progress=on_progress,
        )

        assert len(progress_calls) == 3
        assert progress_calls[-1] == (3, 3)

    @pytest.mark.asyncio
    async def test_concurrent_execution(self):
        """Concurrent mode should also produce correct results."""

        async def mock_llm(system: str, user: str) -> str:
            return _make_valid_json(2)

        inputs = [_make_input(f"Equip-{i}") for i in range(5)]
        results = await generate_all_equipment_narratives(
            inputs, mock_llm, max_concurrency=3,
        )

        assert len(results) == 5
        assert all(r.source == "llm" for r in results)

    @pytest.mark.asyncio
    async def test_mixed_success_and_fallback(self):
        call_count = 0

        async def mock_llm(system: str, user: str) -> str:
            nonlocal call_count
            call_count += 1
            # Second equipment always fails
            if "Equip-1" in user:
                raise RuntimeError("fail")
            return _make_valid_json(2)

        inputs = [_make_input(f"Equip-{i}") for i in range(3)]
        results = await generate_all_equipment_narratives(
            inputs, mock_llm, max_concurrency=1,
        )

        assert len(results) == 3
        # Equip-0 and Equip-2 should be llm, Equip-1 should be fallback
        assert results[0].source == "llm"
        assert results[1].source == "fallback"
        assert results[2].source == "llm"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_never_raises_exception(self):
        """generate_equipment_narrative must NEVER raise — always returns result."""
        async def mock_llm(system: str, user: str) -> str:
            raise Exception("catastrophic failure")

        inp = _make_input()
        result = await generate_equipment_narrative(inp, mock_llm)
        assert result.output is not None  # Fallback produced

    @pytest.mark.asyncio
    async def test_result_preserves_equipment_name(self):
        async def mock_llm(system: str, user: str) -> str:
            return _make_valid_json(2)

        inp = _make_input("Moinho MO-03")
        result = await generate_equipment_narrative(inp, mock_llm)
        assert result.equipment_name == "Moinho MO-03"
