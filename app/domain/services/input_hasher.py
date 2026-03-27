"""Hash de entrada para deduplicação de jobs.

Calcula um SHA-256 determinístico do payload de entrada de um job,
permitindo identificar reprocessamentos duplicados.

Uso::

    from app.domain.services.input_hasher import compute_input_hash

    hash_hex = compute_input_hash(rows, profile="dust", company_metadata=metadata)
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def compute_input_hash(
    rows: list[dict[str, Any]],
    profile: str,
    company_metadata: dict[str, Any] | None = None,
) -> str:
    """Calcula SHA-256 do input de um job para deduplicação.

    O hash é determinístico para o mesmo conjunto de dados,
    independentemente da ordem dos campos em dicts.

    Args:
        rows: Linhas da planilha normalizadas.
        profile: Perfil de processamento (dust/gas/vapors).
        company_metadata: Metadados de capa opcionais.

    Returns:
        SHA-256 hex string (64 chars).
    """
    payload = {
        "profile": profile,
        "row_count": len(rows),
        "rows_hash": hashlib.sha256(
            json.dumps(rows, sort_keys=True, default=str).encode()
        ).hexdigest(),
    }
    if company_metadata:
        payload["metadata_hash"] = hashlib.sha256(
            json.dumps(company_metadata, sort_keys=True, default=str).encode()
        ).hexdigest()

    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()
