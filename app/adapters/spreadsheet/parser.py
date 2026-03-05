"""Adaptador de parsing de planilhas usando pandas.

Converte arquivos XLSX / CSV em listas de ``MachineRiskRow``, aplicando
normalização de colunas, trimming de strings e mapeamento de aliases.
"""

from __future__ import annotations

import io
from typing import Any

import pandas as pd

from app.domain.entities import MachineRiskRow, PriorityLevel, RiskLevel
from app.domain.errors import ValidationError


# ---------------------------------------------------------------------------
# Mapeamento de aliases → nome canônico de coluna
# ---------------------------------------------------------------------------

COLUMN_ALIASES: dict[str, str] = {
    # area
    "area": "area",
    "área": "area",
    "setor": "area",
    "sector": "area",
    # equipamento
    "equipamento": "equipamento",
    "máquina": "equipamento",
    "maquina": "equipamento",
    "machine": "equipamento",
    "equipment": "equipamento",
    # perigo
    "perigo": "perigo",
    "hazard": "perigo",
    "risco_desc": "perigo",
    # causa
    "causa": "causa",
    "cause": "causa",
    "causa_raiz": "causa",
    # consequencia
    "consequencia": "consequencia",
    "consequência": "consequencia",
    "consequence": "consequencia",
    # risco
    "risco": "risco",
    "risk": "risco",
    "nivel_risco": "risco",
    "nível_risco": "risco",
    "risk_level": "risco",
    # probabilidade
    "probabilidade": "probabilidade",
    "probability": "probabilidade",
    "prob": "probabilidade",
    # severidade
    "severidade": "severidade",
    "severity": "severidade",
    "sev": "severidade",
    # norma_ref
    "norma_ref": "norma_ref",
    "norma": "norma_ref",
    "referencia_normativa": "norma_ref",
    "norm_ref": "norma_ref",
    # recomendacao
    "recomendacao": "recomendacao",
    "recomendação": "recomendacao",
    "recommendation": "recomendacao",
    # prioridade
    "prioridade": "prioridade",
    "priority": "prioridade",
    # foto_ref
    "foto_ref": "foto_ref",
    "foto": "foto_ref",
    "photo": "foto_ref",
    "evidencia": "foto_ref",
    "evidência": "foto_ref",
    # observacoes
    "observacoes": "observacoes",
    "observações": "observacoes",
    "obs": "observacoes",
    "observations": "observacoes",
    "notes": "observacoes",
}

# Campos obrigatórios em ``MachineRiskRow``.
REQUIRED_COLUMNS: set[str] = {"area", "equipamento", "perigo", "causa", "consequencia", "risco"}

# Todas as colunas válidas aceitas pelo modelo.
ALL_COLUMNS: set[str] = set(MachineRiskRow.model_fields.keys())

# Campos especiais que precisam de parse de Enum
_RISK_LEVEL_MAP: dict[str, RiskLevel] = {v.value: v for v in RiskLevel}
_PRIORITY_LEVEL_MAP: dict[str, PriorityLevel] = {v.value: v for v in PriorityLevel}


# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------

def _normalize_column_name(name: str) -> str:
    """Normaliza o nome de coluna: lower, strip, remove acentos simples."""
    return name.strip().lower()


def _resolve_aliases(columns: list[str]) -> dict[str, str]:
    """Retorna mapa {nome_original -> nome_canônico} para as colunas do DataFrame.

    Raises:
        ValidationError: se duas colunas originais mapeiam para o mesmo nome canônico.
    """
    mapping: dict[str, str] = {}
    seen_canonical: dict[str, str] = {}  # canonical -> original

    for col in columns:
        normalized = _normalize_column_name(col)
        canonical = COLUMN_ALIASES.get(normalized)
        if canonical is None:
            # Coluna desconhecida — será ignorada
            continue

        if canonical in seen_canonical:
            raise ValidationError(
                f"Colunas duplicadas mapeiam para '{canonical}': "
                f"'{seen_canonical[canonical]}' e '{col}'"
            )

        seen_canonical[canonical] = col
        mapping[col] = canonical

    return mapping


def _parse_risk_level(value: Any) -> RiskLevel:
    """Converte texto livre para ``RiskLevel``."""
    if isinstance(value, RiskLevel):
        return value

    text = str(value).strip().lower()
    level = _RISK_LEVEL_MAP.get(text)
    if level is None:
        valid = ", ".join(sorted(_RISK_LEVEL_MAP.keys()))
        raise ValidationError(
            f"Nível de risco inválido: '{value}'. Valores aceitos: {valid}"
        )
    return level


def _parse_priority_level(value: Any) -> PriorityLevel | None:
    """Converte texto livre para ``PriorityLevel`` (ou None)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, PriorityLevel):
        return value

    text = str(value).strip().lower()
    if not text:
        return None

    level = _PRIORITY_LEVEL_MAP.get(text)
    if level is None:
        valid = ", ".join(sorted(_PRIORITY_LEVEL_MAP.keys()))
        raise ValidationError(
            f"Prioridade inválida: '{value}'. Valores aceitos: {valid}"
        )
    return level


def _cell_to_optional_str(value: Any) -> str | None:
    """Converte valor de célula para string (ou None se vazio/NaN)."""
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


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class PandasSpreadsheetParser:
    """Parser de planilhas (XLSX / CSV) que retorna ``list[MachineRiskRow]``.

    Implementa ``SpreadsheetParserPort``.

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
        df = self._read_dataframe(file_bytes, filename)
        df = self._normalize_dataframe(df)
        return self._convert_rows(df)

    # ------------------------------------------------------------------
    # Etapas internas
    # ------------------------------------------------------------------

    @staticmethod
    def _read_dataframe(file_bytes: bytes, filename: str) -> pd.DataFrame:
        """Lê os bytes como DataFrame de acordo com a extensão do arquivo."""
        lower = filename.strip().lower()
        buffer = io.BytesIO(file_bytes)

        if lower.endswith(".xlsx"):
            try:
                return pd.read_excel(buffer, engine="openpyxl")
            except Exception as exc:
                raise ValidationError(
                    f"Falha ao ler arquivo Excel '{filename}': {exc}"
                ) from exc

        if lower.endswith(".csv"):
            try:
                buffer_text = io.StringIO(file_bytes.decode("utf-8"))
                return pd.read_csv(buffer_text)
            except UnicodeDecodeError:
                buffer_text = io.StringIO(file_bytes.decode("latin-1"))
                return pd.read_csv(buffer_text)
            except Exception as exc:
                raise ValidationError(
                    f"Falha ao ler arquivo CSV '{filename}': {exc}"
                ) from exc

        raise ValidationError(
            f"Formato de arquivo não suportado: '{filename}'. "
            "Apenas .xlsx e .csv são aceitos."
        )

    @staticmethod
    def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        """Normaliza colunas (aliases) e valores (trim / NaN → None)."""
        if df.empty:
            raise ValidationError("A planilha está vazia (sem linhas de dados).")

        # Resolver aliases
        alias_map = _resolve_aliases(list(df.columns.astype(str)))
        df = df.rename(columns=alias_map)

        # Manter apenas colunas conhecidas
        known = [c for c in df.columns if c in ALL_COLUMNS]
        df = df[known]

        # Verificar colunas obrigatórias
        present = set(df.columns)
        missing = REQUIRED_COLUMNS - present
        if missing:
            raise ValidationError(
                f"Colunas obrigatórias ausentes na planilha: {sorted(missing)}"
            )

        # Trim em colunas de texto
        for col in df.select_dtypes(include=["object", "string"]).columns:
            df[col] = df[col].map(
                lambda v: v.strip() if isinstance(v, str) else v
            )

        # NaN → None
        df = df.where(pd.notna(df), None)

        return df

    @staticmethod
    def _convert_rows(df: pd.DataFrame) -> list[MachineRiskRow]:
        """Converte cada linha do DataFrame normalizado em ``MachineRiskRow``."""
        rows: list[MachineRiskRow] = []

        for idx, record in df.iterrows():
            row_idx = int(idx)  # type: ignore[arg-type]
            try:
                row = MachineRiskRow(
                    area=_cell_to_str(record.get("area"), "area", row_idx),
                    equipamento=_cell_to_str(record.get("equipamento"), "equipamento", row_idx),
                    perigo=_cell_to_str(record.get("perigo"), "perigo", row_idx),
                    causa=_cell_to_str(record.get("causa"), "causa", row_idx),
                    consequencia=_cell_to_str(record.get("consequencia"), "consequencia", row_idx),
                    risco=_parse_risk_level(
                        _cell_to_str(record.get("risco"), "risco", row_idx)
                    ),
                    probabilidade=_cell_to_optional_str(record.get("probabilidade")),
                    severidade=_cell_to_optional_str(record.get("severidade")),
                    norma_ref=_cell_to_optional_str(record.get("norma_ref")),
                    recomendacao=_cell_to_optional_str(record.get("recomendacao")),
                    prioridade=_parse_priority_level(record.get("prioridade")),
                    foto_ref=_cell_to_optional_str(record.get("foto_ref")),
                    observacoes=_cell_to_optional_str(record.get("observacoes")),
                )
            except ValidationError:
                raise
            except Exception as exc:
                raise ValidationError(
                    f"Erro ao processar linha {row_idx + 1}: {exc}"
                ) from exc

            rows.append(row)

        return rows
