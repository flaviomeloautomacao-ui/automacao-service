"""Utilitário para parsing de JSON retornado pelo LLM.

Lida com respostas envolvidas em blocos markdown (```json ... ```)
e valida que o resultado é um dicionário.
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger


def parse_llm_json(raw: str) -> dict[str, Any] | None:
    """Parseia string JSON, lidando com blocos markdown ``` ```.

    Remove blocos de código markdown que modelos LLM frequentemente
    adicionam ao redor do JSON.

    Args:
        raw: String bruta retornada pelo LLM.

    Returns:
        Dicionário parseado ou ``None`` se inválido.
    """
    cleaned = raw.strip()

    # Remover blocos markdown ```json ... ```
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        start = 1 if lines[0].startswith("```") else 0
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        cleaned = "\n".join(lines[start:end]).strip()

    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Falha ao parsear JSON da resposta LLM.")
        return None

    if not isinstance(data, dict):
        logger.warning("Resposta LLM não é um objeto JSON (dict).")
        return None

    return data
