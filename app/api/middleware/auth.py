"""Middleware de autenticação interna (API key compartilhada).

A API Python é chamada apenas pelo backend Next.js (server-to-server).
A proteção é feita via shared API key em variável de ambiente.

Se ``INTERNAL_API_KEY`` não estiver configurada, aceitamos tudo (dev mode).

Uso::

    from fastapi import Depends
    from app.api.middleware.auth import verify_internal_api_key

    @router.post("", dependencies=[Depends(verify_internal_api_key)])
    async def process_job(...):
        ...
"""

from __future__ import annotations

from fastapi import HTTPException, Request
from loguru import logger

from app.infrastructure.config import get_settings

INTERNAL_API_KEY_HEADER = "X-Internal-API-Key"


async def verify_internal_api_key(request: Request) -> None:
    """Middleware que verifica API key interna.

    Apenas o Next.js backend deve chamar a API Python.
    A key é compartilhada via variável de ambiente.

    Args:
        request: Request FastAPI.

    Raises:
        HTTPException: Se a key for inválida ou ausente.
    """
    settings = get_settings()
    expected_key = settings.INTERNAL_API_KEY

    if not expected_key:
        # Se não configurada, aceitar tudo (dev mode)
        return

    provided_key = request.headers.get(INTERNAL_API_KEY_HEADER)
    if not provided_key or provided_key != expected_key:
        logger.warning(
            "AUTH | Tentativa de acesso com API key inválida | ip={} | path={}",
            request.client.host if request.client else "unknown",
            request.url.path,
        )
        raise HTTPException(
            status_code=401,
            detail="API key interna inválida ou ausente",
        )
