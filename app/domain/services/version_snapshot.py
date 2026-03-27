"""Fingerprint de versão do pipeline para reprodutibilidade.

Calcula hashes do prompt e schema para identificar a configuração
que gerou cada laudo. Permite rastreabilidade e auditoria.

Uso::

    from app.domain.services.version_snapshot import compute_version_fingerprint

    prompt_hash, schema_hash = compute_version_fingerprint(
        system_prompt=prompt_text,
        output_schema=schema_dict,
        rag_config={"top_k": 8, "max_chunks": 5, "min_score": 0.15},
        llm_model="openai/gpt-4o",
        embedding_model="text-embedding-3-small",
    )
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def compute_version_fingerprint(
    system_prompt: str,
    output_schema: dict[str, Any],
    rag_config: dict[str, Any],
    llm_model: str,
    embedding_model: str,
) -> tuple[str, str]:
    """Calcula hashes do prompt e schema para identificar a versão.

    Args:
        system_prompt: Texto completo do system prompt.
        output_schema: Schema JSON de saída esperado.
        rag_config: Configuração do RAG (top_k, max_chunks, min_score).
        llm_model: Identificador do modelo LLM.
        embedding_model: Identificador do modelo de embedding.

    Returns:
        Tupla (prompt_hash, schema_hash).
    """
    prompt_hash = hashlib.sha256(system_prompt.encode()).hexdigest()
    schema_hash = hashlib.sha256(
        json.dumps(output_schema, sort_keys=True).encode()
    ).hexdigest()
    return prompt_hash, schema_hash
