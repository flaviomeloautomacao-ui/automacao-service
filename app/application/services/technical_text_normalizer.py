"""Normalização de texto técnico — typos, variantes e formatação.

Carrega `config/typo_dictionary.yaml` (cacheado) e aplica substituições
case-insensitive com word-boundary. Operação puramente determinística.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Mapping

import yaml

_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "typo_dictionary.yaml"
)


@lru_cache(maxsize=1)
def _load_substitutions() -> tuple[tuple[re.Pattern[str], str], ...]:
    if not _CONFIG_PATH.is_file():
        return ()
    raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    subs: Mapping[str, str] = raw.get("substitutions", {}) or {}
    compiled: list[tuple[re.Pattern[str], str]] = []
    for bad, good in subs.items():
        # word-boundary apenas se a chave começa/termina com caractere de palavra
        pattern = re.compile(
            rf"(?<!\w){re.escape(bad)}(?!\w)" if bad and bad[0].isalnum() else re.escape(bad),
            re.IGNORECASE,
        )
        compiled.append((pattern, good))
    return tuple(compiled)


def normalize_technical_text(text: str) -> str:
    """Aplica todas as substituições do dicionário ao texto."""
    if not text:
        return text
    out = text
    for pattern, replacement in _load_substitutions():
        out = pattern.sub(replacement, out)
    return out


def reset_cache() -> None:
    """Para testes / reload de configuração."""
    _load_substitutions.cache_clear()
