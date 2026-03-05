"""Testes do adapter PandasSpreadsheetParser.

Todos os testes usam ``pandas.DataFrame`` em memória — nenhum arquivo real
é necessário. Onde preciso simular bytes, convertemos o DataFrame para
CSV / XLSX em memória.
"""

from __future__ import annotations

import io

import pandas as pd
import pytest

from app.adapters.spreadsheet.parser import PandasSpreadsheetParser
from app.domain.entities import MachineRiskRow, PriorityLevel, RiskLevel
from app.domain.errors import ValidationError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def parser() -> PandasSpreadsheetParser:
    """Instância limpa do parser."""
    return PandasSpreadsheetParser()


def _minimal_df(**overrides: object) -> pd.DataFrame:
    """Cria um DataFrame mínimo com 1 linha contendo todos os campos obrigatórios."""
    base: dict[str, list] = {
        "area": ["Produção"],
        "equipamento": ["Prensa Hidráulica"],
        "perigo": ["Esmagamento de membros"],
        "causa": ["Falha na proteção"],
        "consequencia": ["Amputação"],
        "risco": ["moderado"],
    }
    base.update({k: [v] for k, v in overrides.items()})
    return pd.DataFrame(base)


def _df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Converte DataFrame para bytes CSV (UTF-8)."""
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def _df_to_xlsx_bytes(df: pd.DataFrame) -> bytes:
    """Converte DataFrame para bytes XLSX em memória."""
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# parse — cenários de sucesso
# ---------------------------------------------------------------------------

class TestParseSuccess:
    """Cenários onde o parsing deve ter sucesso."""

    def test_csv_minimal(self, parser: PandasSpreadsheetParser) -> None:
        """Arquivo CSV com campos obrigatórios mínimos."""
        df = _minimal_df()
        rows = parser.parse(_df_to_csv_bytes(df), "riscos.csv")

        assert len(rows) == 1
        row = rows[0]
        assert isinstance(row, MachineRiskRow)
        assert row.area == "Produção"
        assert row.equipamento == "Prensa Hidráulica"
        assert row.risco == RiskLevel.MODERADO

    def test_xlsx_minimal(self, parser: PandasSpreadsheetParser) -> None:
        """Arquivo XLSX com campos obrigatórios mínimos."""
        df = _minimal_df()
        rows = parser.parse(_df_to_xlsx_bytes(df), "riscos.xlsx")

        assert len(rows) == 1
        assert rows[0].risco == RiskLevel.MODERADO

    def test_alias_columns(self, parser: PandasSpreadsheetParser) -> None:
        """Colunas com nomes alternativos (aliases) devem ser mapeadas."""
        df = pd.DataFrame({
            "Área": ["Almoxarifado"],
            "Máquina": ["Empilhadeira"],
            "Hazard": ["Tombamento"],
            "Cause": ["Piso irregular"],
            "Consequence": ["Fraturas"],
            "Risk_Level": ["substancial"],
        })
        rows = parser.parse(_df_to_csv_bytes(df), "test.csv")

        assert len(rows) == 1
        assert rows[0].equipamento == "Empilhadeira"
        assert rows[0].risco == RiskLevel.SUBSTANCIAL

    def test_optional_fields_populated(self, parser: PandasSpreadsheetParser) -> None:
        """Campos opcionais são preservados quando presentes."""
        df = _minimal_df(
            probabilidade="Alta",
            severidade="Grave",
            norma_ref="NR-12",
            recomendacao="Instalar barreira",
            prioridade="urgente",
            foto_ref="foto_01.jpg",
            observacoes="Verificar semanal",
        )
        rows = parser.parse(_df_to_csv_bytes(df), "dados.csv")

        row = rows[0]
        assert row.probabilidade == "Alta"
        assert row.severidade == "Grave"
        assert row.norma_ref == "NR-12"
        assert row.recomendacao == "Instalar barreira"
        assert row.prioridade == PriorityLevel.URGENTE
        assert row.foto_ref == "foto_01.jpg"
        assert row.observacoes == "Verificar semanal"

    def test_optional_fields_none_when_empty(self, parser: PandasSpreadsheetParser) -> None:
        """Campos opcionais ficam None quando não preenchidos."""
        df = _minimal_df()
        rows = parser.parse(_df_to_csv_bytes(df), "dados.csv")

        row = rows[0]
        assert row.probabilidade is None
        assert row.severidade is None
        assert row.norma_ref is None
        assert row.recomendacao is None
        assert row.prioridade is None
        assert row.foto_ref is None
        assert row.observacoes is None

    def test_whitespace_trimmed(self, parser: PandasSpreadsheetParser) -> None:
        """Espaços em branco ao redor de strings devem ser removidos."""
        df = pd.DataFrame({
            "area": ["  Produção  "],
            "equipamento": [" Torno CNC "],
            "perigo": ["Projeção de peças "],
            "causa": [" Ausência de carenagem"],
            "consequencia": [" Ferimento "],
            "risco": [" moderado "],
        })
        rows = parser.parse(_df_to_csv_bytes(df), "test.csv")

        row = rows[0]
        assert row.area == "Produção"
        assert row.equipamento == "Torno CNC"
        assert row.risco == RiskLevel.MODERADO

    def test_multiple_rows(self, parser: PandasSpreadsheetParser) -> None:
        """Múltiplas linhas são convertidas corretamente."""
        df = pd.DataFrame({
            "area": ["Produção", "Manutenção"],
            "equipamento": ["Prensa", "Torno"],
            "perigo": ["Esmagamento", "Projeção"],
            "causa": ["Falha proteção", "Sem carenagem"],
            "consequencia": ["Amputação", "Ferimento"],
            "risco": ["intolerável", "moderado"],
        })
        rows = parser.parse(_df_to_csv_bytes(df), "multi.csv")

        assert len(rows) == 2
        assert rows[0].risco == RiskLevel.INTOLERAVEL
        assert rows[1].risco == RiskLevel.MODERADO

    def test_all_risk_levels(self, parser: PandasSpreadsheetParser) -> None:
        """Todos os níveis de risco válidos são aceitos."""
        levels = ["trivial", "tolerável", "moderado", "substancial", "intolerável"]
        df = pd.DataFrame({
            "area": ["A"] * 5,
            "equipamento": ["E"] * 5,
            "perigo": ["P"] * 5,
            "causa": ["C"] * 5,
            "consequencia": ["X"] * 5,
            "risco": levels,
        })
        rows = parser.parse(_df_to_csv_bytes(df), "levels.csv")

        assert len(rows) == 5
        assert rows[0].risco == RiskLevel.TRIVIAL
        assert rows[4].risco == RiskLevel.INTOLERAVEL


# ---------------------------------------------------------------------------
# parse — cenários de erro
# ---------------------------------------------------------------------------

class TestParseErrors:
    """Cenários onde o parsing deve lançar ``ValidationError``."""

    def test_unsupported_format(self, parser: PandasSpreadsheetParser) -> None:
        """Extensão não suportada (.txt) deve lançar erro."""
        with pytest.raises(ValidationError, match="Formato de arquivo não suportado"):
            parser.parse(b"data", "arquivo.txt")

    def test_missing_required_columns(self, parser: PandasSpreadsheetParser) -> None:
        """Planilha sem colunas obrigatórias deve indicar quais faltam."""
        df = pd.DataFrame({"area": ["X"], "equipamento": ["Y"]})
        with pytest.raises(ValidationError, match="Colunas obrigatórias ausentes"):
            parser.parse(_df_to_csv_bytes(df), "incompleto.csv")

    def test_empty_required_field(self, parser: PandasSpreadsheetParser) -> None:
        """Célula obrigatória vazia gera erro informando linha e campo."""
        df = _minimal_df(equipamento="")
        with pytest.raises(ValidationError, match="equipamento.*vazio"):
            parser.parse(_df_to_csv_bytes(df), "vazio.csv")

    def test_invalid_risk_level(self, parser: PandasSpreadsheetParser) -> None:
        """Nível de risco inválido gera erro descritivo."""
        df = _minimal_df(risco="catastrófico")
        with pytest.raises(ValidationError, match="Nível de risco inválido"):
            parser.parse(_df_to_csv_bytes(df), "risco_ruim.csv")

    def test_invalid_priority_level(self, parser: PandasSpreadsheetParser) -> None:
        """Prioridade inválida gera erro descritivo."""
        df = _minimal_df(prioridade="crítica")
        with pytest.raises(ValidationError, match="Prioridade inválida"):
            parser.parse(_df_to_csv_bytes(df), "prio_ruim.csv")

    def test_empty_spreadsheet(self, parser: PandasSpreadsheetParser) -> None:
        """Planilha sem linhas de dados deve gerar erro."""
        df = pd.DataFrame(columns=["area", "equipamento", "perigo", "causa", "consequencia", "risco"])
        with pytest.raises(ValidationError, match="planilha está vazia"):
            parser.parse(_df_to_csv_bytes(df), "vazio.csv")

    def test_none_required_field(self, parser: PandasSpreadsheetParser) -> None:
        """Campo obrigatório com None (NaN no CSV) deve lançar erro."""
        df = pd.DataFrame({
            "area": [None],
            "equipamento": ["Prensa"],
            "perigo": ["X"],
            "causa": ["Y"],
            "consequencia": ["Z"],
            "risco": ["moderado"],
        })
        with pytest.raises(ValidationError, match="area.*vazio"):
            parser.parse(_df_to_csv_bytes(df), "none.csv")


# ---------------------------------------------------------------------------
# Protocolo — garante compatibilidade com SpreadsheetParserPort
# ---------------------------------------------------------------------------

class TestProtocol:
    """Verifica que a classe implementa o protocolo do domínio."""

    def test_implements_port(self) -> None:
        from app.domain.ports import SpreadsheetParserPort

        assert isinstance(PandasSpreadsheetParser(), SpreadsheetParserPort)
