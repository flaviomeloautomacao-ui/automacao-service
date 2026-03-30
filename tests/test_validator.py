"""Testes do adapter BasicSpreadsheetValidator.

Cobre:
  1. Dados válidos — nenhum erro levantado.
  2. Campo obrigatório vazio — ValidationError com detalhes.
"""

from __future__ import annotations

import pytest

from app.adapters.spreadsheet.validator import BasicSpreadsheetValidator
from app.domain.entities import MachineRiskRow
from app.domain.errors import ValidationError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def validator() -> BasicSpreadsheetValidator:
    """Instância limpa do validador."""
    return BasicSpreadsheetValidator()


def _make_row(**overrides: object) -> MachineRiskRow:
    """Cria uma ``MachineRiskRow`` mínima válida, aceitando sobrescritas."""
    defaults: dict[str, object] = {
        "equipamento": "Prensa Hidráulica",
        "perigo": "Esmagamento de membros",
        "causas": "Falha na proteção",
        "consequencias": "Amputação",
        "categoria_severidade": "IV",
        "categoria_probabilidade": "Alto",
        "classificacao_risco": "Alto",
    }
    defaults.update(overrides)
    return MachineRiskRow(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 1. Dados válidos — sem erros
# ---------------------------------------------------------------------------

class TestValidacaoOK:
    """Cenários válidos que não devem levantar exceção."""

    def test_uma_linha_valida(self, validator: BasicSpreadsheetValidator) -> None:
        """Uma única linha com todos os campos obrigatórios preenchidos."""
        rows = [_make_row()]
        validator.validate(rows)  # não deve levantar

    def test_varias_linhas_validas(self, validator: BasicSpreadsheetValidator) -> None:
        """Múltiplas linhas válidas."""
        rows = [
            _make_row(equipamento="Prensa"),
            _make_row(equipamento="Torno"),
        ]
        validator.validate(rows)

    def test_campos_opcionais_ausentes(self, validator: BasicSpreadsheetValidator) -> None:
        """Campos opcionais None não geram erro."""
        rows = [_make_row(
            descricao_equipamento=None,
            riscos=None,
            medidas_existentes=None,
            medidas_implementar=None,
            observacoes=None,
        )]
        validator.validate(rows)

    def test_campos_opcionais_preenchidos(self, validator: BasicSpreadsheetValidator) -> None:
        """Campos opcionais preenchidos não geram erro."""
        rows = [_make_row(
            descricao_equipamento="Prensa 150t",
            riscos="Mecânico",
            categoria_severidade="IV",
            categoria_probabilidade="Alto",
            classificacao_risco="Alto",
            medidas_existentes="Barreira",
            medidas_implementar="Sensor",
            observacoes="OK",
        )]
        validator.validate(rows)


# ---------------------------------------------------------------------------
# 2. Campo obrigatório vazio
# ---------------------------------------------------------------------------

class TestCampoObrigatorioVazio:
    """Cenários onde campos obrigatórios estão vazios / em branco."""

    def test_equipamento_vazio(self, validator: BasicSpreadsheetValidator) -> None:
        """``equipamento`` vazio deve gerar ValidationError."""
        rows = [_make_row(equipamento="")]
        with pytest.raises(ValidationError) as exc_info:
            validator.validate(rows)

        err = exc_info.value
        assert len(err.errors) >= 1
        assert err.errors[0]["column"] == "equipamento"
        assert err.errors[0]["row"] == 1

    def test_perigo_somente_espacos(self, validator: BasicSpreadsheetValidator) -> None:
        """``perigo`` contendo apenas espaços é considerado vazio."""
        rows = [_make_row(perigo="   ")]
        with pytest.raises(ValidationError) as exc_info:
            validator.validate(rows)

        campos = [e["column"] for e in exc_info.value.errors]
        assert "perigo" in campos

    def test_causas_vazio(self, validator: BasicSpreadsheetValidator) -> None:
        """``causas`` vazio deve gerar ValidationError."""
        rows = [_make_row(causas="")]
        with pytest.raises(ValidationError) as exc_info:
            validator.validate(rows)

        campos = [e["column"] for e in exc_info.value.errors]
        assert "causas" in campos

    def test_consequencias_vazio(self, validator: BasicSpreadsheetValidator) -> None:
        """``consequencias`` vazio deve gerar ValidationError."""
        rows = [_make_row(consequencias="")]
        with pytest.raises(ValidationError) as exc_info:
            validator.validate(rows)

        campos = [e["column"] for e in exc_info.value.errors]
        assert "consequencias" in campos

    def test_lista_vazia(self, validator: BasicSpreadsheetValidator) -> None:
        """Lista sem linhas deve gerar ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            validator.validate([])

        assert exc_info.value.errors[0]["column"] == "*"
