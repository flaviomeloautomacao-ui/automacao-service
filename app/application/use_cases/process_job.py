"""Caso de uso — processa um Job com atualização de progresso.

Orquestra o pipeline de geração de laudo reportando cada etapa
diretamente no banco via ``JobRepository``.

Etapas do pipeline (mapeadas às steps criadas pelo Next.js):
  1. upload_storage  — já concluída pelo Next.js
  2. data_processing — parse + validação + draft
  3. llm_analysis    — geração de seções narrativas via LLM
  4. pdf_rendering   — renderização HTML → PDF
  5. report_storage  — armazenamento do PDF + metadados

O front-end faz polling a cada 3s em ``GET /api/jobs/:id``
e exibe progresso em tempo real.
"""

from __future__ import annotations

import hashlib
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from app.adapters.db.job_repository import JobRepository
from app.adapters.storage.paths import report_pdf_path, upload_original_path
from app.application.use_cases.process_upload import (
    ProcessUploadUseCase,
    group_rows_by_equipment,
)
from app.domain.errors import DomainError


class ProcessJobUseCase:
    """Processa um job com atualização de progresso em tempo real.

    Delega a lógica de pipeline ao ``ProcessUploadUseCase`` existente
    mas intercepta cada etapa para reportar progresso.

    Args:
        job_repo: Repositório de jobs/steps.
        upload_use_case: Caso de uso original de processamento.
    """

    def __init__(
        self,
        *,
        job_repo: JobRepository,
        upload_use_case: ProcessUploadUseCase,
    ) -> None:
        self._job_repo = job_repo
        self._uc = upload_use_case

    async def execute(
        self,
        job_id: str,
        file_bytes: bytes,
        filename: str,
        content_type: str,
        profile: str | None = None,
    ) -> dict[str, str]:
        """Executa o pipeline completo com reportagem de progresso.

        Args:
            job_id: UUID do job (criado pelo Next.js).
            file_bytes: Conteúdo binário da planilha.
            filename: Nome original do arquivo.
            content_type: MIME type.
            profile: Perfil de risco (dust, gas, vapors).

        Returns:
            Dicionário com upload_id, draft_id, report_id, pdf_url, pdf_path.
        """
        try:
            # ── Iniciar processamento ─────────────────────────────
            await self._job_repo.update_job(
                job_id,
                status="processing",
                progress=10,
                current_step="Iniciando processamento…",
                started_at=datetime.now(timezone.utc),
            )

            # ── Step 2: data_processing ───────────────────────────
            await self._job_repo.start_step(job_id, "data_processing")
            await self._job_repo.update_job(
                job_id,
                progress=15,
                current_step="Processando dados da planilha…",
            )

            # 2a) Armazena arquivo cru no storage (sem tabela legada)
            upload_ref = str(uuid.uuid4())
            storage_path = upload_original_path(upload_ref, filename)
            await self._uc._storage.put_bytes(
                self._uc._bucket,
                storage_path,
                file_bytes,
                content_type=content_type,
            )
            logger.info("Job {} | Arquivo armazenado | path={}", job_id, storage_path)

            await self._job_repo.update_job(job_id, progress=20)

            # 2b) Parse da planilha
            rows = self._uc._parse_spreadsheet(file_bytes, filename)

            await self._job_repo.update_job(
                job_id,
                progress=22,
                current_step="Validando dados…",
            )

            # 2c) Validação determinística
            self._uc._validate_rows(rows)

            await self._job_repo.update_job(job_id, progress=25)

            # 2d) Prepara dados (sem tabela legada de drafts)
            rows_dicts = [row.model_dump(mode="json") for row in rows]

            # 2e) Agrupa equipamentos
            grouped_equipment = group_rows_by_equipment(rows_dicts)

            await self._job_repo.complete_step(job_id, "data_processing")
            await self._job_repo.update_job(
                job_id,
                progress=30,
                current_step="Dados processados com sucesso",
            )

            logger.info(
                "Job {} | data_processing concluído | {} equipamentos",
                job_id,
                len(grouped_equipment),
            )

            # ── Step 3: llm_analysis ──────────────────────────────
            await self._job_repo.start_step(job_id, "llm_analysis")
            await self._job_repo.update_job(
                job_id,
                progress=35,
                current_step="Gerando recomendações via IA…",
            )

            llm_sections = await self._uc._generate_llm_sections(
                rows_dicts,
                None,  # company_metadata
                profile=profile,
                grouped_equipment=grouped_equipment,
            )

            llm_sections_html = self._uc._normalize_llm_sections(llm_sections)

            await self._job_repo.complete_step(job_id, "llm_analysis")
            await self._job_repo.update_job(
                job_id,
                progress=70,
                current_step="Recomendações geradas com sucesso",
            )

            logger.info("Job {} | llm_analysis concluído", job_id)

            # ── Step 4: pdf_rendering ─────────────────────────────
            await self._job_repo.start_step(job_id, "pdf_rendering")
            await self._job_repo.update_job(
                job_id,
                progress=75,
                current_step="Gerando PDF do laudo…",
            )

            pdf_bytes = self._uc._render_pdf(
                rows_dicts,
                llm_sections_html,
                None,  # company_metadata
                profile=profile,
                grouped_equipment=grouped_equipment,
            )

            await self._job_repo.complete_step(job_id, "pdf_rendering")
            await self._job_repo.update_job(
                job_id,
                progress=85,
                current_step="PDF gerado com sucesso",
            )

            logger.info("Job {} | pdf_rendering concluído | {} bytes", job_id, len(pdf_bytes))

            # ── Step 5: report_storage ────────────────────────────
            await self._job_repo.start_step(job_id, "report_storage")
            await self._job_repo.update_job(
                job_id,
                progress=90,
                current_step="Armazenando relatório…",
            )

            # Armazena PDF diretamente no storage (sem tabela legada)
            report_id = str(uuid.uuid4())
            pdf_path = report_pdf_path(report_id, version=1)
            await self._uc._storage.put_bytes(
                self._uc._bucket,
                pdf_path,
                pdf_bytes,
                content_type="application/pdf",
            )
            pdf_url = await self._uc._storage.get_signed_url(
                self._uc._bucket,
                pdf_path,
            )
            logger.info(
                "Job {} | PDF armazenado | report_id={} | path={}",
                job_id, report_id, pdf_path,
            )

            await self._job_repo.complete_step(job_id, "report_storage")

            # ── Finalizar job ─────────────────────────────────────
            await self._job_repo.mark_job_done(job_id, pdf_path)

            logger.info(
                "Job {} | Pipeline CONCLUÍDO | report_id={} | pdf_path={}",
                job_id,
                report_id,
                pdf_path,
            )

            return {
                "report_id": report_id,
                "pdf_url": pdf_url,
                "pdf_path": pdf_path,
            }

        except DomainError as exc:
            logger.error("Job {} | Erro de domínio: {}", job_id, str(exc))
            await self._fail_job(
                job_id,
                error_code=type(exc).__name__.upper(),
                error_message=str(exc),
                step_name=await self._current_processing_step(job_id),
            )
            raise

        except Exception as exc:
            logger.error(
                "Job {} | Erro inesperado: {}\n{}",
                job_id,
                str(exc),
                traceback.format_exc(),
            )
            await self._fail_job(
                job_id,
                error_code="INTERNAL_ERROR",
                error_message=f"Erro inesperado: {str(exc)}",
                step_name=await self._current_processing_step(job_id),
            )
            raise

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _fail_job(
        self,
        job_id: str,
        error_code: str,
        error_message: str,
        step_name: str | None = None,
    ) -> None:
        """Marca job e step corrente como falhos.

        Usa uma sessão NOVA para garantir que a gravação de erro funcione
        mesmo se a sessão original estiver em estado inválido (rollback pendente).
        """
        from app.infrastructure.db import get_session as _get_session  # noqa: PLC0415

        try:
            async for session in _get_session():
                fresh_repo = JobRepository(session)
                if step_name:
                    await fresh_repo.fail_step(job_id, step_name, error_message)
                await fresh_repo.mark_job_failed(job_id, error_code, error_message)
                break
        except Exception as inner_exc:
            logger.error(
                "Job {} | Falha ao marcar job como error: {}",
                job_id,
                str(inner_exc),
            )

    async def _current_processing_step(self, job_id: str) -> str | None:
        """Retorna o nome da step atualmente em 'processing'.

        Usa sessão nova para funcionar mesmo quando a sessão principal
        está em estado inválido.
        """
        from app.infrastructure.db import get_session as _get_session  # noqa: PLC0415

        try:
            async for session in _get_session():
                fresh_repo = JobRepository(session)
                steps = await fresh_repo.get_steps(job_id)
                for step in steps:
                    if step["status"] == "processing":
                        return step["name"]
                return None
        except Exception:
            return None
