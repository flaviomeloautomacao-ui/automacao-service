"""Ponto de entrada da aplicação FastAPI.

Responsável por criar a instância FastAPI, registrar routers
e configurar middlewares/eventos de ciclo de vida.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import costs, documents, health, process, uploads
from app.domain.errors import (
    BudgetExceededError,
    DBError,
    DomainError,
    LLMError,
    StorageError,
    TemplateError,
    ValidationError,
)
from app.infrastructure.dependencies import get_logger


def create_app() -> FastAPI:
    """Cria e configura a instância FastAPI.

    Returns:
        FastAPI: aplicação pronta com routers registrados.
    """
    app = FastAPI(
        title="Automação de Laudos Técnicos",
        description="Serviço de geração automatizada de laudos técnicos a partir de planilhas.",
        version="0.1.0",
    )

    # ── Routers ─────────────────────────────────────────────────
    app.include_router(health.router)
    app.include_router(uploads.router, prefix="/uploads", tags=["uploads"])
    app.include_router(process.router, prefix="/process", tags=["process"])
    app.include_router(documents.router, prefix="/reports", tags=["reports"])
    app.include_router(costs.router, prefix="/costs", tags=["costs"])

    # ── Exception Handlers ──────────────────────────────────────

    @app.exception_handler(ValidationError)
    async def _validation_error_handler(
        request: Request,
        exc: ValidationError,
    ) -> JSONResponse:
        """Retorna 422 para erros de validação de domínio."""
        return JSONResponse(
            status_code=422,
            content={
                "data": None,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": str(exc),
                    "details": exc.errors,
                },
            },
        )

    @app.exception_handler(StorageError)
    async def _storage_error_handler(
        request: Request,
        exc: StorageError,
    ) -> JSONResponse:
        """Retorna 502 para falhas de storage."""
        logger = get_logger()
        logger.error("StorageError: {}", str(exc))
        return JSONResponse(
            status_code=502,
            content={
                "data": None,
                "error": {
                    "code": "STORAGE_ERROR",
                    "message": "Falha no serviço de armazenamento.",
                },
            },
        )

    @app.exception_handler(DBError)
    async def _db_error_handler(
        request: Request,
        exc: DBError,
    ) -> JSONResponse:
        """Retorna 500 para falhas de banco de dados."""
        logger = get_logger()
        logger.error("DBError: {}", str(exc))
        return JSONResponse(
            status_code=500,
            content={
                "data": None,
                "error": {
                    "code": "DB_ERROR",
                    "message": "Falha no banco de dados.",
                },
            },
        )

    @app.exception_handler(LLMError)
    async def _llm_error_handler(
        request: Request,
        exc: LLMError,
    ) -> JSONResponse:
        """Retorna 502 para falhas de LLM."""
        logger = get_logger()
        logger.error("LLMError: {}", str(exc))
        return JSONResponse(
            status_code=502,
            content={
                "data": None,
                "error": {
                    "code": "LLM_ERROR",
                    "message": "Falha no serviço de geração de texto.",
                },
            },
        )

    @app.exception_handler(BudgetExceededError)
    async def _budget_error_handler(
        request: Request,
        exc: BudgetExceededError,
    ) -> JSONResponse:
        """Retorna 429 para estouro de budget LLM."""
        logger = get_logger()
        logger.error("BudgetExceededError: {}", str(exc))
        return JSONResponse(
            status_code=429,
            content={
                "data": None,
                "error": {
                    "code": "BUDGET_EXCEEDED",
                    "message": str(exc),
                },
            },
        )

    @app.exception_handler(TemplateError)
    async def _template_error_handler(
        request: Request,
        exc: TemplateError,
    ) -> JSONResponse:
        """Retorna 500 para falhas de renderização."""
        logger = get_logger()
        logger.error("TemplateError: {}", str(exc))
        return JSONResponse(
            status_code=500,
            content={
                "data": None,
                "error": {
                    "code": "TEMPLATE_ERROR",
                    "message": "Falha na geração do relatório.",
                },
            },
        )

    @app.exception_handler(DomainError)
    async def _domain_error_handler(
        request: Request,
        exc: DomainError,
    ) -> JSONResponse:
        """Catch-all para erros de domínio não tratados acima."""
        logger = get_logger()
        logger.error("DomainError: {}", str(exc))
        return JSONResponse(
            status_code=500,
            content={
                "data": None,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Erro interno do serviço.",
                },
            },
        )

    return app


app = create_app()
