"""Deduplicação de justificativas técnicas via hash SHA1 + similaridade leve.

LLM frequentemente produz justificativas duplicadas com pequenas variações
(mesmo conteúdo, ordem de palavras diferente). Este módulo:

  1. Normaliza cada justificativa (lowercase, remove pontuação, colapsa espaços).
  2. Calcula SHA1 do texto normalizado → chave de deduplicação exata.
  3. Opcionalmente, aplica trigram-jaccard ≥ 0.85 para deduplicar variações.

Operação puramente determinística.
"""
from __future__ import annotations

import hashlib
import re
from typing import Iterable, Mapping

_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WS_RE = re.compile(r"\s+")

# Prefixo boilerplate gerado pelo fallback determinístico de justificativas.
# Quando presente, todas as justificativas de um mesmo equipamento
# começam idênticas — ignoramos o prefixo para que o dedup colapse
# corretamente as duplicatas mesmo com variações em ordem de palavras.
_BOILERPLATE_PREFIX_RE = re.compile(
    r"^\s*recomenda(ç|c)(ã|a)o\s+baseada\s+na\s+an(á|a)lise\s+de\s+risco\s+do\s+equipamento\s+",
    flags=re.IGNORECASE,
)


def _normalize(text: str) -> str:
    s = text.strip().lower()
    s = _BOILERPLATE_PREFIX_RE.sub("", s)
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s)
    return s.strip()


def _hash(text: str) -> str:
    return hashlib.sha1(_normalize(text).encode("utf-8")).hexdigest()


def _trigrams(text: str) -> set[str]:
    norm = _normalize(text)
    return {norm[i : i + 3] for i in range(max(0, len(norm) - 2))}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def dedupe_justifications(
    items: Iterable[Mapping[str, object]],
    *,
    text_key: str = "texto",
    similarity_threshold: float = 0.80,
) -> list[dict[str, object]]:
    """Remove justificativas duplicadas.

    Mantém a primeira ocorrência. Anexa `_hash` (SHA1) a cada item retornado
    para rastreabilidade no PDF Preflight.
    """
    seen_hashes: set[str] = set()
    seen_trigrams: list[set[str]] = []
    out: list[dict[str, object]] = []

    for item in items:
        text = str(item.get(text_key) or "").strip()
        if not text:
            continue
        h = _hash(text)
        if h in seen_hashes:
            continue
        # Similaridade leve para variações
        tri = _trigrams(text)
        if any(_jaccard(tri, prev) >= similarity_threshold for prev in seen_trigrams):
            continue
        seen_hashes.add(h)
        seen_trigrams.append(tri)
        out.append({**dict(item), "_hash": h})
    return out
