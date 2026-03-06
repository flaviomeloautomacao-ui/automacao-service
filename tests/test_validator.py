"""Testes do adapter BasicSpreadsheetValidator.

Cobre:
  1. Dados válidos — nenhum erro levantado.
  2. Campo obrigatório vazio — ValidationError com detalhes.
  3. Valor de risco fora do conjunto permitido — ValidationError.
"""

from __future__ import annotations

import pytest

from app.adapters.spreadsheet.validator import BasicSpreadsheetValidator
from app.domain.entities import MachineRiskRow, RiskLevel
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
        "area": "Produção",
        "equipamento": "Prensa Hidráulica",
        "perigo": "Esmagamento de membros",
        "causa": "Falha na proteção",
        "consequencia": "Amputação",
        "risco": RiskLevel.MODERADO,
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
            _make_row(area="Setor A", risco=RiskLevel.TRIVIAL),
            _make_row(area="Setor B", risco=RiskLevel.INTOLERAVEL),
        ]
        validator.validate(rows)

    def test_norma_ref_valida(self, validator: BasicSpreadsheetValidator) -> None:
        """``norma_ref`` com sigla reconhecida não gera erro."""
        rows = [_make_row(norma_ref="ABNT NBR 14153")]
        validator.validate(rows)

    def test_norma_ref_ausente(self, validator: BasicSpreadsheetValidator) -> None:
        """``norma_ref`` None não gera erro."""
        rows = [_make_row(norma_ref=None)]
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
        assert err.errors[0]["field"] == "equipamento"
        assert err.errors[0]["row_index"] == 0

    def test_perigo_somente_espacos(self, validator: BasicSpreadsheetValidator) -> None:
        """``perigo`` contendo apenas espaços é considerado vazio."""
        rows = [_make_row(perigo="   ")]
        with pytest.raises(ValidationError) as exc_info:
            validator.validate(rows)

        campos = [e["field"] for e in exc_info.value.errors]
        assert "perigo" in campos

    def test_lista_vazia(self, validator: BasicSpreadsheetValidator) -> None:
        """Lista sem linhas deve gerar ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            validator.validate([])

        assert exc_info.value.errors[0]["field"] == "__all__"


# ---------------------------------------------------------------------------
# 3. Risco inválido (via construção manual para contornar enum)
# ---------------------------------------------------------------------------

class TestRiscoInvalido:
    """Cenários onde o nível de risco informado não é aceito.

    Como ``MachineRiskRow.risco`` é tipado como ``RiskLevel`` (enum), em
    produção valores inválidos seriam barrados pelo Pydantic no parse.
    Aqui testamos a lógica do validador usando um objeto que simula um
    valor inesperado, garantindo que a camada de validação funciona
    independentemente da camada de parsing.
    """

    def test_risco_invalido_via_mock(self, validator: BasicSpreadsheetValidator) -> None:
        """Risco com valor inexistente no enum deve gerar erro."""
        row = _make_row()
        # Forçamos um valor inválido contornando a imutabilidade
        object.__setattr__(row, "risco", "catastrófico")

        with pytest.raises(ValidationError) as exc_info:
            validator.validate([row])

        erros_risco = [e for e in exc_info.value.errors if e["field"] == "risco"]
        assert len(erros_risco) == 1
        assert "catastrófico" in erros_risco[0]["message"]

    def test_norma_ref_invalida(self, validator: BasicSpreadsheetValidator) -> None:
        """``norma_ref`` sem sigla reconhecida deve gerar erro."""
        rows = [_make_row(norma_ref="Alguma norma qualquer")]

        with pytest.raises(ValidationError) as exc_info:
            validator.validate(rows)

        erros_norma = [e for e in exc_info.value.errors if e["field"] == "norma_ref"]
        assert len(erros_norma) == 1
