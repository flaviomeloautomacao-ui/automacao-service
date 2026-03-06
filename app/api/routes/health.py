"""Rota de health-check.

Endpoint(s) para verificação de saúde do serviço (liveness / readiness).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.infrastructure.config import Settings
from app.infrastructure.dependencies import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """Verifica se o serviço está no ar.

    Returns:
        JSON com ``status`` e ``env`` atuais.
    """
    return {
        "status": "ok",
        "env": settings.ENV,
    }
