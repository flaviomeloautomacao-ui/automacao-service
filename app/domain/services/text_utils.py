"""Utilitários de texto compartilhados entre módulos de domínio.

Funções reutilizáveis para split de campos multivalorados e
deduplicação de listas.
"""

from __future__ import annotations

import re

_SPLIT_PATTERN = re.compile(r"[;\n•]+")


def split_field(text: str | None) -> list[str]:
    """Divide um campo de texto em itens individuais.

    Separa por ``;``, ``\\n`` ou ``•`` e remove vazios.

    Args:
        text: Texto a dividir (pode ser None).

    Returns:
        Lista de strings limpas, sem vazios.
    """
    if not text:
        return []
    parts = _SPLIT_PATTERN.split(text)
    return [p.strip().lstrip("- ").strip() for p in parts if p.strip()]


def append_unique(lst: list[str], items: list[str]) -> None:
    """Adiciona itens que ainda não existem na lista.

    Preserva ordem de inserção e realiza strip em cada item.

    Args:
        lst: Lista destino (mutada in-place).
        items: Itens a adicionar.
    """
    for item in items:
        cleaned = item.strip()
        if cleaned and cleaned not in lst:
            lst.append(cleaned)
