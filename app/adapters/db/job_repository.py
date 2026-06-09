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
    AreaReferenceDocumentModel,
    AreaReportAreaModel,
    AreaReportSubstanceModel,
    AreaSpreadsheetUploadModel,
    DhaReportEquipmentModel,
    DhaSpreadsheetUploadModel,
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
    # V3 — novos campos
    "Categoria da Probabilidade": "categoria_probabilidade",
    "Classificação do Risco": "classificacao_risco",
    "Categoria da Severidade 2": "categoria_severidade_2",
    "Categoria da Probabilidade 2": "categoria_probabilidade_2",
    "Categoria do Risco 2": "categoria_probabilidade_2",     # alias V1 residual
    "Categoria de Probabilidade 2": "categoria_probabilidade_2",  # variação "de"
    "Classificação do Risco 2": "classificacao_risco_2",
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
                "document_type": job.document_type,
                "document_schema_version": job.document_schema_version,
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
        input_hash: str | None = None,
        llm_cost_usd: float | None = None,
        llm_total_tokens: int | None = None,
        llm_call_count: int | None = None,
        pipeline_version_id: str | None = None,
        dedup_source_job_id: str | None = None,
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
            if input_hash is not None:
                values["input_hash"] = input_hash
            if llm_cost_usd is not None:
                values["llm_cost_usd"] = llm_cost_usd
            if llm_total_tokens is not None:
                values["llm_total_tokens"] = llm_total_tokens
            if llm_call_count is not None:
                values["llm_call_count"] = llm_call_count
            if pipeline_version_id is not None:
                values["pipeline_version_id"] = pipeline_version_id
            if dedup_source_job_id is not None:
                values["dedup_source_job_id"] = uuid.UUID(dedup_source_job_id)

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
        *,
        llm_cost_usd: float | None = None,
        llm_total_tokens: int | None = None,
        llm_call_count: int | None = None,
    ) -> None:
        """Marca um job como concluído com sucesso."""
        await self.update_job(
            job_id,
            status="done",
            progress=100,
            current_step="Concluído",
            pdf_path=pdf_path,
            finished_at=datetime.now(timezone.utc),
            llm_cost_usd=llm_cost_usd,
            llm_total_tokens=llm_total_tokens,
            llm_call_count=llm_call_count,
        )

    async def find_done_job_by_hash(
        self,
        input_hash: str,
    ) -> dict[str, Any] | None:
        """Busca um job concluído com o mesmo input_hash (deduplicação).

        Args:
            input_hash: SHA-256 do input do job.

        Returns:
            Dict com id, pdf_path e report_id do job encontrado, ou None.
        """
        try:
            stmt = (
                select(Job)
                .where(Job.input_hash == input_hash, Job.status == "done")
                .limit(1)
            )
            result = await self._session.execute(stmt)
            job = result.scalar_one_or_none()
            if job is None:
                return None
            return {
                "id": str(job.id),
                "pdf_path": job.pdf_path,
                "status": job.status,
            }
        except Exception as exc:
            from loguru import logger  # noqa: PLC0415
            logger.warning(
                "DEDUP_CHECK | Falha ao buscar job por hash {}: {}",
                input_hash[:16],
                str(exc),
            )
            return None

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

    async def get_dha_spreadsheet_rows(self, job_id: str) -> list[dict[str, Any]]:
        """Busca linhas DHA v2 persistidas em ``dha_spreadsheet_rows``."""
        try:
            stmt = (
                select(DhaSpreadsheetUploadModel)
                .where(DhaSpreadsheetUploadModel.job_id == uuid.UUID(job_id))
            )
            result = await self._session.execute(stmt)
            upload = result.scalar_one_or_none()

            if upload is None:
                raise DBError(f"DhaSpreadsheetUpload não encontrado para job {job_id}")

            sorted_rows = sorted(upload.rows, key=lambda r: r.row_index)
            return [_normalize_row_keys(row.normalized_json) for row in sorted_rows]
        except DBError:
            raise
        except Exception as exc:
            raise DBError(
                f"Falha ao buscar dha_spreadsheet_rows do job {job_id}: {exc}"
            ) from exc

    async def get_area_spreadsheet_rows(self, job_id: str) -> list[dict[str, Any]]:
        """Busca linhas de Classificação de Áreas v2."""
        try:
            stmt = (
                select(AreaSpreadsheetUploadModel)
                .where(AreaSpreadsheetUploadModel.job_id == uuid.UUID(job_id))
            )
            result = await self._session.execute(stmt)
            upload = result.scalar_one_or_none()

            if upload is None:
                raise DBError(f"AreaSpreadsheetUpload não encontrado para job {job_id}")

            sorted_rows = sorted(upload.rows, key=lambda r: r.row_index)
            return [row.normalized_json for row in sorted_rows]
        except DBError:
            raise
        except Exception as exc:
            raise DBError(
                f"Falha ao buscar area_spreadsheet_rows do job {job_id}: {exc}"
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
                "observacoes_gerais_prompt": report.observacoes_gerais_prompt,
                # ── Novos campos (Fase 4) ──
                "cover_image_url": report.cover_image_url,
                "art_numero": report.art_numero,
                "codigo_documento": report.codigo_documento,
                "revisions": [
                    {
                        "version": rev.version,
                        "date": rev.date,
                        "author": rev.author,
                        "description": rev.description,
                    }
                    for rev in sorted(report.revisions, key=lambda r: r.version)
                ],
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

    async def get_dha_report_equipments_with_images(
        self, job_id: str
    ) -> list[dict[str, Any]]:
        """Busca equipamentos DHA v2 com imagens."""
        try:
            stmt = select(ReportModel).where(
                ReportModel.job_id == uuid.UUID(job_id)
            )
            result = await self._session.execute(stmt)
            report = result.scalar_one_or_none()
            if report is None:
                return []

            stmt_equip = (
                select(DhaReportEquipmentModel)
                .where(DhaReportEquipmentModel.report_id == report.id)
            )
            eq_result = await self._session.execute(stmt_equip)
            equipments_db = sorted(
                eq_result.scalars().all(),
                key=lambda equipment: equipment.order_index,
            )

            equipments: list[dict[str, Any]] = []
            for eq in equipments_db:
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
                f"Falha ao buscar dha_report_equipments do job {job_id}: {exc}"
            ) from exc

    async def get_area_report_context(self, job_id: str) -> dict[str, Any]:
        """Busca complementação v2 de Classificação de Áreas."""
        try:
            stmt = select(ReportModel).where(
                ReportModel.job_id == uuid.UUID(job_id)
            )
            result = await self._session.execute(stmt)
            report = result.scalar_one_or_none()
            if report is None:
                return {
                    "areas": [],
                    "substances": [],
                    "references": [],
                }

            area_result = await self._session.execute(
                select(AreaReportAreaModel).where(
                    AreaReportAreaModel.report_id == report.id,
                ),
            )
            areas = sorted(
                area_result.scalars().all(),
                key=lambda area: area.order_index,
            )

            substance_result = await self._session.execute(
                select(AreaReportSubstanceModel).where(
                    AreaReportSubstanceModel.report_id == report.id,
                ),
            )
            substances = sorted(
                substance_result.scalars().all(),
                key=lambda substance: substance.order_index,
            )

            reference_result = await self._session.execute(
                select(AreaReferenceDocumentModel).where(
                    AreaReferenceDocumentModel.report_id == report.id,
                ),
            )
            references = sorted(
                reference_result.scalars().all(),
                key=lambda reference: reference.order_index,
            )

            return {
                "areas": [
                    {
                        "id": str(area.id),
                        "area_name": area.area_name,
                        "description": area.description,
                        "order_index": area.order_index,
                        "operational_notes": area.operational_notes,
                        "ventilation_premises": area.ventilation_premises,
                        "extra_json": area.extra_json,
                        "photos": [
                            {
                                "id": str(img.id),
                                "public_id": img.public_id,
                                "secure_url": img.secure_url,
                                "width": img.width,
                                "height": img.height,
                                "caption": img.caption,
                            }
                            for img in sorted(
                                area.photos, key=lambda p: p.created_at,
                            )
                        ],
                        "sources": [
                            {
                                "id": str(source.id),
                                "order_index": source.order_index,
                                "tag_referencia": source.tag_referencia,
                                "substance_name": source.substance_name,
                                "source_name": source.source_name,
                                "liberation_degree": source.liberation_degree,
                                "ventilation_type": source.ventilation_type,
                                "ventilation_degree": source.ventilation_degree,
                                "ventilation_availability": source.ventilation_availability,
                                "zone": source.zone,
                                "extension": source.extension,
                                "grupo": source.grupo,
                                "classe_temperatura": source.classe_temperatura,
                                "epl": source.epl,
                                "temperatura_processo": source.temperatura_processo,
                                "pressao_processo": source.pressao_processo,
                                "volume_processo": source.volume_processo,
                                "notes": source.notes,
                            }
                            for source in sorted(area.sources, key=lambda s: s.order_index)
                        ],
                    }
                    for area in areas
                ],
                "substances": [
                    {
                        "substance_name": substance.substance_name,
                        "order_index": substance.order_index,
                        "grupo": substance.grupo,
                        "classe_temperatura": substance.classe_temperatura,
                        "epl": substance.epl,
                        "properties_json": substance.properties_json,
                        "notes": substance.notes,
                        # ── Campos físico-químicos detalhados (Tabela 1) ──
                        "tipo": substance.tipo,
                        "ponto_fulgor": substance.ponto_fulgor,
                        "lii": substance.lii,
                        "densidade_relativa": substance.densidade_relativa,
                        "tai": substance.tai,
                        "cme": substance.cme,
                        "mit": substance.mit,
                        "sit_camada": substance.sit_camada,
                        "tmax": substance.tmax,
                        "st": substance.st,
                        "legend_notes": substance.legend_notes or [],
                    }
                    for substance in substances
                ],
                "references": [
                    {
                        "title": reference.title,
                        "document_code": reference.document_code,
                        "document_url": reference.document_url,
                        "notes": reference.notes,
                    }
                    for reference in references
                ],
            }
        except Exception as exc:
            raise DBError(
                f"Falha ao buscar contexto de áreas do job {job_id}: {exc}"
            ) from exc
