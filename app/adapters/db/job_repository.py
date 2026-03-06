"""Repositório para atualização de Jobs e Steps.

Usado pelo serviço de processamento para reportar progresso
diretamente no banco de dados compartilhado com o Next.js.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.db.job_models import Job, JobStep
from app.domain.errors import DBError


class JobRepository:
    """Repositório de Jobs/Steps — atualiza progresso de processamento.

    Args:
        session: Sessão SQLAlchemy async.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Job
    # ------------------------------------------------------------------

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Busca um job pelo UUID.

        Returns:
            Dict com dados do job ou None.
        """
        try:
            stmt = select(Job).where(Job.id == uuid.UUID(job_id))
            result = await self._session.execute(stmt)
            job = result.scalar_one_or_none()
            if job is None:
                return None
            return {
                "id": str(job.id),
                "filename": job.filename,
                "profile": job.profile,
                "status": job.status,
                "progress": job.progress,
                "current_step": job.current_step,
                "row_count": job.row_count,
                "error_code": job.error_code,
                "error_message": job.error_message,
                "pdf_path": job.pdf_path,
                "archive_path": job.archive_path,
            }
        except Exception as exc:
            raise DBError(f"Falha ao buscar job {job_id}: {exc}") from exc

    async def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: int | None = None,
        current_step: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        pdf_path: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        """Atualiza campos de um job.

        Apenas campos com valor não-None são atualizados.
        """
        try:
            values: dict[str, Any] = {}
            if status is not None:
                values["status"] = status
            if progress is not None:
                values["progress"] = progress
            if current_step is not None:
                values["current_step"] = current_step
            if error_code is not None:
                values["error_code"] = error_code
            if error_message is not None:
                values["error_message"] = error_message
            if pdf_path is not None:
                values["pdf_path"] = pdf_path
            if started_at is not None:
                values["started_at"] = started_at
            if finished_at is not None:
                values["finished_at"] = finished_at

            if not values:
                return

            # updated_at é atualizado automaticamente pelo onupdate
            values["updated_at"] = datetime.now(timezone.utc)

            stmt = (
                update(Job)
                .where(Job.id == uuid.UUID(job_id))
                .values(**values)
            )
            await self._session.execute(stmt)
            await self._session.commit()
        except Exception as exc:
            await self._session.rollback()
            raise DBError(f"Falha ao atualizar job {job_id}: {exc}") from exc

    async def mark_job_failed(
        self,
        job_id: str,
        error_code: str,
        error_message: str,
    ) -> None:
        """Marca um job como failed e atualiza campos de erro."""
        await self.update_job(
            job_id,
            status="error",
            error_code=error_code,
            error_message=error_message,
            finished_at=datetime.now(timezone.utc),
        )

    async def mark_job_done(
        self,
        job_id: str,
        pdf_path: str,
    ) -> None:
        """Marca um job como concluído com sucesso."""
        await self.update_job(
            job_id,
            status="done",
            progress=100,
            current_step="Concluído",
            pdf_path=pdf_path,
            finished_at=datetime.now(timezone.utc),
        )

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    async def get_steps(self, job_id: str) -> list[dict[str, Any]]:
        """Retorna todas as steps de um job ordenadas por ``order``."""
        try:
            stmt = (
                select(JobStep)
                .where(JobStep.job_id == uuid.UUID(job_id))
                .order_by(JobStep.order)
            )
            result = await self._session.execute(stmt)
            steps = result.scalars().all()
            return [
                {
                    "id": str(s.id),
                    "name": s.name,
                    "label": s.label,
                    "status": s.status,
                    "order": s.order,
                }
                for s in steps
            ]
        except Exception as exc:
            raise DBError(f"Falha ao buscar steps do job {job_id}: {exc}") from exc

    async def start_step(self, job_id: str, step_name: str) -> None:
        """Marca uma step como 'processing' e registra started_at."""
        try:
            stmt = (
                update(JobStep)
                .where(
                    JobStep.job_id == uuid.UUID(job_id),
                    JobStep.name == step_name,
                )
                .values(
                    status="processing",
                    started_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await self._session.execute(stmt)
            await self._session.commit()
        except Exception as exc:
            await self._session.rollback()
            raise DBError(
                f"Falha ao iniciar step {step_name} do job {job_id}: {exc}"
            ) from exc

    async def complete_step(self, job_id: str, step_name: str) -> None:
        """Marca uma step como 'done' e registra completed_at."""
        try:
            stmt = (
                update(JobStep)
                .where(
                    JobStep.job_id == uuid.UUID(job_id),
                    JobStep.name == step_name,
                )
                .values(
                    status="done",
                    completed_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await self._session.execute(stmt)
            await self._session.commit()
        except Exception as exc:
            await self._session.rollback()
            raise DBError(
                f"Falha ao completar step {step_name} do job {job_id}: {exc}"
            ) from exc

    async def fail_step(
        self, job_id: str, step_name: str, error_message: str
    ) -> None:
        """Marca uma step como 'error' com mensagem de erro."""
        try:
            stmt = (
                update(JobStep)
                .where(
                    JobStep.job_id == uuid.UUID(job_id),
                    JobStep.name == step_name,
                )
                .values(
                    status="error",
                    error_message=error_message,
                    completed_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await self._session.execute(stmt)
            await self._session.commit()
        except Exception as exc:
            await self._session.rollback()
            raise DBError(
                f"Falha ao marcar step {step_name} como error: {exc}"
            ) from exc
