"""Adaptador de parsing de planilhas usando pandas.

Converte arquivos XLSX / CSV em listas de ``MachineRiskRow``, lidando
com o layout real da planilha padrão de análise de risco:

- Detecção automática do cabeçalho (linhas vazias antes do header).
- Remoção de colunas totalmente vazias e da coluna auxiliar "Coluna1".
- Mapeamento de nomes de coluna da planilha → campos normalizados.
- Preservação de conteúdo multiline nas células.
- Logging de debug em cada etapa do pipeline.
"""

from __future__ import annotations

import io
import re
from typing import Any

import pandas as pd
from loguru import logger

from app.domain.entities import MachineRiskRow
from app.domain.errors import ValidationError


def _normalize_ws(text: str) -> str:
    """Normaliza whitespace: troca NBSP/tabs/newlines por espaço, colapsa múltiplos, trim."""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


# ---------------------------------------------------------------------------
# Mapeamento coluna-planilha → campo normalizado
# ---------------------------------------------------------------------------

COLUMN_MAP: dict[str, str] = {
    "equipamento": "equipamento",
    "descrição do equipamento": "descricao_equipamento",
    "descricao do equipamento": "descricao_equipamento",
    "riscos": "riscos",
    "perigo": "perigo",
    "causas possíveis": "causas",
    "causas possiveis": "causas",
    "causas": "causas",
    "consequências": "consequencias",
    "consequencias": "consequencias",
    "categoria da severidade": "categoria_severidade",
    "categoria do risco": "categoria_risco",
    # V3 — novos campos
    "categoria da probabilidade": "categoria_probabilidade",
    "classificação do risco": "classificacao_risco",
    "classificacao do risco": "classificacao_risco",           # sem acento
    "categoria da severidade 2": "categoria_severidade_2",
    "categoria da probabilidade 2": "categoria_probabilidade_2",
    "categoria do risco 2": "categoria_probabilidade_2",       # alias V1 residual
    "categoria de probabilidade 2": "categoria_probabilidade_2", # variação "de"
    "classificação do risco 2": "classificacao_risco_2",
    "classificacao do risco 2": "classificacao_risco_2",       # sem acento
    "medidas preventivas existentes": "medidas_existentes",
    "medidas preventivas a implementar": "medidas_implementar",
    "observações": "observacoes",
    "observacoes": "observacoes",
}

#: Tokens usados para detectar a linha de cabeçalho.
#: V1 e V3 contêm todos estes tokens no cabeçalho.
_HEADER_TOKENS: set[str] = {"equipamento", "riscos", "perigo", "consequências"}

#: Campos obrigatórios que devem estar presentes como colunas.
REQUIRED_COLUMNS: set[str] = {"equipamento", "perigo", "causas", "consequencias"}

#: Todas as colunas aceitas pelo modelo ``MachineRiskRow``.
ALL_COLUMNS: set[str] = set(MachineRiskRow.model_fields.keys())


# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------

def _cell_to_optional_str(value: Any) -> str | None:
    """Converte valor de célula para string (ou None se vazio/NaN).

    Preserva conteúdo multiline.
    """
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def _cell_to_str(value: Any, field: str, row_index: int) -> str:
    """Converte valor de célula para string não-vazia, ou lança erro."""
    result = _cell_to_optional_str(value)
    if not result:
        raise ValidationError(
            f"Linha {row_index + 1}: campo obrigatório '{field}' está vazio."
        )
    return result


def _is_empty_row(row: pd.Series) -> bool:
    """Retorna True se todos os valores da linha forem nulos ou vazios."""
    for v in row:
        if v is None:
            continue
        if isinstance(v, float) and pd.isna(v):
            continue
        if isinstance(v, str) and not v.strip():
            continue
        return False
    return True


def _detect_header_row(df_raw: pd.DataFrame) -> int:
    """Encontra o índice da linha que contém os tokens do cabeçalho.

    Procura a primeira linha cujas células (normalizadas: lower + whitespace robusto)
    contêm simultaneamente todos os tokens em ``_HEADER_TOKENS``.

    Returns:
        Índice (0-based) da linha de cabeçalho.

    Raises:
        ValidationError: se nenhuma linha válida for encontrada.
    """
    for row_idx in range(len(df_raw)):
        cells = set()
        for v in df_raw.iloc[row_idx]:
            if isinstance(v, str):
                cells.add(_normalize_ws(v).lower())
        if _HEADER_TOKENS.issubset(cells):
            logger.debug("Cabeçalho detectado na linha {} (0-based)", row_idx)
            return row_idx

    raise ValidationError(
        "Não foi possível detectar a linha de cabeçalho na planilha. "
        "Esperava-se uma linha contendo simultaneamente: "
        + ", ".join(sorted(_HEADER_TOKENS))
    )


def _normalize_columns(columns: list[str]) -> dict[str, str]:
    """Retorna mapa {nome_original → campo_normalizado} a partir de ``COLUMN_MAP``.

    Colunas que não batem no mapa são ignoradas (ex.: ``Coluna1``).
    Usa normalização robusta de whitespace (NBSP, tabs, múltiplos espaços).
    """
    mapping: dict[str, str] = {}
    for col in columns:
        key = _normalize_ws(col).lower()
        canonical = COLUMN_MAP.get(key)
        if canonical is not None:
            mapping[col] = canonical
        else:
            logger.debug("Coluna ignorada (sem mapeamento): '{}'", col)
    return mapping


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class PandasSpreadsheetParser:
    """Parser de planilhas (XLSX / CSV) que retorna ``list[MachineRiskRow]``.

    Implementa ``SpreadsheetParserPort``.

    Suporta o layout real da planilha padrão de análise de risco, incluindo
    linhas vazias antes do cabeçalho, colunas auxiliares e conteúdo multiline.

    Uso::

        parser = PandasSpreadsheetParser()
        rows = parser.parse(file_bytes, "riscos.xlsx")
    """

    def parse(self, file_bytes: bytes, filename: str) -> list[MachineRiskRow]:
        """Lê os bytes do arquivo e retorna linhas normalizadas.

        Args:
            file_bytes: conteúdo cru do arquivo.
            filename: nome original (usado para inferir formato .xlsx / .csv).

        Returns:
            Lista de ``MachineRiskRow``.

        Raises:
            ValidationError: se formato não suportado, colunas obrigatórias
                faltando ou dados inválidos.
        """
        df_raw = self._read_raw(file_bytes, filename)
        logger.debug("DataFrame bruto: shape={}", df_raw.shape)

        df = self._detect_and_set_header(df_raw)
        df = self._cleanup_columns(df)
        df = self._normalize_and_filter(df)
        return self._convert_rows(df)

    # ------------------------------------------------------------------
    # Etapas internas
    # ------------------------------------------------------------------

    @staticmethod
    def _read_raw(file_bytes: bytes, filename: str) -> pd.DataFrame:
        """Lê os bytes sem interpretar cabeçalho (``header=None``)."""
        lower = filename.strip().lower()
        buffer = io.BytesIO(file_bytes)

        if lower.endswith(".xlsx"):
            try:
                return pd.read_excel(buffer, engine="openpyxl", header=None)
            except Exception as exc:
                raise ValidationError(
                    f"Falha ao ler arquivo Excel '{filename}': {exc}"
                ) from exc

        if lower.endswith(".csv"):
            try:
                buffer_text = io.StringIO(file_bytes.decode("utf-8"))
                return pd.read_csv(buffer_text, header=None)
            except UnicodeDecodeError:
                buffer_text = io.StringIO(file_bytes.decode("latin-1"))
                return pd.read_csv(buffer_text, header=None)
            except Exception as exc:
                raise ValidationError(
                    f"Falha ao ler arquivo CSV '{filename}': {exc}"
                ) from exc

        raise ValidationError(
            f"Formato de arquivo não suportado: '{filename}'. "
            "Apenas .xlsx e .csv são aceitos."
        )

    @staticmethod
    def _detect_and_set_header(df_raw: pd.DataFrame) -> pd.DataFrame:
        """Detecta a linha de cabeçalho e retorna DataFrame com dados abaixo dela."""
        header_idx = _detect_header_row(df_raw)

        # Usa a linha detectada como nomes de coluna (normaliza whitespace)
        header_values = [
            _normalize_ws(str(v)) if pd.notna(v) else f"__empty_{i}"
            for i, v in enumerate(df_raw.iloc[header_idx])
        ]
        df = df_raw.iloc[header_idx + 1:].copy()
        df.columns = header_values
        df = df.reset_index(drop=True)

        logger.debug(
            "Colunas após detecção do cabeçalho: {}",
            list(df.columns),
        )
        return df

    @staticmethod
    def _cleanup_columns(df: pd.DataFrame) -> pd.DataFrame:
        """Remove colunas totalmente vazias, colunas auxiliares e a primeira coluna vazia.

        Não remove colunas que possuem mapeamento conhecido em ``COLUMN_MAP``
        (mesmo que estejam sem dados), pois a validação posterior tratará
        campos obrigatórios vazios.
        """
        cols_to_drop: list[str] = []

        for col in df.columns:
            col_str = _normalize_ws(str(col)).lower()

            # Coluna auxiliar "Coluna1"
            if col_str == "coluna1":
                cols_to_drop.append(col)
                continue

            # Colunas cujo nome é placeholder vazio
            if col_str.startswith("__empty_"):
                cols_to_drop.append(col)
                continue

            # Só remove por "dados vazios" se a coluna NÃO tiver mapeamento
            if col_str not in COLUMN_MAP:
                if df[col].dropna().astype(str).str.strip().replace("", pd.NA).dropna().empty:
                    cols_to_drop.append(col)
                    continue

        if cols_to_drop:
            logger.debug("Colunas removidas: {}", cols_to_drop)
            df = df.drop(columns=cols_to_drop)

        return df

    @staticmethod
    def _normalize_and_filter(df: pd.DataFrame) -> pd.DataFrame:
        """Mapeia nomes de coluna, filtra apenas cols conhecidas e remove linhas vazias."""
        if df.empty:
            raise ValidationError("A planilha está vazia (sem linhas de dados).")

        # Mapear nomes
        col_map = _normalize_columns(list(df.columns.astype(str)))
        df = df.rename(columns=col_map)

        # Manter apenas colunas conhecidas
        known = [c for c in df.columns if c in ALL_COLUMNS]
        df = df[known]

        logger.debug("Colunas normalizadas finais: {}", list(df.columns))

        # Verificar colunas obrigatórias
        present = set(df.columns)
        missing = REQUIRED_COLUMNS - present
        if missing:
            raise ValidationError(
                f"Colunas obrigatórias ausentes na planilha: {sorted(missing)}"
            )

        # NaN → None
        df = df.where(pd.notna(df), None)

        # Remover linhas completamente vazias
        original_len = len(df)
        df = df[~df.apply(_is_empty_row, axis=1)]
        df = df.reset_index(drop=True)
        removed = original_len - len(df)
        if removed:
            logger.debug("{} linha(s) vazia(s) removida(s)", removed)

        if df.empty:
            raise ValidationError("A planilha está vazia (sem linhas de dados após filtro).")

        logger.debug("Total de linhas válidas: {}", len(df))
        return df

    @staticmethod
    def _convert_rows(df: pd.DataFrame) -> list[MachineRiskRow]:
        """Converte cada linha do DataFrame normalizado em ``MachineRiskRow``."""
        rows: list[MachineRiskRow] = []

        for idx, record in df.iterrows():
            row_idx = int(idx)  # type: ignore[arg-type]
            try:
                row = MachineRiskRow(
                    equipamento=_cell_to_str(
                        record.get("equipamento"), "equipamento", row_idx
                    ),
                    descricao_equipamento=_cell_to_optional_str(
                        record.get("descricao_equipamento")
                    ),
                    riscos=_cell_to_optional_str(record.get("riscos")),
                    perigo=_cell_to_str(
                        record.get("perigo"), "perigo", row_idx
                    ),
                    causas=_cell_to_str(
                        record.get("causas"), "causas", row_idx
                    ),
                    consequencias=_cell_to_str(
                        record.get("consequencias"), "consequencias", row_idx
                    ),
                    categoria_severidade=_cell_to_optional_str(
                        record.get("categoria_severidade")
                    ),
                    categoria_risco=_cell_to_optional_str(
                        record.get("categoria_risco")
                    ),
                    # V3 — avaliação atual
                    categoria_probabilidade=_cell_to_optional_str(
                        record.get("categoria_probabilidade")
                    ),
                    classificacao_risco=_cell_to_optional_str(
                        record.get("classificacao_risco")
                    ),
                    # V3 — avaliação residual
                    categoria_severidade_2=_cell_to_optional_str(
                        record.get("categoria_severidade_2")
                    ),
                    categoria_probabilidade_2=_cell_to_optional_str(
                        record.get("categoria_probabilidade_2")
                    ),
                    classificacao_risco_2=_cell_to_optional_str(
                        record.get("classificacao_risco_2")
                    ),
                    medidas_existentes=_cell_to_optional_str(
                        record.get("medidas_existentes")
                    ),
                    medidas_implementar=_cell_to_optional_str(
                        record.get("medidas_implementar")
                    ),
                    observacoes=_cell_to_optional_str(
                        record.get("observacoes")
                    ),
                )
            except ValidationError:
                raise
            except Exception as exc:
                raise ValidationError(
                    f"Erro ao processar linha {row_idx + 1}: {exc}"
                ) from exc

            rows.append(row)

        logger.debug("Conversão finalizada: {} MachineRiskRow criadas", len(rows))
        return rows
