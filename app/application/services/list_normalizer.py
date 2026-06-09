"""Normalização de listas — pontuação consistente, paralelismo, capitalização.

Aplicado a campos textuais de listas (recomendações, justificativas, observações).
Não invoca LLM — operação puramente determinística.
"""
from __future__ import annotations

import re
from typing import Iterable


_BULLET_TRAIL_RE = re.compile(r"\s*[,;]\s*$")
_MULTI_SPACE_RE = re.compile(r"\s{2,}")


def normalize_list_item(text: str, *, end_with_period: bool = True) -> str:
    """Normaliza um item de lista.

    Regras:
      • Strip + colapsa espaços múltiplos.
      • Capitaliza primeira letra (preservando siglas/acrônimos).
      • Garante terminação consistente: ponto final (default) ou nada.
      • Remove vírgula/ponto-e-vírgula final espúrios antes de aplicar ponto.
    """
    if not text:
        return ""
    s = text.strip()
    s = _MULTI_SPACE_RE.sub(" ", s)
    s = _BULLET_TRAIL_RE.sub("", s)

    # Capitalização apenas da 1ª letra se for minúscula simples (preserva siglas)
    if s and s[0].islower():
        s = s[0].upper() + s[1:]

    if end_with_period:
        if not s.endswith((".", "!", "?", ":")):
            s += "."
    return s


def normalize_list(items: Iterable[str], *, end_with_period: bool = True) -> list[str]:
    """Aplica `normalize_list_item` a cada item, removendo vazios e duplicatas
    (case-insensitive, preservando primeira ocorrência)."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in items:
        normalized = normalize_list_item(raw, end_with_period=end_with_period)
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(normalized)
    return out
