"""Proteção contra gastos LLM descontrolados.

Verifica limites ANTES de cada chamada LLM e pode abortar o job
se o custo acumulado exceder os thresholds configurados.

Uso::

    from app.domain.services.budget_guard import BudgetGuard

    guard = BudgetGuard(settings)
    guard.check_job_budget(current_cost=0.45, current_calls=12, job_id="abc")
    await guard.check_daily_budget(session)
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from loguru import logger

from app.domain.errors import BudgetExceededError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.infrastructure.config import Settings


class BudgetGuard:
    """Proteção contra gastos LLM descontrolados.

    Verifica limites ANTES de cada chamada LLM e pode abortar o job
    se o custo acumulado exceder os thresholds configurados.

    Args:
        settings: Configurações da aplicação (usado para defaults).
    """

    def __init__(self, settings: "Settings | None" = None) -> None:
        self._max_cost_per_job: float = float(
            os.environ.get("LLM_MAX_COST_PER_JOB_USD", "2.00")
        )
        self._max_cost_per_day: float = float(
            os.environ.get("LLM_MAX_COST_PER_DAY_USD", "50.00")
        )
        self._max_calls_per_job: int = int(
            os.environ.get("LLM_MAX_CALLS_PER_JOB", "100")
        )

    def check_job_budget(
        self,
        current_cost: float,
        current_calls: int,
        job_id: str,
    ) -> None:
        """Verifica se o job ainda está dentro do budget.

        Args:
            current_cost: Custo acumulado do job em USD.
            current_calls: Número de chamadas LLM realizadas.
            job_id: ID do job para logging.

        Raises:
            BudgetExceededError: Se ultrapassou algum limite.
        """
        if current_cost > self._max_cost_per_job:
            raise BudgetExceededError(
                f"Job {job_id} excedeu limite de custo: "
                f"${current_cost:.4f} > ${self._max_cost_per_job:.2f}"
            )
        if current_calls > self._max_calls_per_job:
            raise BudgetExceededError(
                f"Job {job_id} excedeu limite de chamadas: "
                f"{current_calls} > {self._max_calls_per_job}"
            )

        logger.debug(
            "Job {} | BUDGET_CHECK | cost=${:.4f}/{:.2f} | calls={}/{}",
            job_id,
            current_cost,
            self._max_cost_per_job,
            current_calls,
            self._max_calls_per_job,
        )

    async def check_daily_budget(
        self,
        session: "AsyncSession",
    ) -> None:
        """Consulta custo acumulado nas últimas 24h e verifica teto.

        Usa os campos pré-agregados em ``jobs`` para query rápida.

        Args:
            session: Sessão SQLAlchemy async.

        Raises:
            BudgetExceededError: Se custo diário excedeu o limite.
        """
        from sqlalchemy import func as sqla_func
        from sqlalchemy import select

        from app.adapters.db.job_models import Job as JobModel

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        result = await session.execute(
            select(sqla_func.coalesce(sqla_func.sum(JobModel.llm_cost_usd), 0.0))
            .where(JobModel.created_at >= cutoff)
            .where(JobModel.llm_cost_usd.isnot(None))
        )
        daily_cost = result.scalar_one()

        logger.info(
            "BUDGET_CHECK | daily_cost=${:.4f} | limit=${:.2f}",
            daily_cost,
            self._max_cost_per_day,
        )

        if daily_cost > self._max_cost_per_day:
            raise BudgetExceededError(
                f"Custo diário excedido: ${daily_cost:.4f} > ${self._max_cost_per_day:.2f}"
            )
