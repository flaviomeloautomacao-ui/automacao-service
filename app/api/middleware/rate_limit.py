"""Rate limiting simples em memória para jobs.

Limita a frequência de criação/processamento de jobs para
proteger contra uso abusivo.

Suficiente para single-instance. Para escalar, migrar para Redis.

Uso::

    from fastapi import Depends
    from app.api.middleware.rate_limit import rate_limit_jobs

    @router.post("", dependencies=[Depends(rate_limit_jobs)])
    async def process_job(...):
        ...
"""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException, Request
from loguru import logger

# Rate limit simples em memória (suficiente para single-instance)
_job_timestamps: dict[str, list[float]] = defaultdict(list)
MAX_JOBS_PER_MINUTE = 10
MAX_JOBS_PER_HOUR = 50


async def rate_limit_jobs(request: Request) -> None:
    """Limita a frequência de criação/processamento de jobs.

    Args:
        request: Request FastAPI.

    Raises:
        HTTPException: Se o rate limit for excedido (429).
    """
    now = time.time()
    key = "global"  # Para multi-tenant, usar user_id

    # Limpar timestamps antigos (> 1 hora)
    _job_timestamps[key] = [
        t for t in _job_timestamps[key] if now - t < 3600
    ]

    recent_minute = sum(1 for t in _job_timestamps[key] if now - t < 60)
    recent_hour = len(_job_timestamps[key])

    if recent_minute >= MAX_JOBS_PER_MINUTE:
        logger.warning(
            "RATE_LIMIT | Excedido: {}/{} jobs/min | ip={}",
            recent_minute,
            MAX_JOBS_PER_MINUTE,
            request.client.host if request.client else "unknown",
        )
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit: {MAX_JOBS_PER_MINUTE} jobs/minuto excedido",
        )
    if recent_hour >= MAX_JOBS_PER_HOUR:
        logger.warning(
            "RATE_LIMIT | Excedido: {}/{} jobs/hora | ip={}",
            recent_hour,
            MAX_JOBS_PER_HOUR,
            request.client.host if request.client else "unknown",
        )
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit: {MAX_JOBS_PER_HOUR} jobs/hora excedido",
        )

    _job_timestamps[key].append(now)
