"""Filtro de contaminação — remove boilerplate de normas/RAG leaked em narrativas.

Carrega `config/contamination_patterns.yaml` e remove ocorrências de padrões
identificados como "vazamento" do RAG (citação literal de norma onde devia
haver análise contextualizada).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "contamination_patterns.yaml"
)


@dataclass(frozen=True)
class _ContaminationRule:
    name: str
    pattern: re.Pattern[str]
    replacement: str


@lru_cache(maxsize=1)
def _load_rules() -> tuple[_ContaminationRule, ...]:
    if not _CONFIG_PATH.is_file():
        return ()
    raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    rules: list[_ContaminationRule] = []
    for item in raw.get("patterns", []) or []:
        rules.append(
            _ContaminationRule(
                name=str(item.get("name", "")),
                pattern=re.compile(str(item["regex"])),
                replacement=str(item.get("replacement", "")),
            )
        )
    return tuple(rules)


_MULTI_SPACE_RE = re.compile(r"\s{2,}")
_LEADING_PUNCT_RE = re.compile(r"^\s*[.,;:]\s*")


def filter_contamination(text: str) -> str:
    """Remove ocorrências de padrões de contaminação e re-justifica o texto."""
    if not text:
        return text
    out = text
    for rule in _load_rules():
        out = rule.pattern.sub(rule.replacement, out)
    # Cleanup de espaços/pontuação resultantes
    out = _MULTI_SPACE_RE.sub(" ", out)
    out = _LEADING_PUNCT_RE.sub("", out)
    return out.strip()


def reset_cache() -> None:
    _load_rules.cache_clear()
