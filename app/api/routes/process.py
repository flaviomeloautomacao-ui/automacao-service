"""Rota de processamento assíncrono de jobs.

Endpoint ``POST /process`` recebe ``{ job_id }`` e dispara o
pipeline em background via FastAPI BackgroundTasks.

O Next.js chama esta rota de forma fire-and-forget após o
usuário completar a etapa de complementação.

O Python busca os dados (planilha, metadados do relatório,
equipamentos e imagens) diretamente do banco de dados.
O front-end faz polling a cada 3s para exibir progresso.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field, field_validator

from app.api.middleware.auth import verify_internal_api_key
from app.api.middleware.rate_limit import rate_limit_jobs
from app.infrastructure.dependencies import get_logger, get_process_job_use_case
from app.application.use_cases.process_job import ProcessJobUseCase

router = APIRouter()


class ProcessRequest(BaseModel):
    """Corpo da requisição POST /process."""

    job_id: str = Field(..., min_length=36, max_length=36)

    @field_validator("job_id")
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        import uuid  # noqa: PLC0415

        try:
            uuid.UUID(v)
        except ValueError as exc:
            raise ValueError(f"job_id inválido: {v}") from exc
        return v


async def _process_in_background(
    use_case: ProcessJobUseCase,
    job_id: str,
) -> None:
    """Wrapper para execução em background.

    Captura exceções para que o BackgroundTask não falhe silenciosamente.
    """
    logger = get_logger()
    try:
        logger.info("Background | Iniciando processamento do job {}", job_id)
        result = await use_case.execute(job_id=job_id)
        logger.info(
            "Background | Job {} concluído com sucesso | pdf_path={}",
            job_id,
            result.get("pdf_path"),
        )
    except Exception as exc:
        # O use case já marca o job como error no banco.
        # Aqui apenas logamos para visibilidade.
        logger.error(
            "Background | Job {} falhou: {}",
            job_id,
            str(exc),
        )


@router.post(
    "",
    dependencies=[Depends(verify_internal_api_key), Depends(rate_limit_jobs)],
)
async def process_job(
    body: ProcessRequest,
    background_tasks: BackgroundTasks,
    use_case: ProcessJobUseCase = Depends(get_process_job_use_case),
) -> dict[str, Any]:
    """Recebe um job para processamento assíncrono.

    O endpoint retorna imediatamente com status ``accepted``.
    O processamento real acontece em background.

    O Python busca todos os dados necessários do banco:
    - ``spreadsheet_rows`` (linhas da planilha)
    - ``reports`` (metadados de capa / company_metadata)
    - ``report_equipments`` + ``equipment_images`` (complementação)

    Args:
        body: JSON com ``job_id``.
        background_tasks: Gerenciador de tarefas em background do FastAPI.
        use_case: Caso de uso injetado via Depends.

    Returns:
        JSON com status ``accepted`` e job_id.
    """
    logger = get_logger()

    if not body.job_id:
        return {
            "data": None,
            "error": {"code": "MISSING_JOB_ID", "message": "job_id é obrigatório."},
        }

    logger.info("POST /process | job_id={}", body.job_id)

    background_tasks.add_task(
        _process_in_background,
        use_case=use_case,
        job_id=body.job_id,
    )

    return {
        "data": {"status": "accepted", "job_id": body.job_id},
        "error": None,
    }
