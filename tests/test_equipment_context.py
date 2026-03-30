"""Testes — EquipmentContextBuilder (build_equipment_contexts).

Cobre:
  1. Agrupamento por nome de equipamento.
  2. Severidade e risco consolidados para o valor mais alto.
  3. Deduplicação de campos multivalorados.
  4. Ordem de saída preserva primeira aparição.
  5. Campo ``index`` sequencial a partir de 1.
  6. Tratamento de linhas com equipamento vazio.
  7. Tratamento de equipamento sem perigos → ignorado.
  8. Placeholders quando causas/consequências ausentes.
  9. Descrição mais longa é escolhida.
 10. rows_dicts vazio → ValueError.
"""

from __future__ import annotations

import pytest

from app.domain.entities import EquipmentContext, RiskClassification
from app.domain.services.equipment_context_builder import (
    _highest_risk,
    _highest_severity,
    _split_field,
    build_equipment_contexts,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_row(**overrides: object) -> dict:
    """Cria um dict de row mínimo válido, aceitando sobrescritas."""
    defaults: dict[str, object] = {
        "equipamento": "Prensa Hidráulica",
        "descricao_equipamento": "Prensa para conformação de chapas",
        "perigo": "Esmagamento de membros",
        "causas": "Falha na proteção",
        "consequencias": "Amputação",
        "categoria_severidade": "Alta",
        "categoria_risco": "Alto",
        "categoria_probabilidade": "Alto",
        "classificacao_risco": "Alto",
        "medidas_existentes": "Barreira física",
        "medidas_implementar": "Sensor de presença",
        "observacoes": None,
        "riscos": "Risco mecânico",
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# 1. Agrupamento básico — equipamento único, uma linha
# ---------------------------------------------------------------------------

class TestSingleEquipmentSingleRow:
    """Cenário mais simples: uma linha ↦ um EquipmentContext."""

    def test_basic_fields(self) -> None:
        rows = [_make_row()]
        contexts = build_equipment_contexts(rows)

        assert len(contexts) == 1
        ctx = contexts[0]
        assert ctx.index == 1
        assert ctx.equipment_name == "Prensa Hidráulica"
        assert ctx.descricao_da_operacao == "Prensa para conformação de chapas"
        assert ctx.identificacao_dos_perigos == ["Esmagamento de membros"]
        assert ctx.causas_possiveis == ["Falha na proteção"]
        assert ctx.consequencias_potenciais == ["Amputação"]
        assert ctx.classificacao_do_risco == RiskClassification(
            categoria_severidade="Alta",
            categoria_probabilidade="Alto",
            classificacao_risco="Alto",
        )
        assert ctx.medidas_preventivas_existentes == ["Barreira física"]
        assert ctx.medidas_a_implementar == ["Sensor de presença"]
        assert ctx.row_count == 1

    def test_frozen(self) -> None:
        """EquipmentContext deve ser imutável."""
        ctx = build_equipment_contexts([_make_row()])[0]
        with pytest.raises(Exception):  # ValidationError
            ctx.equipment_name = "Outro"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. Agrupamento — múltiplas linhas, mesmo equipamento
# ---------------------------------------------------------------------------

class TestMultipleRowsSameEquipment:
    """Linhas do mesmo equipamento devem fundir em um único contexto."""

    def test_deduplication(self) -> None:
        rows = [
            _make_row(perigo="Esmagamento"),
            _make_row(perigo="Esmagamento"),  # duplicate
            _make_row(perigo="Corte"),
        ]
        contexts = build_equipment_contexts(rows)
        assert len(contexts) == 1
        assert contexts[0].identificacao_dos_perigos == ["Esmagamento", "Corte"]
        assert contexts[0].row_count == 3

    def test_multivalue_split(self) -> None:
        """Campos com ';' ou newline são splitados e deduplicados."""
        rows = [
            _make_row(causas="Falha mecânica; Falta de manutenção"),
            _make_row(causas="Falha mecânica; Erro humano"),
        ]
        contexts = build_equipment_contexts(rows)
        assert contexts[0].causas_possiveis == [
            "Falha mecânica",
            "Falta de manutenção",
            "Erro humano",
        ]

    def test_description_longest(self) -> None:
        """Descrição mais longa entre as linhas é selecionada."""
        rows = [
            _make_row(descricao_equipamento="Curta"),
            _make_row(descricao_equipamento="Descrição muito mais longa e detalhada"),
        ]
        contexts = build_equipment_contexts(rows)
        assert contexts[0].descricao_da_operacao == "Descrição muito mais longa e detalhada"


# ---------------------------------------------------------------------------
# 3. Severidade e risco — consolidação para o mais alto
# ---------------------------------------------------------------------------

class TestSeverityRiskConsolidation:
    """Severidade e risco devem ser consolidados para o valor mais alto."""

    def test_severity_highest_chosen(self) -> None:
        rows = [
            _make_row(categoria_severidade="Baixa"),
            _make_row(categoria_severidade="Muito Alta"),
            _make_row(categoria_severidade="Média"),
        ]
        contexts = build_equipment_contexts(rows)
        assert contexts[0].classificacao_do_risco.categoria_severidade == "Muito Alta"

    def test_risk_highest_chosen(self) -> None:
        rows = [
            _make_row(categoria_probabilidade="Baixo", classificacao_risco="Baixo"),
            _make_row(categoria_probabilidade="Muito Alto", classificacao_risco="Muito Alto"),
            _make_row(categoria_probabilidade="Médio", classificacao_risco="Médio"),
        ]
        contexts = build_equipment_contexts(rows)
        assert contexts[0].classificacao_do_risco.categoria_probabilidade == "Muito Alto"
        assert contexts[0].classificacao_do_risco.classificacao_risco == "Muito Alto"

    def test_severity_media_para_alta(self) -> None:
        """'Média para Alta' deve ser inferior a 'Alta'."""
        rows = [
            _make_row(categoria_severidade="Média para Alta"),
            _make_row(categoria_severidade="Alta"),
        ]
        contexts = build_equipment_contexts(rows)
        assert contexts[0].classificacao_do_risco.categoria_severidade == "Alta"

    def test_unknown_severity_no_overwrite(self) -> None:
        """Valor desconhecido não sobrescreve um valor conhecido."""
        rows = [
            _make_row(categoria_severidade="Alta"),
            _make_row(categoria_severidade="XPTO Desconhecida"),
        ]
        contexts = build_equipment_contexts(rows)
        assert contexts[0].classificacao_do_risco.categoria_severidade == "Alta"


# ---------------------------------------------------------------------------
# 4. Múltiplos equipamentos — ordem preservada
# ---------------------------------------------------------------------------

class TestMultipleEquipments:
    """Vários equipamentos mantêm a ordem de primeira aparição."""

    def test_order_preserved(self) -> None:
        rows = [
            _make_row(equipamento="Torno"),
            _make_row(equipamento="Prensa"),
            _make_row(equipamento="Furadeira"),
        ]
        contexts = build_equipment_contexts(rows)
        assert len(contexts) == 3
        assert [c.equipment_name for c in contexts] == ["Torno", "Prensa", "Furadeira"]
        assert [c.index for c in contexts] == [1, 2, 3]

    def test_case_insensitive_grouping(self) -> None:
        """Nomes case-insensitive devem agrupar no mesmo equipamento."""
        rows = [
            _make_row(equipamento="Prensa Hidráulica"),
            _make_row(equipamento="prensa hidráulica", perigo="Corte"),
            _make_row(equipamento="PRENSA HIDRÁULICA", perigo="Projeção"),
        ]
        contexts = build_equipment_contexts(rows)
        assert len(contexts) == 1
        # Display name preserva a primeira aparição
        assert contexts[0].equipment_name == "Prensa Hidráulica"
        assert len(contexts[0].identificacao_dos_perigos) == 3


# ---------------------------------------------------------------------------
# 5. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Casos de borda."""

    def test_empty_rows_raises(self) -> None:
        with pytest.raises(ValueError, match="vazio"):
            build_equipment_contexts([])

    def test_row_without_equipment_skipped(self) -> None:
        """Linhas sem equipamento são descartadas."""
        rows = [
            _make_row(equipamento=""),
            _make_row(equipamento="Prensa"),
        ]
        contexts = build_equipment_contexts(rows)
        assert len(contexts) == 1
        assert contexts[0].equipment_name == "Prensa"

    def test_equipment_without_perigos_skipped(self) -> None:
        """Equipamento sem nenhum perigo é ignorado."""
        rows = [
            _make_row(equipamento="Equip Sem Perigo", perigo=""),
        ]
        contexts = build_equipment_contexts(rows)
        assert len(contexts) == 0

    def test_missing_causas_placeholder(self) -> None:
        """Contexto sem causas recebe placeholder."""
        rows = [_make_row(causas="")]
        contexts = build_equipment_contexts(rows)
        assert contexts[0].causas_possiveis == ["Causa não especificada na planilha"]

    def test_missing_consequencias_placeholder(self) -> None:
        rows = [_make_row(consequencias="")]
        contexts = build_equipment_contexts(rows)
        assert contexts[0].consequencias_potenciais == [
            "Consequência não especificada na planilha"
        ]

    def test_missing_descricao_placeholder(self) -> None:
        rows = [_make_row(descricao_equipamento="")]
        contexts = build_equipment_contexts(rows)
        assert contexts[0].descricao_da_operacao == "Não informado"

    def test_missing_severity_risk_placeholder(self) -> None:
        rows = [_make_row(categoria_severidade=None, categoria_risco=None, categoria_probabilidade=None, classificacao_risco=None)]
        ctx = build_equipment_contexts(rows)[0]
        assert ctx.classificacao_do_risco.categoria_severidade == "Não informada"
        assert ctx.classificacao_do_risco.categoria_probabilidade == "Não informado"
        assert ctx.classificacao_do_risco.classificacao_risco == "Não informado"


# ---------------------------------------------------------------------------
# 6. Helpers unitários
# ---------------------------------------------------------------------------

class TestHelpers:
    """Cobertura dos helpers internos."""

    def test_split_field_semicolon(self) -> None:
        assert _split_field("A; B; C") == ["A", "B", "C"]

    def test_split_field_newline(self) -> None:
        assert _split_field("A\nB\nC") == ["A", "B", "C"]

    def test_split_field_bullet(self) -> None:
        assert _split_field("• A• B") == ["A", "B"]

    def test_split_field_none(self) -> None:
        assert _split_field(None) == []

    def test_split_field_empty(self) -> None:
        assert _split_field("") == []

    def test_highest_severity_ordering(self) -> None:
        assert _highest_severity("Baixa", "Alta") == "Alta"
        assert _highest_severity("Alta", "Baixa") == "Alta"
        assert _highest_severity("Média", "Muito Alta") == "Muito Alta"
        assert _highest_severity("Média para Alta", "Muito Alta") == "Muito Alta"
        assert _highest_severity("Média para Alta", "Alta") == "Alta"

    def test_highest_risk_ordering(self) -> None:
        assert _highest_risk("Baixo", "Alto") == "Alto"
        assert _highest_risk("Alto", "Baixo") == "Alto"
        assert _highest_risk("Médio", "Muito Alto") == "Muito Alto"
