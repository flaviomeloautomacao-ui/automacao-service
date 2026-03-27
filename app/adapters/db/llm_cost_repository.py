"""Repositório de persistência de custos LLM no banco de dados.

Responsável por:
- Inserir registros de uso LLM em batch (``llm_usage_logs``)
- Atualizar campos pré-agregados no Job (``llm_cost_usd``, etc.)
- Buscar registros para API de custos

Toda operação é resiliente — falhas de persistência são logadas
mas NÃO propagam exceções para o pipeline.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.db.job_models import (
    Job,
    LlmUsageLogModel,
    PipelineVersionModel,
)
from app.infrastructure.llm_cost_tracker import LLMUsageRecord


class LLMCostRepository:
    """Persistência de custos LLM no PostgreSQL.

    Opera como complemento ao ``LLMCostTracker`` em memória:
    recebe os registros acumulados e faz flush para o banco.

    Args:
        session: Sessão SQLAlchemy async.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_batch(
        self,
        records: list[LLMUsageRecord],
        job_id: str,
    ) -> int:
        """Insere registros de uso LLM em batch.

        Args:
            records: Lista de ``LLMUsageRecord`` acumulados pelo tracker.
            job_id: UUID do job (para filtrar registros relevantes).

        Returns:
            Número de registros inseridos com sucesso.
        """
        if not records:
            return 0

        job_records = [r for r in records if r.job_id == job_id]
        if not job_records:
            return 0

        inserted = 0
        try:
            for record in job_records:
                log_entry = LlmUsageLogModel(
                    id=uuid.uuid4(),
                    job_id=uuid.UUID(job_id),
                    flow=record.flow,
                    step=record.step,
                    provider=record.provider,
                    model=record.model,
                    call_type=record.call_type,
                    input_tokens=record.input_tokens,
                    output_tokens=record.output_tokens,
                    total_tokens=record.total_tokens,
                    tokens_source=record.tokens_source,
                    estimated_cost_usd=record.estimated_cost_usd,
                    duration_ms=record.duration_ms,
                    success=record.success,
                    error_message=record.error_message or None,
                    retry_attempt=record.retry_attempt,
                    equipment_name=record.equipment_name or None,
                    prompt_chars=record.prompt_chars,
                    response_chars=record.response_chars,
                )
                self._session.add(log_entry)
                inserted += 1

            await self._session.flush()
            await self._session.commit()

            logger.info(
                "COST_FLUSH | job={} | records_saved={} | total_cost=${:.6f}",
                job_id,
                inserted,
                sum(r.estimated_cost_usd for r in job_records),
            )
        except Exception as exc:
            await self._session.rollback()
            logger.error(
                "COST_FLUSH | FALHA ao persistir {} registros para job {}: {}",
                len(job_records),
                job_id,
                str(exc),
            )
            inserted = 0

        return inserted

    async def update_job_cost_summary(
        self,
        job_id: str,
        total_cost_usd: float,
        total_tokens: int,
        call_count: int,
    ) -> None:
        """Atualiza campos pré-agregados de custo no Job.

        Estes campos permitem query rápida sem JOIN com ``llm_usage_logs``.

        Args:
            job_id: UUID do job.
            total_cost_usd: Custo total acumulado.
            total_tokens: Total de tokens consumidos.
            call_count: Número de chamadas LLM.
        """
        try:
            stmt = (
                update(Job)
                .where(Job.id == uuid.UUID(job_id))
                .values(
                    llm_cost_usd=total_cost_usd,
                    llm_total_tokens=total_tokens,
                    llm_call_count=call_count,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await self._session.execute(stmt)
            await self._session.commit()

            logger.info(
                "COST_SUMMARY | job={} | cost=${:.6f} | tokens={} | calls={}",
                job_id,
                total_cost_usd,
                total_tokens,
                call_count,
            )
        except Exception as exc:
            await self._session.rollback()
            logger.error(
                "COST_SUMMARY | FALHA ao atualizar custo do job {}: {}",
                job_id,
                str(exc),
            )

    async def get_job_cost_breakdown(
        self,
        job_id: str,
    ) -> dict[str, Any]:
        """Busca breakdown de custos de um job para a API.

        Retorna dados organizados por step e por equipamento.

        Args:
            job_id: UUID do job.

        Returns:
            Dict com summary, by_step, by_equipment e records.
        """
        try:
            stmt = (
                select(LlmUsageLogModel)
                .where(LlmUsageLogModel.job_id == uuid.UUID(job_id))
                .order_by(LlmUsageLogModel.created_at)
            )
            result = await self._session.execute(stmt)
            logs = result.scalars().all()

            if not logs:
                return {
                    "summary": {
                        "total_cost_usd": 0.0,
                        "total_tokens": 0,
                        "call_count": 0,
                    },
                    "by_step": {},
                    "by_equipment": {},
                    "records": [],
                }

            # Aggregate by step
            by_step: dict[str, dict[str, Any]] = {}
            for log in logs:
                step_name = log.step
                if step_name not in by_step:
                    by_step[step_name] = {
                        "cost_usd": 0.0,
                        "tokens": 0,
                        "calls": 0,
                    }
                by_step[step_name]["cost_usd"] += log.estimated_cost_usd
                by_step[step_name]["tokens"] += log.total_tokens
                by_step[step_name]["calls"] += 1

            # Aggregate by equipment
            by_equipment: dict[str, dict[str, Any]] = {}
            for log in logs:
                if log.equipment_name:
                    equip = log.equipment_name
                    if equip not in by_equipment:
                        by_equipment[equip] = {
                            "cost_usd": 0.0,
                            "tokens": 0,
                            "calls": 0,
                        }
                    by_equipment[equip]["cost_usd"] += log.estimated_cost_usd
                    by_equipment[equip]["tokens"] += log.total_tokens
                    by_equipment[equip]["calls"] += 1

            # Raw records
            records = [
                {
                    "id": str(log.id),
                    "flow": log.flow,
                    "step": log.step,
                    "provider": log.provider,
                    "model": log.model,
                    "call_type": log.call_type,
                    "input_tokens": log.input_tokens,
                    "output_tokens": log.output_tokens,
                    "total_tokens": log.total_tokens,
                    "tokens_source": log.tokens_source,
                    "estimated_cost_usd": log.estimated_cost_usd,
                    "duration_ms": log.duration_ms,
                    "success": log.success,
                    "error_message": log.error_message,
                    "retry_attempt": log.retry_attempt,
                    "equipment_name": log.equipment_name,
                    "prompt_chars": log.prompt_chars,
                    "response_chars": log.response_chars,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                }
                for log in logs
            ]

            total_cost = sum(log.estimated_cost_usd for log in logs)
            total_tokens = sum(log.total_tokens for log in logs)

            return {
                "summary": {
                    "total_cost_usd": round(total_cost, 6),
                    "total_tokens": total_tokens,
                    "call_count": len(logs),
                },
                "by_step": by_step,
                "by_equipment": by_equipment,
                "records": records,
            }
        except Exception as exc:
            logger.error(
                "COST_BREAKDOWN | FALHA para job {}: {}",
                job_id,
                str(exc),
            )
            return {
                "summary": {
                    "total_cost_usd": 0.0,
                    "total_tokens": 0,
                    "call_count": 0,
                },
                "by_step": {},
                "by_equipment": {},
                "records": [],
            }

    # ------------------------------------------------------------------
    # Pipeline Version
    # ------------------------------------------------------------------

    async def find_or_create_pipeline_version(
        self,
        *,
        prompt_version: str,
        schema_version: str,
        rag_strategy: str,
        llm_model: str,
        embedding_model: str,
        prompt_hash: str,
        schema_hash: str,
        rag_top_k: int,
        rag_max_chunks: int,
        rag_min_score: float,
        config_snapshot: dict[str, Any],
    ) -> str:
        """Busca ou cria um snapshot de versão do pipeline.

        Se já existir uma versão com mesmos prompt_hash e schema_hash,
        retorna o ID existente. Caso contrário, cria uma nova.

        Returns:
            ID da versão (cuid string).
        """
        try:
            # Buscar existente
            stmt = (
                select(PipelineVersionModel)
                .where(
                    PipelineVersionModel.prompt_hash == prompt_hash,
                    PipelineVersionModel.schema_hash == schema_hash,
                )
                .limit(1)
            )
            result = await self._session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                logger.debug(
                    "VERSION_SNAPSHOT | Reutilizando versão existente: {}",
                    existing.id,
                )
                return existing.id

            # Criar nova
            version_id = f"pv_{uuid.uuid4().hex[:24]}"

            new_version = PipelineVersionModel(
                id=version_id,
                prompt_version=prompt_version,
                schema_version=schema_version,
                rag_strategy=rag_strategy,
                llm_model=llm_model,
                embedding_model=embedding_model,
                prompt_hash=prompt_hash,
                schema_hash=schema_hash,
                rag_top_k=rag_top_k,
                rag_max_chunks=rag_max_chunks,
                rag_min_score=rag_min_score,
                config_snapshot=config_snapshot,
            )
            self._session.add(new_version)
            await self._session.flush()
            await self._session.commit()

            logger.info(
                "VERSION_SNAPSHOT | Nova versão criada: {} | prompt_hash={}",
                version_id,
                prompt_hash[:16],
            )
            return version_id

        except Exception as exc:
            await self._session.rollback()
            logger.error(
                "VERSION_SNAPSHOT | FALHA ao criar/buscar versão: {}",
                str(exc),
            )
            return ""

    async def link_job_to_version(
        self,
        job_id: str,
        version_id: str,
    ) -> None:
        """Vincula um job a uma versão do pipeline.

        Args:
            job_id: UUID do job.
            version_id: ID da versão do pipeline.
        """
        if not version_id:
            return
        try:
            stmt = (
                update(Job)
                .where(Job.id == uuid.UUID(job_id))
                .values(
                    pipeline_version_id=version_id,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await self._session.execute(stmt)
            await self._session.commit()
        except Exception as exc:
            await self._session.rollback()
            logger.error(
                "VERSION_SNAPSHOT | FALHA ao vincular job {} à versão {}: {}",
                job_id,
                version_id,
                str(exc),
            )
