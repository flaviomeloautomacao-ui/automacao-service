"""Rotas de upload de arquivos.

Endpoints para receber e processar arquivos enviados pelo cliente.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Form, UploadFile

from app.application.use_cases.process_upload import ProcessUploadUseCase
from app.infrastructure.dependencies import get_logger, get_use_case

router = APIRouter()


@router.post("")
async def create_upload(
    file: UploadFile,
    profile: str = Form(""),
    use_case: ProcessUploadUseCase = Depends(get_use_case),
) -> dict[str, Any]:
    """Recebe uma planilha, processa e gera o laudo em PDF.

    O endpoint lê os bytes do arquivo enviado, delega ao
    ``ProcessUploadUseCase`` todo o pipeline (parse, validação,
    LLM, renderização e persistência) e retorna os IDs gerados
    junto com a URL assinada do PDF.

    Args:
        file: Arquivo enviado via multipart/form-data.
        use_case: Caso de uso injetado via Depends.

    Returns:
        JSON com ``upload_id``, ``draft_id``, ``report_id`` e ``pdf_url``.
    """
    logger = get_logger()

    file_bytes = await file.read()
    filename = file.filename or "upload.xlsx"
    content_type = file.content_type or "application/octet-stream"

    logger.info(
        "Upload recebido | filename={} | size={} bytes | content_type={}",
        filename,
        len(file_bytes),
        content_type,
    )

    result = await use_case.execute(
        file_bytes=file_bytes,
        filename=filename,
        content_type=content_type,
        profile=profile or None,
    )

    return {"data": result, "error": None}
