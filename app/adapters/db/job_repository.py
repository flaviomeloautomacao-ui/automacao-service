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

from app.adapters.db.job_models import (
    Job,
    JobStep,
    ReportModel,
    SpreadsheetUploadModel,
)
from app.domain.errors import DBError

# Map Portuguese column names (from Next.js rawJson) to snake_case Python keys.
# This acts as a safety net in case normalizedJson was not properly normalized.
_COLUMN_NORMALIZE_MAP: dict[str, str] = {
    "Equipamento": "equipamento",
    "Descrição do equipamento": "descricao_equipamento",
    "Riscos": "riscos",
    "Perigo": "perigo",
    "Causas Possíveis": "causas",
    "Consequências": "consequencias",
    "Categoria da Severidade": "categoria_severidade",
    "Categoria do Risco": "categoria_risco",
    "Medidas Preventivas Existentes": "medidas_existentes",
    "Medidas Preventivas a Implementar": "medidas_implementar",
    "Observações": "observacoes",
}


def _normalize_row_keys(row: dict) -> dict:
    """Normalize row keys from Portuguese to snake_case if needed.

    If the row already has snake_case keys, returns as-is.
    If it has Portuguese keys, converts them.
    """
    # Quick check: if 'equipamento' (snake_case) already exists, skip
    if "equipamento" in row:
        return row
    return {_COLUMN_NORMALIZE_MAP.get(k, k): v for k, v in row.items()}


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

    # ------------------------------------------------------------------
    # Data Fetching (leitura de dados para o pipeline)
    # ------------------------------------------------------------------

    async def get_spreadsheet_rows(self, job_id: str) -> list[dict[str, Any]]:
        """Busca as linhas da planilha persistidas para um job.

        Acessa ``spreadsheet_uploads`` → ``spreadsheet_rows``.

        Returns:
            Lista de dicts ``normalized_json`` ordenados por ``row_index``.

        Raises:
            DBError: Se falhar ou não encontrar SpreadsheetUpload.
        """
        try:
            stmt = (
                select(SpreadsheetUploadModel)
                .where(SpreadsheetUploadModel.job_id == uuid.UUID(job_id))
            )
            result = await self._session.execute(stmt)
            upload = result.scalar_one_or_none()

            if upload is None:
                raise DBError(f"SpreadsheetUpload não encontrado para job {job_id}")

            # rows já são carregados via lazy="selectin" na relação
            sorted_rows = sorted(upload.rows, key=lambda r: r.row_index)
            return [_normalize_row_keys(row.normalized_json) for row in sorted_rows]
        except DBError:
            raise
        except Exception as exc:
            raise DBError(
                f"Falha ao buscar spreadsheet_rows do job {job_id}: {exc}"
            ) from exc

    async def get_report_metadata(self, job_id: str) -> dict[str, Any] | None:
        """Busca os metadados do relatório (company_metadata) de um job.

        Returns:
            Dict com campos de capa do relatório, ou None se não existir.
        """
        try:
            stmt = select(ReportModel).where(
                ReportModel.job_id == uuid.UUID(job_id)
            )
            result = await self._session.execute(stmt)
            report = result.scalar_one_or_none()
            if report is None:
                return None

            data_avaliacao = None
            if report.data_avaliacao is not None:
                data_avaliacao = report.data_avaliacao.strftime("%d/%m/%Y")

            return {
                "razao_social": report.razao_social,
                "cnpj": report.cnpj,
                "site": report.site,
                "endereco": report.endereco,
                "local_vistoriado": report.local_vistoriado,
                "data_avaliacao": data_avaliacao,
                "contrato": report.contrato,
                "elaboracao": report.elaboracao,
                "responsavel": report.responsavel,
                "registro_profissional": report.registro_profissional,
                "observacoes_gerais": report.observacoes_gerais,
            }
        except Exception as exc:
            raise DBError(
                f"Falha ao buscar report do job {job_id}: {exc}"
            ) from exc

    async def get_report_equipments_with_images(
        self, job_id: str
    ) -> list[dict[str, Any]]:
        """Busca os equipamentos do relatório com suas imagens.

        Returns:
            Lista de dicts com dados dos equipamentos e array de imagens,
            ordenados por ``order_index``.
        """
        try:
            stmt = select(ReportModel).where(
                ReportModel.job_id == uuid.UUID(job_id)
            )
            result = await self._session.execute(stmt)
            report = result.scalar_one_or_none()
            if report is None:
                return []

            # equipments + images são carregados via lazy="selectin"
            sorted_equips = sorted(report.equipments, key=lambda e: e.order_index)
            equipments = []
            for eq in sorted_equips:
                images = [
                    {
                        "id": str(img.id),
                        "secure_url": img.secure_url,
                        "public_id": img.public_id,
                        "width": img.width,
                        "height": img.height,
                    }
                    for img in eq.images
                ]
                equipments.append({
                    "id": str(eq.id),
                    "equipment_name": eq.equipment_name,
                    "equipment_description": eq.equipment_description,
                    "order_index": eq.order_index,
                    "local_instalacao": eq.local_instalacao,
                    "funcao_operacional": eq.funcao_operacional,
                    "observacoes_extras": eq.observacoes_extras,
                    "extra_json": eq.extra_json,
                    "images": images,
                })
            return equipments
        except Exception as exc:
            raise DBError(
                f"Falha ao buscar report_equipments do job {job_id}: {exc}"
            ) from exc
