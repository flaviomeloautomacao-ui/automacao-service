"""Testes — build_equipment_user_prompt.

Cobre:
  1. Prompt contém todos os blocos obrigatórios do contrato §8.
  2. Prompt é determinístico (mesma entrada → mesma saída).
  3. Listas vazias usam mensagem de fallback.
  4. Blocos opcionais (normative_excerpts, literature_excerpts) são
     incluídos somente quando fornecidos.
  5. Nenhum dado de outro equipamento vaza no prompt.
  6. Formato JSON solicitado está presente.
"""

from __future__ import annotations

from app.domain.entities import EquipmentLLMInput, NormativeExcerpt, LiteratureExcerpt, RiskClassification
from app.domain.services.equipment_user_prompt import (
    _format_bullet_list,
    build_equipment_user_prompt,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_NORMAS = [
    "NFPA 652:2022 — Standard on the Fundamentals of Combustible Dust",
    "ABNT NBR IEC 60079-10-2 — Classificação de áreas",
]


def _make_input(**overrides: object) -> EquipmentLLMInput:
    defaults: dict[str, object] = {
        "equipment_name": "Elevador de Canecas EC-01",
        "descricao_da_operacao": "Transporte vertical de grãos",
        "identificacao_dos_perigos": ["Acúmulo de poeira combustível"],
        "causas_possiveis": ["Falha no sistema de aspiração"],
        "consequencias_potenciais": ["Explosão primária"],
        "classificacao_do_risco": RiskClassification(
            categoria_severidade="Alta",
            categoria_probabilidade="Alto",
            classificacao_risco="Alto",
        ),
        "medidas_preventivas_existentes": ["Sistema de aspiração parcial"],
        "medidas_a_implementar": ["Instalar supressão de explosão"],
        "normas_aplicaveis": _NORMAS,
    }
    defaults.update(overrides)
    return EquipmentLLMInput(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 1. Blocos obrigatórios presentes
# ---------------------------------------------------------------------------


class TestRequiredBlocks:

    def test_contains_equipment_header(self) -> None:
        prompt = build_equipment_user_prompt(_make_input())
        assert "### Equipamento ###" in prompt
        assert "Elevador de Canecas EC-01" in prompt

    def test_contains_descricao(self) -> None:
        prompt = build_equipment_user_prompt(_make_input())
        assert "Transporte vertical de grãos" in prompt

    def test_contains_perigos(self) -> None:
        prompt = build_equipment_user_prompt(_make_input())
        assert "### Perigos Identificados ###" in prompt
        assert "• Acúmulo de poeira combustível" in prompt

    def test_contains_causas(self) -> None:
        prompt = build_equipment_user_prompt(_make_input())
        assert "### Causas Possíveis ###" in prompt
        assert "• Falha no sistema de aspiração" in prompt

    def test_contains_consequencias(self) -> None:
        prompt = build_equipment_user_prompt(_make_input())
        assert "### Consequências Potenciais ###" in prompt
        assert "• Explosão primária" in prompt

    def test_contains_risk_classification(self) -> None:
        prompt = build_equipment_user_prompt(_make_input())
        assert "### Classificação do Risco" in prompt
        assert "Categoria de Severidade: Alta" in prompt
        assert "Categoria da Probabilidade: Alto" in prompt
        assert "Classificação do Risco: Alto" in prompt

    def test_contains_medidas_existentes(self) -> None:
        prompt = build_equipment_user_prompt(_make_input())
        assert "### Medidas Preventivas Existentes ###" in prompt
        assert "• Sistema de aspiração parcial" in prompt

    def test_contains_medidas_implementar(self) -> None:
        prompt = build_equipment_user_prompt(_make_input())
        assert "### Medidas a Implementar" in prompt
        assert "• Instalar supressão de explosão" in prompt

    def test_contains_normas(self) -> None:
        prompt = build_equipment_user_prompt(_make_input())
        assert "### Normas Aplicáveis ###" in prompt
        assert "• NFPA 652:2022" in prompt

    def test_contains_json_format(self) -> None:
        prompt = build_equipment_user_prompt(_make_input())
        assert '"recomendacoes_tecnicas"' in prompt
        assert '"justificativas_tecnicas"' in prompt
        assert '"numero"' in prompt
        assert '"norma_referencia"' in prompt

    def test_requests_analysis_instruction(self) -> None:
        prompt = build_equipment_user_prompt(_make_input())
        assert "Analise SOMENTE este equipamento" in prompt


# ---------------------------------------------------------------------------
# 2. Determinismo
# ---------------------------------------------------------------------------


class TestDeterminism:

    def test_same_input_same_output(self) -> None:
        inp = _make_input()
        assert build_equipment_user_prompt(inp) == build_equipment_user_prompt(inp)

    def test_different_equipment_different_output(self) -> None:
        a = _make_input(equipment_name="EC-01")
        b = _make_input(equipment_name="EC-02")
        assert build_equipment_user_prompt(a) != build_equipment_user_prompt(b)


# ---------------------------------------------------------------------------
# 3. Listas vazias — fallback
# ---------------------------------------------------------------------------


class TestEmptyListFallback:

    def test_empty_medidas_existentes(self) -> None:
        inp = _make_input(medidas_preventivas_existentes=[])
        prompt = build_equipment_user_prompt(inp)
        assert "Nenhuma medida existente informada." in prompt

    def test_empty_medidas_implementar(self) -> None:
        inp = _make_input(medidas_a_implementar=[])
        prompt = build_equipment_user_prompt(inp)
        assert "Nenhuma medida sugerida." in prompt


# ---------------------------------------------------------------------------
# 4. Blocos opcionais
# ---------------------------------------------------------------------------


class TestOptionalBlocks:

    def test_no_optional_blocks_by_default(self) -> None:
        prompt = build_equipment_user_prompt(_make_input())
        assert "### Trechos Normativos" not in prompt
        assert "### Trechos de Literatura" not in prompt

    def test_normative_excerpts_included(self) -> None:
        prompt = build_equipment_user_prompt(
            _make_input(),
            normative_excerpts=["NFPA 652 §8.2.1: Sistemas de captação devem..."],
        )
        assert "### Trechos Normativos Relevantes ###" in prompt
        assert "[1] NFPA 652 §8.2.1: Sistemas de captação devem..." in prompt

    def test_literature_excerpts_included(self) -> None:
        prompt = build_equipment_user_prompt(
            _make_input(),
            literature_excerpts=[
                "Eckhoff (2003): A MEC de poeira de soja...",
                "Amyotte (2013): Medidas de proteção...",
            ],
        )
        assert "### Trechos de Literatura Técnica ###" in prompt
        assert "[1] Eckhoff (2003)" in prompt
        assert "[2] Amyotte (2013)" in prompt

    def test_both_optional_blocks(self) -> None:
        prompt = build_equipment_user_prompt(
            _make_input(),
            normative_excerpts=["Norma X"],
            literature_excerpts=["Artigo Y"],
        )
        assert "### Trechos Normativos Relevantes ###" in prompt
        assert "### Trechos de Literatura Técnica ###" in prompt


# ---------------------------------------------------------------------------
# 5. Isolamento — sem contaminação cruzada
# ---------------------------------------------------------------------------


class TestIsolation:

    def test_only_provided_equipment_data(self) -> None:
        prompt = build_equipment_user_prompt(
            _make_input(equipment_name="Peneira Vibratória PV-03")
        )
        assert "Peneira Vibratória PV-03" in prompt
        assert "EC-01" not in prompt

    def test_multiple_perigos_all_present(self) -> None:
        inp = _make_input(
            identificacao_dos_perigos=["Perigo A", "Perigo B", "Perigo C"]
        )
        prompt = build_equipment_user_prompt(inp)
        assert "• Perigo A" in prompt
        assert "• Perigo B" in prompt
        assert "• Perigo C" in prompt


# ---------------------------------------------------------------------------
# 6. Helper unitário
# ---------------------------------------------------------------------------


class TestFormatBulletList:

    def test_non_empty(self) -> None:
        assert _format_bullet_list(["A", "B"]) == "• A\n• B"

    def test_empty_default_msg(self) -> None:
        assert _format_bullet_list([]) == "Nenhum item informado."

    def test_empty_custom_msg(self) -> None:
        assert _format_bullet_list([], "Vazio.") == "Vazio."


# ---------------------------------------------------------------------------
# 7. Model-level excerpt fields (normative_context / literature_context)
# ---------------------------------------------------------------------------


class TestModelLevelExcerpts:
    """Excerpts populated on the EquipmentLLMInput model itself."""

    def test_normative_context_on_model_appears_in_prompt(self) -> None:
        excerpts = [
            NormativeExcerpt(source="NFPA 652:2022", section="8.2.1", text="Sistemas de captação devem operar..."),
        ]
        inp = _make_input(normative_context=excerpts)
        prompt = build_equipment_user_prompt(inp)
        assert "### Trechos Normativos Relevantes ###" in prompt
        assert "NFPA 652:2022" in prompt
        assert "seção 8.2.1" in prompt
        assert "Sistemas de captação devem operar..." in prompt

    def test_literature_context_on_model_appears_in_prompt(self) -> None:
        excerpts = [
            LiteratureExcerpt(source="Eckhoff (2003)", text="A MEC típica para grãos..."),
        ]
        inp = _make_input(literature_context=excerpts)
        prompt = build_equipment_user_prompt(inp)
        assert "### Trechos de Literatura Técnica ###" in prompt
        assert "Eckhoff (2003)" in prompt
        assert "A MEC típica para grãos..." in prompt

    def test_normative_context_without_section(self) -> None:
        excerpts = [
            NormativeExcerpt(source="ABNT NBR 16577", text="Requisitos gerais..."),
        ]
        inp = _make_input(normative_context=excerpts)
        prompt = build_equipment_user_prompt(inp)
        assert "ABNT NBR 16577: Requisitos gerais..." in prompt
        assert "seção" not in prompt.split("ABNT NBR 16577")[1].split("\n")[0]

    def test_model_and_kwarg_excerpts_merged(self) -> None:
        """Model excerpts appear first, then keyword arg excerpts."""
        model_exc = [
            NormativeExcerpt(source="NFPA 652", section="4.1", text="Texto modelo"),
        ]
        inp = _make_input(normative_context=model_exc)
        prompt = build_equipment_user_prompt(
            inp, normative_excerpts=["Texto kwarg extra"],
        )
        assert "[1] NFPA 652, seção 4.1: Texto modelo" in prompt
        assert "[2] Texto kwarg extra" in prompt

    def test_empty_model_excerpts_no_block(self) -> None:
        inp = _make_input(normative_context=[], literature_context=[])
        prompt = build_equipment_user_prompt(inp)
        assert "### Trechos Normativos" not in prompt
        assert "### Trechos de Literatura" not in prompt

    def test_multiple_model_excerpts_numbered(self) -> None:
        excerpts = [
            NormativeExcerpt(source="NFPA 652", text="Trecho A"),
            NormativeExcerpt(source="NFPA 654", section="6.3", text="Trecho B"),
        ]
        inp = _make_input(normative_context=excerpts)
        prompt = build_equipment_user_prompt(inp)
        assert "[1] NFPA 652: Trecho A" in prompt
        assert "[2] NFPA 654, seção 6.3: Trecho B" in prompt
