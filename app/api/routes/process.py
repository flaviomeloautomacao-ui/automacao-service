"""Rota de processamento assíncrono de jobs.

Endpoint ``POST /process`` recebe job_id + arquivo e dispara o
pipeline em background via FastAPI BackgroundTasks.

O Next.js chama esta rota de forma fire-and-forget após criar o job.
O Python processa em segundo plano e atualiza o banco diretamente.
O front-end faz polling a cada 3s para exibir progresso.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Form, UploadFile

from app.infrastructure.dependencies import get_logger, get_process_job_use_case
from app.application.use_cases.process_job import ProcessJobUseCase

router = APIRouter()


async def _process_in_background(
    use_case: ProcessJobUseCase,
    job_id: str,
    file_bytes: bytes,
    filename: str,
    content_type: str,
    profile: str | None,
) -> None:
    """Wrapper para execução em background.

    Captura exceções para que o BackgroundTask não falhe silenciosamente.
    """
    logger = get_logger()
    try:
        logger.info("Background | Iniciando processamento do job {}", job_id)
        result = await use_case.execute(
            job_id=job_id,
            file_bytes=file_bytes,
            filename=filename,
            content_type=content_type,
            profile=profile,
        )
        logger.info(
            "Background | Job {} concluído com sucesso | report_id={}",
            job_id,
            result.get("report_id"),
        )
    except Exception as exc:
        # O use case já marca o job como error no banco.
        # Aqui apenas logamos para visibilidade.
        logger.error(
            "Background | Job {} falhou: {}",
            job_id,
            str(exc),
        )


@router.post("")
async def process_job(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    job_id: str = Form(""),
    profile: str = Form(""),
    use_case: ProcessJobUseCase = Depends(get_process_job_use_case),
) -> dict[str, Any]:
    """Recebe um job para processamento assíncrono.

    O endpoint retorna imediatamente com status ``accepted``.
    O processamento real acontece em background.

    Args:
        background_tasks: Gerenciador de tarefas em background do FastAPI.
        file: Arquivo da planilha (multipart/form-data).
        job_id: UUID do job criado pelo Next.js.
        profile: Perfil de risco (dust, gas, vapors).
        use_case: Caso de uso injetado via Depends.

    Returns:
        JSON com status ``accepted`` e job_id.
    """
    logger = get_logger()

    if not job_id:
        return {
            "data": None,
            "error": {"code": "MISSING_JOB_ID", "message": "job_id é obrigatório."},
        }

    file_bytes = await file.read()
    filename = file.filename or "upload.xlsx"
    content_type = file.content_type or "application/octet-stream"

    logger.info(
        "POST /process | job_id={} | filename={} | size={} bytes",
        job_id,
        filename,
        len(file_bytes),
    )

    background_tasks.add_task(
        _process_in_background,
        use_case=use_case,
        job_id=job_id,
        file_bytes=file_bytes,
        filename=filename,
        content_type=content_type,
        profile=profile or None,
    )

    return {
        "data": {"job_id": job_id, "status": "accepted"},
        "error": None,
    }
