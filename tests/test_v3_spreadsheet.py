"""Testes específicos para o suporte à planilha V3 (14 colunas).

Cobre:
  1. Parser — layout V3 com 14 colunas (campos de probabilidade, classificação
     e risco residual).
  2. Validator — campos obrigatórios V3 (categoria_probabilidade, classificacao_risco).
  3. EquipmentContextBuilder — consolidação de campos V3: probabilidade, classificação,
     risco residual.
  4. EquipmentPromptContext — propagação do risco residual ao EquipmentLLMInput.
  5. User Prompt — seções "Situação Atual" e "Pós Implementação" no prompt.
  6. Entidades V3 — ResidualRiskClassification, RiskClassification 3 campos.
"""

from __future__ import annotations

import io

import pandas as pd
import pytest

from app.adapters.spreadsheet.parser import PandasSpreadsheetParser
from app.adapters.spreadsheet.validator import BasicSpreadsheetValidator
from app.domain.entities import (
    EquipmentContext,
    EquipmentLLMInput,
    MachineRiskRow,
    ResidualRiskClassification,
    RiskClassification,
)
from app.domain.errors import ValidationError
from app.domain.services.equipment_context_builder import build_equipment_contexts
from app.domain.services.equipment_prompt_context import build_equipment_prompt_context
from app.domain.services.equipment_user_prompt import build_equipment_user_prompt


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

_NORMAS = [
    "NR-12 — Segurança no Trabalho em Máquinas e Equipamentos",
    "ABNT NBR 14153 — Segurança de máquinas",
]

# Colunas V3 completas (14 colunas)
_V3_COLUMNS = [
    "Equipamento",
    "Descrição do equipamento",
    "Riscos",
    "Perigo",
    "Causas Possíveis",
    "Consequências",
    "Categoria da Severidade",
    "Categoria da Probabilidade",
    "Classificação do Risco",
    "Medidas Preventivas Existentes",
    "Medidas Preventivas a Implementar",
    "Categoria da Severidade 2",
    "Categoria da Probabilidade 2",
    "Classificação do Risco 2",
]


def _build_v3_layout(
    data_rows: list[list],
    *,
    empty_rows_before: int = 0,
) -> pd.DataFrame:
    """Constrói DataFrame com layout V3 bruto (header=None)."""
    columns = list(_V3_COLUMNS)
    ncols = len(columns)
    rows: list[list] = []

    for _ in range(empty_rows_before):
        rows.append([None] * ncols)

    rows.append(columns)  # header

    for dr in data_rows:
        padded = list(dr) + [None] * (ncols - len(dr))
        rows.append(padded[:ncols])

    return pd.DataFrame(rows)


def _v3_minimal_data(**overrides: object) -> list:
    """Retorna uma lista representando 1 linha V3 mínima."""
    base = {
        "equipamento": "Prensa Hidráulica",
        "descricao_equipamento": "Prensa 150t",
        "riscos": "Mecânico",
        "perigo": "Esmagamento de membros",
        "causas": "Falha na proteção",
        "consequencias": "Amputação",
        "categoria_severidade": "Alta",
        "categoria_probabilidade": "Alto",
        "classificacao_risco": "Muito Alto",
        "medidas_existentes": "Barreira física",
        "medidas_implementar": "Sensor de presença",
        "categoria_severidade_2": "Média",
        "categoria_probabilidade_2": "Médio",
        "classificacao_risco_2": "Médio",
    }
    base.update(overrides)
    return [
        base["equipamento"],
        base["descricao_equipamento"],
        base["riscos"],
        base["perigo"],
        base["causas"],
        base["consequencias"],
        base["categoria_severidade"],
        base["categoria_probabilidade"],
        base["classificacao_risco"],
        base["medidas_existentes"],
        base["medidas_implementar"],
        base["categoria_severidade_2"],
        base["categoria_probabilidade_2"],
        base["classificacao_risco_2"],
    ]


def _df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False)
    return buf.getvalue().encode("utf-8")


def _make_v3_row(**overrides: object) -> MachineRiskRow:
    """Cria um MachineRiskRow com campos V3."""
    defaults: dict[str, object] = {
        "equipamento": "Prensa Hidráulica",
        "perigo": "Esmagamento",
        "causas": "Falha na proteção",
        "consequencias": "Amputação",
        "categoria_severidade": "Alta",
        "categoria_probabilidade": "Alto",
        "classificacao_risco": "Muito Alto",
    }
    defaults.update(overrides)
    return MachineRiskRow(**defaults)  # type: ignore[arg-type]


def _make_v3_row_dict(**overrides: object) -> dict:
    """Cria dict de row V3 para o builder."""
    defaults: dict[str, object] = {
        "equipamento": "Prensa Hidráulica",
        "descricao_equipamento": "Prensa 150t",
        "perigo": "Esmagamento",
        "causas": "Falha na proteção",
        "consequencias": "Amputação",
        "categoria_severidade": "Alta",
        "categoria_risco": "Alto",
        "categoria_probabilidade": "Alto",
        "classificacao_risco": "Muito Alto",
        "medidas_existentes": "Barreira física",
        "medidas_implementar": "Sensor de presença",
        "riscos": "Mecânico",
        "observacoes": None,
    }
    defaults.update(overrides)
    return defaults


def _make_v3_ctx(**overrides: object) -> EquipmentContext:
    """EquipmentContext V3 com risco residual."""
    defaults: dict[str, object] = {
        "index": 1,
        "equipment_name": "Prensa Hidráulica PH-01",
        "descricao_da_operacao": "Conformação de chapas",
        "identificacao_dos_perigos": ["Esmagamento de membros"],
        "causas_possiveis": ["Falha na proteção"],
        "consequencias_potenciais": ["Amputação"],
        "classificacao_do_risco": RiskClassification(
            categoria_severidade="Alta",
            categoria_probabilidade="Alto",
            classificacao_risco="Muito Alto",
        ),
        "classificacao_risco_residual": ResidualRiskClassification(
            categoria_severidade="Média",
            categoria_probabilidade="Médio",
            classificacao_risco="Médio",
        ),
        "medidas_preventivas_existentes": ["Barreira física"],
        "medidas_a_implementar": ["Sensor de presença"],
        "observacoes": [],
        "riscos_descricao": ["Mecânico"],
        "row_count": 1,
    }
    defaults.update(overrides)
    return EquipmentContext(**defaults)  # type: ignore[arg-type]


def _make_v3_llm_input(**overrides: object) -> EquipmentLLMInput:
    """EquipmentLLMInput V3 com risco residual."""
    defaults: dict[str, object] = {
        "equipment_name": "Prensa Hidráulica PH-01",
        "descricao_da_operacao": "Conformação de chapas",
        "identificacao_dos_perigos": ["Esmagamento de membros"],
        "causas_possiveis": ["Falha na proteção"],
        "consequencias_potenciais": ["Amputação"],
        "classificacao_do_risco": RiskClassification(
            categoria_severidade="Alta",
            categoria_probabilidade="Alto",
            classificacao_risco="Muito Alto",
        ),
        "classificacao_risco_residual": ResidualRiskClassification(
            categoria_severidade="Média",
            categoria_probabilidade="Médio",
            classificacao_risco="Médio",
        ),
        "medidas_preventivas_existentes": ["Barreira física"],
        "medidas_a_implementar": ["Sensor de presença"],
        "normas_aplicaveis": _NORMAS,
    }
    defaults.update(overrides)
    return EquipmentLLMInput(**defaults)  # type: ignore[arg-type]


# ===========================================================================
# 1. Parser — V3 layout (14 colunas)
# ===========================================================================

class TestParserV3:
    """Parser deve reconhecer e mapear os 14 cabeçalhos V3."""

    @pytest.fixture
    def parser(self) -> PandasSpreadsheetParser:
        return PandasSpreadsheetParser()

    def test_v3_csv_all_fields(self, parser: PandasSpreadsheetParser) -> None:
        """Layout V3 completo — todos os 14 campos mapeados."""
        df = _build_v3_layout([_v3_minimal_data()])
        rows = parser.parse(_df_to_csv_bytes(df), "riscos_v3.csv")

        assert len(rows) == 1
        row = rows[0]
        assert row.equipamento == "Prensa Hidráulica"
        assert row.categoria_severidade == "Alta"
        assert row.categoria_probabilidade == "Alto"
        assert row.classificacao_risco == "Muito Alto"
        assert row.categoria_severidade_2 == "Média"
        assert row.categoria_probabilidade_2 == "Médio"
        assert row.classificacao_risco_2 == "Médio"

    def test_v3_csv_residual_none(self, parser: PandasSpreadsheetParser) -> None:
        """Layout V3 sem campos residuais preenchidos."""
        data = _v3_minimal_data(
            categoria_severidade_2=None,
            categoria_probabilidade_2=None,
            classificacao_risco_2=None,
        )
        df = _build_v3_layout([data])
        rows = parser.parse(_df_to_csv_bytes(df), "v3_sem_residual.csv")

        row = rows[0]
        assert row.categoria_probabilidade == "Alto"
        assert row.classificacao_risco == "Muito Alto"
        assert row.categoria_severidade_2 is None
        assert row.categoria_probabilidade_2 is None
        assert row.classificacao_risco_2 is None

    def test_v3_multiple_rows(self, parser: PandasSpreadsheetParser) -> None:
        """Múltiplas linhas V3."""
        row1 = _v3_minimal_data(equipamento="Prensa", classificacao_risco="Muito Alto")
        row2 = _v3_minimal_data(equipamento="Torno", classificacao_risco="Alto")
        df = _build_v3_layout([row1, row2])
        rows = parser.parse(_df_to_csv_bytes(df), "multi_v3.csv")

        assert len(rows) == 2
        assert rows[0].classificacao_risco == "Muito Alto"
        assert rows[1].classificacao_risco == "Alto"


# ===========================================================================
# 2. Validator — V3 campos obrigatórios
# ===========================================================================

class TestValidatorV3:
    """Validador deve exigir categoria_probabilidade e classificacao_risco."""

    @pytest.fixture
    def validator(self) -> BasicSpreadsheetValidator:
        return BasicSpreadsheetValidator()

    def test_v3_valid_row(self, validator: BasicSpreadsheetValidator) -> None:
        rows = [_make_v3_row()]
        validator.validate(rows)  # não deve levantar

    def test_v3_missing_probabilidade(self, validator: BasicSpreadsheetValidator) -> None:
        """categoria_probabilidade vazio deve gerar erro."""
        rows = [_make_v3_row(categoria_probabilidade="")]
        with pytest.raises(ValidationError) as exc_info:
            validator.validate(rows)
        campos = [e["column"] for e in exc_info.value.errors]
        assert "categoria_probabilidade" in campos

    def test_v3_missing_classificacao(self, validator: BasicSpreadsheetValidator) -> None:
        """classificacao_risco vazio deve gerar erro."""
        rows = [_make_v3_row(classificacao_risco="")]
        with pytest.raises(ValidationError) as exc_info:
            validator.validate(rows)
        campos = [e["column"] for e in exc_info.value.errors]
        assert "classificacao_risco" in campos

    def test_v3_residual_optional(self, validator: BasicSpreadsheetValidator) -> None:
        """Campos residuais não são obrigatórios."""
        rows = [_make_v3_row(
            categoria_severidade_2=None,
            categoria_probabilidade_2=None,
            classificacao_risco_2=None,
        )]
        validator.validate(rows)  # não deve levantar


# ===========================================================================
# 3. EquipmentContextBuilder — V3 consolidação
# ===========================================================================

class TestContextBuilderV3:
    """Builder deve consolidar probabilidade, classificação e risco residual."""

    def test_probabilidade_highest(self) -> None:
        rows = [
            _make_v3_row_dict(categoria_probabilidade="Baixo", classificacao_risco="Baixo"),
            _make_v3_row_dict(categoria_probabilidade="Muito Alto", classificacao_risco="Muito Alto"),
        ]
        ctxs = build_equipment_contexts(rows)
        assert ctxs[0].classificacao_do_risco.categoria_probabilidade == "Muito Alto"

    def test_classificacao_highest(self) -> None:
        rows = [
            _make_v3_row_dict(classificacao_risco="Médio"),
            _make_v3_row_dict(classificacao_risco="Muito Alto"),
        ]
        ctxs = build_equipment_contexts(rows)
        assert ctxs[0].classificacao_do_risco.classificacao_risco == "Muito Alto"

    def test_residual_present(self) -> None:
        """Campos residuais preenchidos geram ResidualRiskClassification."""
        rows = [_make_v3_row_dict(
            categoria_severidade_2="Média",
            categoria_probabilidade_2="Médio",
            classificacao_risco_2="Médio",
        )]
        ctxs = build_equipment_contexts(rows)
        res = ctxs[0].classificacao_risco_residual
        assert res is not None
        assert res.categoria_severidade == "Média"
        assert res.categoria_probabilidade == "Médio"
        assert res.classificacao_risco == "Médio"

    def test_residual_none_when_empty(self) -> None:
        """Sem campos residuais → classificacao_risco_residual = None."""
        rows = [_make_v3_row_dict()]
        ctxs = build_equipment_contexts(rows)
        assert ctxs[0].classificacao_risco_residual is None

    def test_residual_highest_consolidation(self) -> None:
        """Campos residuais consolidados para o valor mais alto."""
        rows = [
            _make_v3_row_dict(
                categoria_severidade_2="Baixa",
                categoria_probabilidade_2="Baixo",
                classificacao_risco_2="Baixo",
            ),
            _make_v3_row_dict(
                categoria_severidade_2="Média",
                categoria_probabilidade_2="Médio",
                classificacao_risco_2="Médio",
            ),
        ]
        ctxs = build_equipment_contexts(rows)
        res = ctxs[0].classificacao_risco_residual
        assert res is not None
        assert res.categoria_severidade == "Média"
        assert res.categoria_probabilidade == "Médio"
        assert res.classificacao_risco == "Médio"

    def test_to_template_dict_v3(self) -> None:
        """to_template_dict inclui campos V3."""
        ctx = _make_v3_ctx()
        d = ctx.to_template_dict()
        assert d["probabilidade"] == "Alto"
        assert d["classificacao"] == "Muito Alto"
        assert d["severidade_residual"] == "Média"
        assert d["probabilidade_residual"] == "Médio"
        assert d["classificacao_residual"] == "Médio"

    def test_to_template_dict_no_residual(self) -> None:
        """to_template_dict sem risco residual → None."""
        ctx = _make_v3_ctx(classificacao_risco_residual=None)
        d = ctx.to_template_dict()
        assert d["severidade_residual"] is None
        assert d["probabilidade_residual"] is None
        assert d["classificacao_residual"] is None


# ===========================================================================
# 4. EquipmentPromptContext — propagação V3
# ===========================================================================

class TestPromptContextV3:
    """Prompt context builder deve propagar campos V3 e residual."""

    def test_3_field_risk_classification(self) -> None:
        """RiskClassification com 3 campos no resultado."""
        ctx = _make_v3_ctx()
        result = build_equipment_prompt_context(ctx, _NORMAS)
        assert result is not None
        assert result.classificacao_do_risco.categoria_severidade == "Alta"
        assert result.classificacao_do_risco.categoria_probabilidade == "Alto"
        assert result.classificacao_do_risco.classificacao_risco == "Muito Alto"

    def test_residual_propagated(self) -> None:
        """Risco residual é propagado ao EquipmentLLMInput."""
        ctx = _make_v3_ctx()
        result = build_equipment_prompt_context(ctx, _NORMAS)
        assert result is not None
        assert result.classificacao_risco_residual is not None
        assert result.classificacao_risco_residual.categoria_severidade == "Média"
        assert result.classificacao_risco_residual.categoria_probabilidade == "Médio"
        assert result.classificacao_risco_residual.classificacao_risco == "Médio"

    def test_no_residual_when_absent(self) -> None:
        ctx = _make_v3_ctx(classificacao_risco_residual=None)
        result = build_equipment_prompt_context(ctx, _NORMAS)
        assert result is not None
        assert result.classificacao_risco_residual is None


# ===========================================================================
# 5. User Prompt — seções V3
# ===========================================================================

class TestUserPromptV3:
    """Prompt per-equipment deve refletir o layout V3."""

    def test_situacao_atual_header(self) -> None:
        """Seção de classificação agora diz 'Situação Atual'."""
        prompt = build_equipment_user_prompt(_make_v3_llm_input())
        assert "### Classificação do Risco — Situação Atual ###" in prompt

    def test_probabilidade_in_prompt(self) -> None:
        prompt = build_equipment_user_prompt(_make_v3_llm_input())
        assert "Categoria da Probabilidade: Alto" in prompt

    def test_classificacao_in_prompt(self) -> None:
        prompt = build_equipment_user_prompt(_make_v3_llm_input())
        assert "Classificação do Risco: Muito Alto" in prompt

    def test_residual_block_present(self) -> None:
        """Com risco residual, bloco pós-implementação aparece."""
        prompt = build_equipment_user_prompt(_make_v3_llm_input())
        assert "### Classificação do Risco — Pós Implementação das Medidas Preventivas ###" in prompt
        assert "Severidade Residual: Média" in prompt
        assert "Probabilidade Residual: Médio" in prompt
        assert "Classificação do Risco Residual: Médio" in prompt

    def test_residual_block_absent(self) -> None:
        """Sem risco residual, bloco pós-implementação não aparece."""
        inp = _make_v3_llm_input(classificacao_risco_residual=None)
        prompt = build_equipment_user_prompt(inp)
        assert "Pós Implementação" not in prompt


# ===========================================================================
# 6. Entidades V3
# ===========================================================================

class TestEntitiesV3:
    """Testes dos modelos V3."""

    def test_risk_classification_3_fields(self) -> None:
        rc = RiskClassification(
            categoria_severidade="Alta",
            categoria_probabilidade="Alto",
            classificacao_risco="Muito Alto",
        )
        assert rc.categoria_severidade == "Alta"
        assert rc.categoria_probabilidade == "Alto"
        assert rc.classificacao_risco == "Muito Alto"
        # Alias de compatibilidade
        assert rc.categoria_risco == "Alto"

    def test_risk_classification_frozen(self) -> None:
        rc = RiskClassification(
            categoria_severidade="Alta",
            categoria_probabilidade="Alto",
            classificacao_risco="Muito Alto",
        )
        with pytest.raises(Exception):
            rc.categoria_severidade = "Baixa"  # type: ignore[misc]

    def test_residual_risk_all_optional(self) -> None:
        """Todos os campos do ResidualRiskClassification são opcionais."""
        rrc = ResidualRiskClassification()
        assert rrc.categoria_severidade is None
        assert rrc.categoria_probabilidade is None
        assert rrc.classificacao_risco is None

    def test_residual_risk_partial(self) -> None:
        """Apenas alguns campos do residual preenchidos."""
        rrc = ResidualRiskClassification(
            categoria_severidade="Baixa",
        )
        assert rrc.categoria_severidade == "Baixa"
        assert rrc.categoria_probabilidade is None

    def test_residual_risk_frozen(self) -> None:
        rrc = ResidualRiskClassification(
            categoria_severidade="Baixa",
            categoria_probabilidade="Baixo",
            classificacao_risco="Baixo",
        )
        with pytest.raises(Exception):
            rrc.categoria_severidade = "Alta"  # type: ignore[misc]

    def test_machine_risk_row_v3_fields(self) -> None:
        row = MachineRiskRow(
            equipamento="Prensa",
            perigo="Esmagamento",
            causas="Falha",
            consequencias="Amputação",
            categoria_severidade="Alta",
            categoria_probabilidade="Alto",
            classificacao_risco="Muito Alto",
            categoria_severidade_2="Média",
            categoria_probabilidade_2="Médio",
            classificacao_risco_2="Médio",
        )
        assert row.categoria_probabilidade == "Alto"
        assert row.classificacao_risco == "Muito Alto"
        assert row.categoria_severidade_2 == "Média"
        assert row.categoria_probabilidade_2 == "Médio"
        assert row.classificacao_risco_2 == "Médio"
