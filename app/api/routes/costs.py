"""Rotas de observabilidade de custos LLM.

Endpoints para consulta de métricas de uso e custo de chamadas LLM/embedding,
incluindo agregações por fluxo, etapa, modelo e job.

Endpoints:
    GET /costs/summary       — Resumo geral de custos
    GET /costs/by-flow       — Custos agregados por fluxo
    GET /costs/by-step       — Custos agregados por etapa
    GET /costs/by-model      — Custos agregados por modelo
    GET /costs/by-job        — Custos agregados por job
    GET /costs/ranking       — Chamadas mais caras
    GET /costs/records       — Todos os registros (JSON)
    GET /costs/records/csv   — Todos os registros (CSV)
    POST /costs/persist      — Força persistência em disco
    DELETE /costs/records     — Limpa registros em memória
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.infrastructure.llm_cost_tracker import get_tracker

router = APIRouter()


@router.get("/summary")
async def cost_summary() -> dict[str, Any]:
    """Retorna resumo geral de custos LLM.

    Inclui total de chamadas, tokens consumidos, custo total,
    média por chamada e contagem por tipo.

    Returns:
        JSON com métricas agregadas.
    """
    tracker = get_tracker()
    return {"data": tracker.summarize(), "error": None}


@router.get("/by-flow")
async def cost_by_flow() -> dict[str, Any]:
    """Retorna custos agregados por fluxo (endpoint).

    Cada fluxo (``process_job``, ``upload``, etc.) tem suas
    métricas isoladas.

    Returns:
        JSON com métricas por fluxo.
    """
    tracker = get_tracker()
    return {"data": tracker.summarize_by_flow(), "error": None}


@router.get("/by-step")
async def cost_by_step() -> dict[str, Any]:
    """Retorna custos agregados por etapa.

    Cada etapa (``global_sections``, ``per_equipment_narrative``,
    ``rag_embedding``) tem suas métricas isoladas.

    Returns:
        JSON com métricas por etapa.
    """
    tracker = get_tracker()
    return {"data": tracker.summarize_by_step(), "error": None}


@router.get("/by-model")
async def cost_by_model() -> dict[str, Any]:
    """Retorna custos agregados por modelo LLM.

    Returns:
        JSON com métricas por modelo.
    """
    tracker = get_tracker()
    return {"data": tracker.summarize_by_model(), "error": None}


@router.get("/by-job")
async def cost_by_job() -> dict[str, Any]:
    """Retorna custos agregados por job_id.

    Inclui detalhamento per-equipment para cada job.

    Returns:
        JSON com métricas por job.
    """
    tracker = get_tracker()
    return {"data": tracker.summarize_by_job(), "error": None}


@router.get("/ranking")
async def cost_ranking(top_n: int = 20) -> dict[str, Any]:
    """Retorna as chamadas mais caras ordenadas por custo.

    Args:
        top_n: Número de registros a retornar (query param).

    Returns:
        JSON com lista das chamadas mais caras.
    """
    tracker = get_tracker()
    return {"data": tracker.get_cost_ranking(top_n), "error": None}


@router.get("/records")
async def cost_records() -> dict[str, Any]:
    """Retorna todos os registros de uso em JSON.

    Returns:
        JSON com lista completa de registros.
    """
    import json

    tracker = get_tracker()
    raw = tracker.export_records_json()
    return {"data": json.loads(raw), "error": None}


@router.get("/records/csv")
async def cost_records_csv() -> PlainTextResponse:
    """Retorna todos os registros de uso em formato CSV.

    Returns:
        PlainTextResponse com CSV.
    """
    tracker = get_tracker()
    csv_content = tracker.export_records_csv()
    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=llm_usage_records.csv",
        },
    )


@router.post("/persist")
async def persist_records() -> dict[str, Any]:
    """Força persistência dos registros em disco.

    Returns:
        JSON com confirmação.
    """
    tracker = get_tracker()
    tracker.persist_now()
    return {
        "data": {
            "status": "persisted",
            "total_records": len(tracker.records),
        },
        "error": None,
    }


@router.delete("/records")
async def clear_records() -> dict[str, Any]:
    """Limpa todos os registros em memória.

    ATENÇÃO: Antes de limpar, os registros são persistidos em disco
    se o persist_path estiver configurado.

    Returns:
        JSON com confirmação.
    """
    tracker = get_tracker()
    tracker.persist_now()
    count = len(tracker.records)
    tracker.clear()
    return {
        "data": {
            "status": "cleared",
            "records_cleared": count,
        },
        "error": None,
    }
