"""Testes do adapter PandasSpreadsheetParser.

Todos os testes usam ``pandas.DataFrame`` em memória — nenhum arquivo real
é necessário. Os DataFrames simulam o layout real da planilha padrão de
análise de risco, com header=None e detecção automática de cabeçalho.
"""

from __future__ import annotations

import io

import pandas as pd
import pytest

from app.adapters.spreadsheet.parser import PandasSpreadsheetParser
from app.domain.entities import MachineRiskRow
from app.domain.errors import ValidationError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def parser() -> PandasSpreadsheetParser:
    """Instância limpa do parser."""
    return PandasSpreadsheetParser()


# Colunas exatas da planilha real
_REAL_COLUMNS = [
    "Equipamento",
    "Descrição do equipamento",
    "Riscos",
    "Perigo",
    "Causas Possíveis",
    "Consequências",
    "Categoria da Severidade",
    "Categoria do Risco",
    "Medidas Preventivas Existentes",
    "Medidas Preventivas a Implementar",
    "Observações",
]


def _build_real_layout(
    data_rows: list[list],
    *,
    empty_rows_before: int = 0,
    extra_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Constrói um DataFrame que simula o layout bruto da planilha real.

    Args:
        data_rows: lista de linhas (cada uma = lista de valores).
        empty_rows_before: linhas vazias antes do cabeçalho.
        extra_columns: colunas extras a incluir (ex.: ["Coluna1"]).

    Returns:
        DataFrame SEM header (header=None), como pandas leria o XLSX.
    """
    columns = list(_REAL_COLUMNS)
    if extra_columns:
        columns.extend(extra_columns)

    # montar linhas vazias + header + dados
    ncols = len(columns)
    rows: list[list] = []

    for _ in range(empty_rows_before):
        rows.append([None] * ncols)

    rows.append(columns)  # header

    for dr in data_rows:
        # pad com None se a linha for curta
        padded = list(dr) + [None] * (ncols - len(dr))
        rows.append(padded[:ncols])

    return pd.DataFrame(rows)


def _minimal_data(**overrides: object) -> list:
    """Retorna uma lista representando 1 linha de dados mínima."""
    base = {
        "equipamento": "Prensa Hidráulica",
        "descricao_equipamento": "Prensa 150t",
        "riscos": "Mecânico",
        "perigo": "Esmagamento de membros",
        "causas": "Falha na proteção",
        "consequencias": "Amputação",
        "categoria_severidade": "IV",
        "categoria_risco": "Alto",
        "medidas_existentes": "Barreira física",
        "medidas_implementar": "Sensor de presença",
        "observacoes": "Verificar semanal",
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
        base["categoria_risco"],
        base["medidas_existentes"],
        base["medidas_implementar"],
        base["observacoes"],
    ]


def _df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Converte DataFrame para bytes CSV (UTF-8), sem header (imita o layout real)."""
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False)
    return buf.getvalue().encode("utf-8")


def _df_to_xlsx_bytes(df: pd.DataFrame) -> bytes:
    """Converte DataFrame para bytes XLSX em memória, sem header."""
    buf = io.BytesIO()
    df.to_excel(buf, index=False, header=False, engine="openpyxl")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# parse — cenários de sucesso
# ---------------------------------------------------------------------------

class TestParseSuccess:
    """Cenários onde o parsing deve ter sucesso."""

    def test_csv_minimal(self, parser: PandasSpreadsheetParser) -> None:
        """Arquivo CSV com layout real, campos obrigatórios preenchidos."""
        df = _build_real_layout([_minimal_data()])
        rows = parser.parse(_df_to_csv_bytes(df), "riscos.csv")

        assert len(rows) == 1
        row = rows[0]
        assert isinstance(row, MachineRiskRow)
        assert row.equipamento == "Prensa Hidráulica"
        assert row.perigo == "Esmagamento de membros"
        assert row.causas == "Falha na proteção"
        assert row.consequencias == "Amputação"

    def test_xlsx_minimal(self, parser: PandasSpreadsheetParser) -> None:
        """Arquivo XLSX com layout real."""
        df = _build_real_layout([_minimal_data()])
        rows = parser.parse(_df_to_xlsx_bytes(df), "riscos.xlsx")

        assert len(rows) == 1
        assert rows[0].equipamento == "Prensa Hidráulica"

    def test_empty_rows_before_header(self, parser: PandasSpreadsheetParser) -> None:
        """Linhas vazias antes do cabeçalho são ignoradas."""
        df = _build_real_layout([_minimal_data()], empty_rows_before=3)
        rows = parser.parse(_df_to_csv_bytes(df), "riscos.csv")

        assert len(rows) == 1
        assert rows[0].equipamento == "Prensa Hidráulica"

    def test_coluna1_is_ignored(self, parser: PandasSpreadsheetParser) -> None:
        """Coluna auxiliar 'Coluna1' é removida sem erro."""
        df = _build_real_layout(
            [_minimal_data() + ["algum valor"]],
            extra_columns=["Coluna1"],
        )
        rows = parser.parse(_df_to_csv_bytes(df), "riscos.csv")

        assert len(rows) == 1
        assert rows[0].equipamento == "Prensa Hidráulica"

    def test_optional_fields_populated(self, parser: PandasSpreadsheetParser) -> None:
        """Campos opcionais são preservados quando presentes."""
        df = _build_real_layout([_minimal_data()])
        rows = parser.parse(_df_to_csv_bytes(df), "dados.csv")

        row = rows[0]
        assert row.descricao_equipamento == "Prensa 150t"
        assert row.riscos == "Mecânico"
        assert row.categoria_severidade == "IV"
        assert row.categoria_risco == "Alto"
        assert row.medidas_existentes == "Barreira física"
        assert row.medidas_implementar == "Sensor de presença"
        assert row.observacoes == "Verificar semanal"

    def test_optional_fields_none_when_empty(self, parser: PandasSpreadsheetParser) -> None:
        """Campos opcionais ficam None quando não preenchidos."""
        data = _minimal_data(
            descricao_equipamento=None,
            riscos=None,
            categoria_severidade=None,
            categoria_risco=None,
            medidas_existentes=None,
            medidas_implementar=None,
            observacoes=None,
        )
        df = _build_real_layout([data])
        rows = parser.parse(_df_to_csv_bytes(df), "dados.csv")

        row = rows[0]
        assert row.descricao_equipamento is None
        assert row.riscos is None
        assert row.categoria_severidade is None
        assert row.categoria_risco is None
        assert row.medidas_existentes is None
        assert row.medidas_implementar is None
        assert row.observacoes is None

    def test_whitespace_trimmed(self, parser: PandasSpreadsheetParser) -> None:
        """Espaços em branco ao redor de strings devem ser removidos."""
        data = _minimal_data(
            equipamento="  Torno CNC  ",
            perigo=" Projeção de peças ",
            causas=" Ausência de carenagem ",
            consequencias=" Ferimento ",
        )
        df = _build_real_layout([data])
        rows = parser.parse(_df_to_csv_bytes(df), "test.csv")

        row = rows[0]
        assert row.equipamento == "Torno CNC"
        assert row.perigo == "Projeção de peças"

    def test_multiple_rows(self, parser: PandasSpreadsheetParser) -> None:
        """Múltiplas linhas são convertidas corretamente."""
        row1 = _minimal_data(equipamento="Prensa", perigo="Esmagamento")
        row2 = _minimal_data(equipamento="Torno", perigo="Projeção")
        df = _build_real_layout([row1, row2])
        rows = parser.parse(_df_to_csv_bytes(df), "multi.csv")

        assert len(rows) == 2
        assert rows[0].equipamento == "Prensa"
        assert rows[1].equipamento == "Torno"

    def test_empty_rows_between_data_skipped(self, parser: PandasSpreadsheetParser) -> None:
        """Linhas completamente vazias entre os dados são ignoradas."""
        row1 = _minimal_data(equipamento="Prensa")
        empty = [None] * len(_REAL_COLUMNS)
        row2 = _minimal_data(equipamento="Torno")
        df = _build_real_layout([row1, empty, row2])
        rows = parser.parse(_df_to_csv_bytes(df), "gaps.csv")

        assert len(rows) == 2
        assert rows[0].equipamento == "Prensa"
        assert rows[1].equipamento == "Torno"


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
        # Cabeçalho só com duas colunas
        rows_raw: list[list] = [
            ["Equipamento", "Riscos", "Perigo", "Consequências"],
            ["Prensa", "Mecânico", "Esmag.", "Amput."],
        ]
        df = pd.DataFrame(rows_raw)
        with pytest.raises(ValidationError, match="Colunas obrigatórias ausentes"):
            parser.parse(_df_to_csv_bytes(df), "incompleto.csv")

    def test_empty_required_field(self, parser: PandasSpreadsheetParser) -> None:
        """Célula obrigatória vazia gera erro informando linha e campo."""
        data = _minimal_data(equipamento="")
        df = _build_real_layout([data])
        with pytest.raises(ValidationError, match="equipamento.*vazio"):
            parser.parse(_df_to_csv_bytes(df), "vazio.csv")

    def test_empty_spreadsheet(self, parser: PandasSpreadsheetParser) -> None:
        """Planilha sem linhas de dados deve gerar erro."""
        df = _build_real_layout([])
        with pytest.raises(ValidationError, match="planilha está vazia"):
            parser.parse(_df_to_csv_bytes(df), "vazio.csv")

    def test_none_required_field(self, parser: PandasSpreadsheetParser) -> None:
        """Campo obrigatório com None (NaN) deve lançar erro."""
        data = _minimal_data(perigo=None)
        df = _build_real_layout([data])
        with pytest.raises(ValidationError, match="perigo.*vazio"):
            parser.parse(_df_to_csv_bytes(df), "none.csv")

    def test_no_header_found(self, parser: PandasSpreadsheetParser) -> None:
        """Planilha sem linha de cabeçalho reconhecível deve gerar erro."""
        df = pd.DataFrame([
            ["Col A", "Col B", "Col C"],
            ["val1", "val2", "val3"],
        ])
        with pytest.raises(ValidationError, match="detectar a linha de cabeçalho"):
            parser.parse(_df_to_csv_bytes(df), "sem_header.csv")


# ---------------------------------------------------------------------------
# Protocolo — garante compatibilidade com SpreadsheetParserPort
# ---------------------------------------------------------------------------

class TestProtocol:
    """Verifica que a classe implementa o protocolo do domínio."""

    def test_implements_port(self) -> None:
        from app.domain.ports import SpreadsheetParserPort

        assert isinstance(PandasSpreadsheetParser(), SpreadsheetParserPort)
