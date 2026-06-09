"""Formatação canônica de referências normativas.

Converte variantes comuns (NBR-XYZ, NBR/IEC XYZ, etc.) na forma canônica
"ABNT NBR ISO XXX:AAAA", "ABNT NBR IEC YYY:AAAA", "NFPA ZZZ", "IEC AAAA".

Não invalida normas — apenas normaliza ortografia.
"""
from __future__ import annotations

import re

# Captura: prefixo opcional "ABNT", NBR opcional, ISO|IEC opcional, número, ano opcional
_NBR_PATTERN = re.compile(
    r"\b(?:ABNT\s*)?NBR[\s-]*(ISO|IEC)?[\s-]*(\d{3,5})(?:\s*[:\-/]\s*(\d{4}))?\b",
    re.IGNORECASE,
)
_NFPA_PATTERN = re.compile(r"\bNFPA[\s-]*(\d{2,4})(?:\s*[:\-/]\s*(\d{4}))?\b", re.IGNORECASE)
_IEC_PATTERN = re.compile(r"\bIEC[\s-]*(\d{4,5})(?:[\s-]+(\d+))?(?:\s*[:\-/]\s*(\d{4}))?\b", re.IGNORECASE)
_NR_PATTERN = re.compile(r"\bNR[\s-]*0?(\d{1,2})\b", re.IGNORECASE)


def _format_nbr(match: re.Match[str]) -> str:
    sub = (match.group(1) or "").upper()
    num = match.group(2)
    year = match.group(3)
    parts = ["ABNT", "NBR"]
    if sub:
        parts.append(sub)
    parts.append(num)
    base = " ".join(parts)
    return f"{base}:{year}" if year else base


def _format_nfpa(match: re.Match[str]) -> str:
    num = match.group(1)
    year = match.group(2)
    base = f"NFPA {num}"
    return f"{base}:{year}" if year else base


def _format_iec(match: re.Match[str]) -> str:
    num = match.group(1)
    part = match.group(2)
    year = match.group(3)
    base = f"IEC {num}"
    if part:
        base = f"{base}-{part}"
    return f"{base}:{year}" if year else base


def _format_nr(match: re.Match[str]) -> str:
    return f"NR-{int(match.group(1))}"


def format_normative_reference(text: str) -> str:
    """Aplica formatação canônica a todas as citações de norma no texto."""
    if not text:
        return text
    out = _NBR_PATTERN.sub(_format_nbr, text)
    out = _NFPA_PATTERN.sub(_format_nfpa, out)
    out = _IEC_PATTERN.sub(_format_iec, out)
    out = _NR_PATTERN.sub(_format_nr, out)
    return out
