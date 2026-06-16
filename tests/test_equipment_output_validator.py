"""Testes unitários — equipment_output_validator.

Cobre as regras OV-01 … OV-14, limites §5.2, fallback §4.3.
"""

from __future__ import annotations

import json

import pytest

from app.domain.entities import (
    EquipmentLLMInput,
    EquipmentLLMOutput,
    RiskClassification,
)
from app.domain.services.equipment_output_validator import (
    ValidationResult,
    build_fallback,
    validate_llm_output,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_input(**overrides) -> EquipmentLLMInput:
    """Cria um EquipmentLLMInput padrão para testes."""
    defaults = {
        "equipment_name": "Elevador EC-01",
        "descricao_da_operacao": "Transporte de grãos",
        "identificacao_dos_perigos": ["Poeira combustível", "Atrito excessivo"],
        "causas_possiveis": ["Falha aspiração"],
        "consequencias_potenciais": ["Explosão"],
        "classificacao_do_risco": RiskClassification(
            categoria_severidade="Alta",
            categoria_probabilidade="Alto",
            classificacao_risco="Alto",
        ),
        "medidas_preventivas_existentes": ["Sensor instalado"],
        "medidas_a_implementar": [
            "Instalar supressão",
            "Revisar ventilação",
            "Manutenção preditiva",
        ],
        "normas_aplicaveis": ["NFPA 652:2022", "NR-10"],
    }
    defaults.update(overrides)
    return EquipmentLLMInput(**defaults)


def _make_valid_output(n: int = 3) -> dict:
    """Cria um dict de output LLM válido com n recomendações."""
    return {
        "recomendacoes_tecnicas": [
            {
                "numero": i,
                "texto": f"Recomendação técnica detalhada número {i} com texto suficiente para validação.",
                "norma_referencia": "NFPA 652:2022, seção 8.2",
                "tipo": "boa_pratica",
                "trecho_normativo": None,
            }
            for i in range(1, n + 1)
        ],
        "justificativas_tecnicas": [
            {
                "numero": i,
                "texto": (
                    f"Justificativa técnica detalhada número {i}. "
                    "A classificação de risco Alto com severidade Alta demanda ação corretiva imediata."
                ),
            }
            for i in range(1, n + 1)
        ],
    }


# ---------------------------------------------------------------------------
# OV-01: JSON parsing
# ---------------------------------------------------------------------------


class TestOV01JsonParsing:
    def test_valid_json(self):
        inp = _make_input()
        raw = json.dumps(_make_valid_output())
        result = validate_llm_output(raw, inp)
        assert result.success is True
        assert result.output is not None

    def test_invalid_json(self):
        inp = _make_input()
        result = validate_llm_output("not json at all", inp)
        assert result.success is False
        assert "OV-01" in result.reason
        assert result.needs_retry is True

    def test_json_with_markdown_wrapper(self):
        inp = _make_input()
        raw = "```json\n" + json.dumps(_make_valid_output()) + "\n```"
        result = validate_llm_output(raw, inp)
        assert result.success is True

    def test_empty_string(self):
        inp = _make_input()
        result = validate_llm_output("", inp)
        assert result.success is False
        assert result.needs_retry is True


# ---------------------------------------------------------------------------
# OV-02: required keys
# ---------------------------------------------------------------------------


class TestOV02RequiredKeys:
    def test_missing_recomendacoes(self):
        inp = _make_input()
        data = {"justificativas_tecnicas": []}
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is False
        assert "OV-02" in result.reason

    def test_missing_justificativas(self):
        inp = _make_input()
        data = {"recomendacoes_tecnicas": []}
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is False
        assert "OV-02" in result.reason

    def test_missing_both(self):
        inp = _make_input()
        result = validate_llm_output(json.dumps({}), inp)
        assert result.success is False

    def test_extra_keys_stripped(self):
        """Extra keys are silently stripped (OV-02)."""
        inp = _make_input()
        data = _make_valid_output()
        data["extra_key"] = "should be ignored"
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is True


# ---------------------------------------------------------------------------
# OV-03 / OV-04: arrays of objects
# ---------------------------------------------------------------------------


class TestOV0304ArrayStructure:
    def test_recs_not_array(self):
        inp = _make_input()
        data = {"recomendacoes_tecnicas": "oops", "justificativas_tecnicas": []}
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is False
        assert "OV-03" in result.reason

    def test_justs_not_array(self):
        inp = _make_input()
        data = {"recomendacoes_tecnicas": [], "justificativas_tecnicas": "oops"}
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is False
        assert "OV-04" in result.reason

    def test_recs_contains_non_dict(self):
        inp = _make_input()
        data = {"recomendacoes_tecnicas": ["string item"], "justificativas_tecnicas": []}
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is False


# ---------------------------------------------------------------------------
# OV-05: equalize lengths
# ---------------------------------------------------------------------------


class TestOV05EqualizeLengths:
    def test_recs_longer_than_justs(self):
        inp = _make_input()
        data = _make_valid_output(4)
        data["justificativas_tecnicas"] = data["justificativas_tecnicas"][:3]
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is True
        assert len(result.output.recomendacoes_tecnicas) == 3

    def test_justs_longer_than_recs(self):
        inp = _make_input()
        data = _make_valid_output(4)
        data["recomendacoes_tecnicas"] = data["recomendacoes_tecnicas"][:2]
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is True
        assert len(result.output.justificativas_tecnicas) == 2


# ---------------------------------------------------------------------------
# OV-06 / OV-14: minimum 2 recommendations
# ---------------------------------------------------------------------------


class TestOV06Minimum:
    def test_zero_recs(self):
        inp = _make_input()
        data = {"recomendacoes_tecnicas": [], "justificativas_tecnicas": []}
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is False
        assert "OV-06" in result.reason or "OV-14" in result.reason

    def test_one_rec(self):
        inp = _make_input()
        data = _make_valid_output(1)
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is False
        assert result.needs_retry is True

    def test_two_recs_ok(self):
        inp = _make_input()
        data = _make_valid_output(2)
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is True
        assert len(result.output.recomendacoes_tecnicas) == 2


# ---------------------------------------------------------------------------
# OV-07: max 10 recommendations
# ---------------------------------------------------------------------------


class TestOV07Maximum:
    def test_truncates_to_10(self):
        inp = _make_input()
        data = _make_valid_output(12)
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is True
        assert len(result.output.recomendacoes_tecnicas) == 10


# ---------------------------------------------------------------------------
# OV-08 / OV-09: sequential renumbering
# ---------------------------------------------------------------------------


class TestOV0809Renumber:
    def test_wrong_numbers_renumbered(self):
        inp = _make_input()
        data = _make_valid_output(3)
        data["recomendacoes_tecnicas"][0]["numero"] = 10
        data["recomendacoes_tecnicas"][1]["numero"] = 20
        data["recomendacoes_tecnicas"][2]["numero"] = 30
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is True
        for idx, rec in enumerate(result.output.recomendacoes_tecnicas, 1):
            assert rec.numero == idx
        for idx, jst in enumerate(result.output.justificativas_tecnicas, 1):
            assert jst.numero == idx


# ---------------------------------------------------------------------------
# OV-10 / OV-11: empty text removal
# ---------------------------------------------------------------------------


class TestOV1011EmptyText:
    def test_empty_rec_text_removed(self):
        inp = _make_input()
        data = _make_valid_output(3)
        data["recomendacoes_tecnicas"][1]["texto"] = ""
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is True
        assert len(result.output.recomendacoes_tecnicas) == 2

    def test_empty_just_text_removed(self):
        inp = _make_input()
        data = _make_valid_output(3)
        data["justificativas_tecnicas"][0]["texto"] = "   "
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is True
        assert len(result.output.recomendacoes_tecnicas) == 2

    def test_all_empty_triggers_retry(self):
        inp = _make_input()
        data = _make_valid_output(2)
        data["recomendacoes_tecnicas"][0]["texto"] = ""
        data["recomendacoes_tecnicas"][1]["texto"] = ""
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is False


# ---------------------------------------------------------------------------
# OV-12: norma_referencia fallback
# ---------------------------------------------------------------------------


class TestOV12NormaFallback:
    def test_empty_norma_uses_first_input_norm(self):
        inp = _make_input()
        data = _make_valid_output(2)
        data["recomendacoes_tecnicas"][0]["norma_referencia"] = ""
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is True
        assert result.output.recomendacoes_tecnicas[0].norma_referencia == "NFPA 652:2022"

    def test_short_norma_uses_fallback(self):
        inp = _make_input()
        data = _make_valid_output(2)
        data["recomendacoes_tecnicas"][1]["norma_referencia"] = "AB"
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is True
        assert result.output.recomendacoes_tecnicas[1].norma_referencia == "NFPA 652:2022"


# ---------------------------------------------------------------------------
# OV-13: duplicate removal
# ---------------------------------------------------------------------------


class TestOV13Duplicates:
    def test_exact_duplicate_removed(self):
        inp = _make_input()
        data = _make_valid_output(3)
        data["recomendacoes_tecnicas"][2]["texto"] = data["recomendacoes_tecnicas"][0]["texto"]
        data["justificativas_tecnicas"][2]["texto"] = "Different justification."
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is True
        assert len(result.output.recomendacoes_tecnicas) == 2

    def test_case_insensitive_dedup(self):
        inp = _make_input()
        data = _make_valid_output(3)
        data["recomendacoes_tecnicas"][1]["texto"] = data["recomendacoes_tecnicas"][0]["texto"].upper()
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is True
        assert len(result.output.recomendacoes_tecnicas) == 2


# ---------------------------------------------------------------------------
# §5.2: length limits
# ---------------------------------------------------------------------------


class TestLengthLimits:
    def test_rec_text_truncated(self):
        inp = _make_input()
        data = _make_valid_output(2)
        data["recomendacoes_tecnicas"][0]["texto"] = "X" * 600
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is True
        assert len(result.output.recomendacoes_tecnicas[0].texto) <= 500

    def test_norma_truncated(self):
        inp = _make_input()
        data = _make_valid_output(2)
        data["recomendacoes_tecnicas"][0]["norma_referencia"] = "N" * 200
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is True
        assert len(result.output.recomendacoes_tecnicas[0].norma_referencia) <= 150

    def test_just_text_truncated(self):
        inp = _make_input()
        data = _make_valid_output(2)
        data["justificativas_tecnicas"][0]["texto"] = "J" * 1200
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is True
        assert len(result.output.justificativas_tecnicas[0].texto) <= 1000


# ---------------------------------------------------------------------------
# Fallback (§4.3)
# ---------------------------------------------------------------------------


class TestFallback:
    def test_fallback_uses_medidas_a_implementar(self):
        inp = _make_input(
            medidas_a_implementar=["Instalar X", "Revisar Y", "Adequar Z"],
        )
        output = build_fallback(inp)
        assert isinstance(output, EquipmentLLMOutput)
        assert len(output.recomendacoes_tecnicas) == 3
        assert len(output.justificativas_tecnicas) == 3
        assert output.recomendacoes_tecnicas[0].texto == "Instalar X"
        assert output.recomendacoes_tecnicas[0].norma_referencia == "NFPA 652:2022"

    def test_fallback_keeps_recommendations_and_justifications_one_to_one(self):
        inp = _make_input(
            medidas_a_implementar=["Instalar X", "Revisar Y", "Adequar Z"],
        )
        output = build_fallback(inp)

        assert len(output.recomendacoes_tecnicas) == len(
            output.justificativas_tecnicas
        )
        for rec, just in zip(
            output.recomendacoes_tecnicas,
            output.justificativas_tecnicas,
        ):
            assert just.numero == rec.numero
            assert f"nº {rec.numero}" in just.texto
            assert rec.norma_referencia in just.texto

    def test_fallback_empty_medidas_gets_generic(self):
        inp = _make_input(medidas_a_implementar=[])
        output = build_fallback(inp)
        assert len(output.recomendacoes_tecnicas) >= 2
        assert "avaliação" in output.recomendacoes_tecnicas[0].texto.lower()

    def test_fallback_single_medida_padded_to_2(self):
        inp = _make_input(medidas_a_implementar=["Única medida"])
        output = build_fallback(inp)
        assert len(output.recomendacoes_tecnicas) == 2

    def test_fallback_justificativa_has_equip_info(self):
        inp = _make_input()
        output = build_fallback(inp)
        just = output.justificativas_tecnicas[0].texto
        assert "Elevador EC-01" in just
        assert "Alta" in just

    def test_fallback_numbering_sequential(self):
        inp = _make_input(
            medidas_a_implementar=["A", "B", "C"],
        )
        output = build_fallback(inp)
        for idx, rec in enumerate(output.recomendacoes_tecnicas, 1):
            assert rec.numero == idx
        for idx, jst in enumerate(output.justificativas_tecnicas, 1):
            assert jst.numero == idx

    def test_fallback_tipo_is_boa_pratica(self):
        """Fallback must always produce tipo='boa_pratica'."""
        inp = _make_input()
        output = build_fallback(inp)
        for rec in output.recomendacoes_tecnicas:
            assert rec.tipo == "boa_pratica"
            assert rec.trecho_normativo is None


# ---------------------------------------------------------------------------
# Tipo / trecho_normativo classification
# ---------------------------------------------------------------------------


class TestTipoTrechoClassification:
    def test_normativa_with_trecho_preserved(self):
        """tipo='normativa' + trecho present → kept as normativa."""
        inp = _make_input()
        data = _make_valid_output(2)
        data["recomendacoes_tecnicas"][0]["tipo"] = "normativa"
        data["recomendacoes_tecnicas"][0]["trecho_normativo"] = "Trecho literal da norma NFPA 652."
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is True
        assert result.output.recomendacoes_tecnicas[0].tipo == "normativa"
        assert result.output.recomendacoes_tecnicas[0].trecho_normativo == "Trecho literal da norma NFPA 652."

    def test_normativa_without_trecho_reclassified(self):
        """tipo='normativa' but no trecho → reclassified to boa_pratica."""
        inp = _make_input()
        data = _make_valid_output(2)
        data["recomendacoes_tecnicas"][0]["tipo"] = "normativa"
        data["recomendacoes_tecnicas"][0]["trecho_normativo"] = None
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is True
        assert result.output.recomendacoes_tecnicas[0].tipo == "boa_pratica"
        assert result.output.recomendacoes_tecnicas[0].trecho_normativo is None

    def test_missing_tipo_with_trecho_infers_normativa(self):
        """No tipo field but trecho present → inferred as normativa."""
        inp = _make_input()
        data = _make_valid_output(2)
        # Remove tipo, add trecho
        data["recomendacoes_tecnicas"][0].pop("tipo", None)
        data["recomendacoes_tecnicas"][0]["trecho_normativo"] = "Algum trecho normativo relevante."
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is True
        assert result.output.recomendacoes_tecnicas[0].tipo == "normativa"

    def test_missing_tipo_without_trecho_defaults_boa_pratica(self):
        """No tipo, no trecho → defaults to boa_pratica."""
        inp = _make_input()
        data = _make_valid_output(2)
        data["recomendacoes_tecnicas"][0].pop("tipo", None)
        data["recomendacoes_tecnicas"][0].pop("trecho_normativo", None)
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is True
        assert result.output.recomendacoes_tecnicas[0].tipo == "boa_pratica"

    def test_boa_pratica_tipo_preserved(self):
        """Explicit boa_pratica is preserved."""
        inp = _make_input()
        data = _make_valid_output(2)
        data["recomendacoes_tecnicas"][0]["tipo"] = "boa_pratica"
        data["recomendacoes_tecnicas"][0]["trecho_normativo"] = None
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is True
        assert result.output.recomendacoes_tecnicas[0].tipo == "boa_pratica"


# ---------------------------------------------------------------------------
# End-to-end happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_valid_output_accepted(self):
        inp = _make_input()
        data = _make_valid_output(5)
        result = validate_llm_output(json.dumps(data), inp)
        assert result.success is True
        assert len(result.output.recomendacoes_tecnicas) == 5
        assert len(result.output.justificativas_tecnicas) == 5
        # Numbers must be sequential
        for i, rec in enumerate(result.output.recomendacoes_tecnicas, 1):
            assert rec.numero == i
