"""Validador da matriz de risco DHA — carrega configuração e classifica
cruzamento (Severidade × Probabilidade) → Categoria.

Default: 3×3 conforme `config/risk_matrix.yaml`. Estrutura permite trocar
para 5×5 sem alterar código.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "risk_matrix.yaml"
)


class RiskMatrixError(ValueError):
    """Erro em configuração ou classificação inválida."""


@dataclass(frozen=True)
class RiskMatrixConfig:
    dimension: int
    severity_categories: tuple[str, ...]
    probability_categories: tuple[str, ...]
    matrix: tuple[tuple[str, ...], ...]
    severity_aliases: dict[str, str]
    probability_aliases: dict[str, str]

    def classify(self, severity: str, probability: str) -> str:
        sev = self._canonical_severity(severity)
        prob = self._canonical_probability(probability)
        try:
            row = self.severity_categories.index(sev)
            col = self.probability_categories.index(prob)
            return self.matrix[row][col]
        except (ValueError, IndexError) as exc:
            raise RiskMatrixError(
                f"Cruzamento inválido: severity={severity!r}, probability={probability!r}"
            ) from exc

    def _canonical_severity(self, value: str) -> str:
        key = (value or "").strip()
        return self.severity_aliases.get(key.lower(), key)

    def _canonical_probability(self, value: str) -> str:
        key = (value or "").strip()
        return self.probability_aliases.get(key.lower(), key)


def _build_alias_map(aliases_block: dict[str, list[str]] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for canonical, variants in (aliases_block or {}).items():
        for v in variants or []:
            out[str(v).strip().lower()] = canonical
        out[canonical.strip().lower()] = canonical
    return out


@lru_cache(maxsize=1)
def load_risk_matrix() -> RiskMatrixConfig:
    if not _CONFIG_PATH.is_file():
        raise RiskMatrixError(f"Configuração não encontrada: {_CONFIG_PATH}")
    raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    sev_cats = tuple(raw.get("severity_categories", []) or [])
    prob_cats = tuple(raw.get("probability_categories", []) or [])
    matrix_rows = raw.get("matrix", []) or []
    matrix = tuple(tuple(row) for row in matrix_rows)
    dim = int(raw.get("dimension", len(sev_cats)))
    if len(sev_cats) != dim or len(prob_cats) != dim or len(matrix) != dim:
        raise RiskMatrixError("Dimensões inconsistentes em risk_matrix.yaml")
    for row in matrix:
        if len(row) != dim:
            raise RiskMatrixError("Linha da matriz com tamanho ≠ dimension")
    aliases = raw.get("aliases", {}) or {}
    return RiskMatrixConfig(
        dimension=dim,
        severity_categories=sev_cats,
        probability_categories=prob_cats,
        matrix=matrix,
        severity_aliases=_build_alias_map(aliases.get("severity")),
        probability_aliases=_build_alias_map(aliases.get("probability")),
    )


def reset_cache() -> None:
    load_risk_matrix.cache_clear()
