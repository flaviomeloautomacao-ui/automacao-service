"""Rotas de documentos.

Endpoints para consulta, listagem e manipulação de documentos processados.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.adapters.db.repository import ReportRepository
from app.infrastructure.dependencies import get_logger, get_repository

router = APIRouter()


@router.get("/{report_id}")
async def get_report(
    report_id: str,
    repo: ReportRepository = Depends(get_repository),
) -> dict[str, Any]:
    """Retorna os metadados de um relatório gerado pelo UUID.

    Args:
        report_id: UUID do relatório.
        repo: Repositório injetado via Depends.

    Returns:
        JSON com os dados do relatório (id, draft_id, pdf_url, etc.).

    Raises:
        HTTPException 404: se o relatório não for encontrado.
    """
    logger = get_logger()
    logger.info("Buscando relatório | report_id={}", report_id)

    report = await repo.get_generated(report_id)

    if report is None:
        return {"data": None, "error": {"code": "NOT_FOUND", "message": "Relatório não encontrado."}}

    return {"data": report, "error": None}
