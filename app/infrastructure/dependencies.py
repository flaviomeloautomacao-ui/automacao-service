"""Injeção de dependências (Dependency Injection).

Funções e providers que conectam portas do domínio
às implementações concretas dos adaptadores via FastAPI Depends.

Exemplo de uso em uma rota FastAPI::

    from fastapi import Depends
    from app.infrastructure.dependencies import get_settings, get_logger

    @router.get("/health")
    async def health(settings=Depends(get_settings)):
        return {"env": settings.ENV}
"""

from __future__ import annotations

from typing import TYPE_CHECKING, AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.config import Settings
from app.infrastructure.config import get_settings as _get_settings
from app.infrastructure.db import get_session as _get_session
from app.infrastructure.logging import setup_logging

if TYPE_CHECKING:
    from loguru import Logger

    from app.adapters.db.job_repository import JobRepository
    from app.adapters.db.llm_cost_repository import LLMCostRepository
    from app.adapters.db.repository import ReportRepository
    from app.adapters.llm.openrouter_client import OpenRouterClient
    from app.adapters.norms.abnt_retriever import ABNTRetriever
    from app.adapters.pdf.renderer import WeasyPdfRenderer
    from app.adapters.spreadsheet.parser import PandasSpreadsheetParser
    from app.adapters.spreadsheet.validator import BasicSpreadsheetValidator
    from app.adapters.storage.supabase_storage import SupabaseStorage
    from app.application.use_cases.process_job import ProcessJobUseCase
    from app.application.use_cases.process_upload import ProcessUploadUseCase
    from app.domain.services.budget_guard import BudgetGuard


# ── Settings ────────────────────────────────────────────────────


def get_settings() -> Settings:
    """Retorna o objeto Settings singleton (usa cache interno).

    Destinado a ser usado como ``Depends(get_settings)`` em rotas FastAPI.

    Returns:
        Settings: Configurações carregadas do ``.env`` / variáveis de ambiente.

    Example::

        settings = get_settings()
        print(settings.API_PORT)  # 8000
    """
    return _get_settings()


# ── Logger ──────────────────────────────────────────────────────

_logger: Logger | None = None


def get_logger() -> "Logger":
    """Retorna o logger global do projeto, inicializando-o se necessário.

    Na primeira chamada o logger é configurado com base no ``ENV``
    das settings atuais; chamadas subsequentes devolvem a mesma instância.

    Returns:
        Logger: Instância configurada do ``loguru.logger``.

    Example::

        logger = get_logger()
        logger.debug("Processando documento id={}", doc_id)
    """
    global _logger  # noqa: PLW0603
    if _logger is None:
        settings = get_settings()
        _logger = setup_logging(env=settings.ENV)
    return _logger


# ── Database Session ────────────────────────────────────────────


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Fornece uma ``AsyncSession`` por requisição via FastAPI Depends.

    Delegates to ``app.infrastructure.db.get_session``.

    Yields:
        AsyncSession: sessão pronta para uso.
    """
    async for session in _get_session():
        yield session


# ── Repository ──────────────────────────────────────────────────


async def get_repository(
    session: AsyncSession = Depends(get_db),
) -> "ReportRepository":
    """Fornece um ``ReportRepository`` vinculado à sessão da requisição.

    Args:
        session: Sessão async injetada via ``Depends(get_db)``.

    Returns:
        ReportRepository: repositório com sessão ativa.
    """
    from app.adapters.db.repository import ReportRepository  # noqa: PLC0415

    return ReportRepository(session)


# ── Parser ──────────────────────────────────────────────────────


def get_parser() -> "PandasSpreadsheetParser":
    """Retorna o parser de planilhas (pandas + openpyxl).

    Returns:
        PandasSpreadsheetParser: Implementação concreta de ``SpreadsheetParserPort``.
    """
    from app.adapters.spreadsheet.parser import PandasSpreadsheetParser  # noqa: PLC0415

    return PandasSpreadsheetParser()


# ── Validator ───────────────────────────────────────────────────


def get_validator() -> "BasicSpreadsheetValidator":
    """Retorna o validador determinístico de planilhas.

    Returns:
        BasicSpreadsheetValidator: Implementação concreta de ``SpreadsheetValidatorPort``.
    """
    from app.adapters.spreadsheet.validator import BasicSpreadsheetValidator  # noqa: PLC0415

    return BasicSpreadsheetValidator()


# ── Storage ─────────────────────────────────────────────────────


def get_storage() -> "SupabaseStorage":
    """Retorna o client de storage Supabase (singleton).

    Utiliza as configurações ``SUPABASE_URL`` e ``SUPABASE_SERVICE_ROLE_KEY``
    do Settings para construir o adaptador.
    Segredos **não** são registrados em logs.

    Returns:
        SupabaseStorage: Implementação concreta de ``StoragePort``.
    """
    from app.adapters.storage.supabase_storage import SupabaseStorage  # noqa: PLC0415

    settings = get_settings()
    logger = get_logger()
    logger.debug("Inicializando SupabaseStorage | url={}", settings.SUPABASE_URL)
    return SupabaseStorage(
        supabase_url=settings.SUPABASE_URL,
        service_role_key=settings.SUPABASE_SERVICE_ROLE_KEY,
    )


# ── LLM ─────────────────────────────────────────────────────────


def get_llm() -> "OpenRouterClient":
    """Retorna o client LLM configurado (real ou mock).

    Se ``LLM_MOCK_ENABLED=true``, retorna ``MockLLMClient`` que gera
    respostas determinísticas sem custo. Caso contrário, retorna
    ``OpenRouterClient`` que faz chamadas reais à API.

    Returns:
        Implementação concreta de ``LLMPort``.
    """
    settings = get_settings()

    if settings.LLM_MOCK_ENABLED:
        from app.adapters.llm.mock_client import MockLLMClient  # noqa: PLC0415

        get_logger().warning("LLM MOCK MODE ATIVO — respostas não são reais")
        return MockLLMClient()  # type: ignore[return-value]

    from app.adapters.llm.openrouter_client import OpenRouterClient  # noqa: PLC0415

    return OpenRouterClient(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
        model=settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        top_p=settings.LLM_TOP_P,
    )


# ── PDF Renderer ────────────────────────────────────────────────


def get_pdf_renderer() -> "WeasyPdfRenderer":
    """Retorna o renderer de PDF (WeasyPrint + Jinja2).

    Returns:
        WeasyPdfRenderer: Implementação concreta de ``PdfRendererPort``.
    """
    from app.adapters.pdf.renderer import WeasyPdfRenderer  # noqa: PLC0415

    return WeasyPdfRenderer()


# ── Use Case ────────────────────────────────────────────────────


async def get_use_case(
    repo: "ReportRepository" = Depends(get_repository),
) -> "ProcessUploadUseCase":
    """Monta o ``ProcessUploadUseCase`` com todas as dependências injetadas.

    Args:
        repo: Repositório injetado via ``Depends(get_repository)``.

    Returns:
        ProcessUploadUseCase: caso de uso pronto para execução.
    """
    from app.application.use_cases.process_upload import ProcessUploadUseCase  # noqa: PLC0415

    settings = get_settings()
    return ProcessUploadUseCase(
        repository=repo,
        storage=get_storage(),
        parser=get_parser(),
        validator=get_validator(),
        llm=get_llm(),
        pdf_renderer=get_pdf_renderer(),
        bucket=settings.SUPABASE_BUCKET,
    )


# ── Job Repository ──────────────────────────────────────────────


async def get_job_repository(
    session: AsyncSession = Depends(get_db),
) -> "JobRepository":
    """Fornece um ``JobRepository`` vinculado à sessão da requisição.

    Args:
        session: Sessão async injetada via ``Depends(get_db)``.

    Returns:
        JobRepository: repositório de jobs com sessão ativa.
    """
    from app.adapters.db.job_repository import JobRepository  # noqa: PLC0415

    return JobRepository(session)


# ── LLM Cost Repository ────────────────────────────────────────


async def get_llm_cost_repository(
    session: AsyncSession = Depends(get_db),
) -> "LLMCostRepository":
    """Fornece um ``LLMCostRepository`` vinculado à sessão da requisição.

    Args:
        session: Sessão async injetada via ``Depends(get_db)``.

    Returns:
        LLMCostRepository: repositório de custos LLM.
    """
    from app.adapters.db.llm_cost_repository import LLMCostRepository  # noqa: PLC0415

    return LLMCostRepository(session)


# ── Budget Guard ────────────────────────────────────────────────


def get_budget_guard() -> "BudgetGuard":
    """Retorna o BudgetGuard configurado.

    Returns:
        BudgetGuard: proteção contra gastos descontrolados.
    """
    from app.domain.services.budget_guard import BudgetGuard  # noqa: PLC0415

    settings = get_settings()
    return BudgetGuard(settings)


# ── ABNT Retriever (RAG Normativo) ──────────────────────────────


async def get_abnt_retriever() -> AsyncGenerator["ABNTRetriever | None", None]:
    """Monta o ``ABNTRetriever`` para busca vetorial de normas ABNT.

    Usa uma sessão de banco **dedicada** (isolada da sessão do
    ``JobRepository``) para que falhas em queries pgvector não
    envenenem a transação do pipeline de processamento.

    Retorna ``None`` se o RAG estiver desabilitado ou se a chave de
    embedding não estiver configurada (graceful degradation).

    Yields:
        ABNTRetriever configurado, ou None se indisponível.
    """
    from app.adapters.norms.abnt_retriever import ABNTRetriever  # noqa: PLC0415
    from app.adapters.norms.embedding_provider import OpenAIEmbeddingProvider  # noqa: PLC0415
    from app.adapters.norms.norm_repository import NormVectorRepository  # noqa: PLC0415
    from app.infrastructure.db import get_session as _get_rag_session  # noqa: PLC0415

    settings = get_settings()

    if not settings.RAG_ENABLED:
        get_logger().info("RAG normativo — desabilitado via RAG_ENABLED=false")
        yield None
        return

    api_key = settings.EMBEDDING_API_KEY or settings.OPENROUTER_API_KEY
    if not api_key:
        get_logger().warning(
            "RAG normativo — sem EMBEDDING_API_KEY ou OPENROUTER_API_KEY — retrieval desabilitado"
        )
        yield None
        return

    get_logger().info(
        "RAG normativo — inicializando | model={} | base_url={} | "
        "table_dha={} | table_areas={} | top_k={} | max_chunks={} | min_score={} | DEVLLM={}",
        settings.EMBEDDING_MODEL,
        settings.EMBEDDING_BASE_URL,
        settings.RAG_NORM_TABLE_DHA,
        settings.RAG_NORM_TABLE_AREAS,
        settings.RAG_TOP_K,
        settings.RAG_MAX_CHUNKS,
        settings.RAG_MIN_SCORE,
        settings.DEVLLM,
    )

    embedding_provider = OpenAIEmbeddingProvider(
        api_key=api_key,
        base_url=settings.EMBEDDING_BASE_URL,
        model=settings.EMBEDDING_MODEL,
    )

    # Sessão dedicada para RAG — isolada da sessão do JobRepository
    rag_session_gen = _get_rag_session()
    rag_session = await rag_session_gen.__anext__()
    try:
        norm_repo = NormVectorRepository(
            rag_session,
            table_name=settings.RAG_NORM_TABLE_DHA,
        )

        yield ABNTRetriever(
            embedding_provider=embedding_provider,
            norm_repository=norm_repo,
            top_k=settings.RAG_TOP_K,
            max_chunks=settings.RAG_MAX_CHUNKS,
            min_score=settings.RAG_MIN_SCORE,
        )
    finally:
        # Garante cleanup da sessão RAG (commit/rollback)
        try:
            await rag_session_gen.__anext__()
        except StopAsyncIteration:
            pass


# ── Process Job Use Case ────────────────────────────────────────


async def get_process_job_use_case(
    job_repo: "JobRepository" = Depends(get_job_repository),
    upload_uc: "ProcessUploadUseCase" = Depends(get_use_case),
    abnt_retriever: "ABNTRetriever | None" = Depends(get_abnt_retriever),
    cost_repo: "LLMCostRepository" = Depends(get_llm_cost_repository),
    budget_guard: "BudgetGuard" = Depends(get_budget_guard),
) -> "ProcessJobUseCase":
    """Monta o ``ProcessJobUseCase`` com dependências injetadas.

    Combina o ``JobRepository`` (para reportar progresso) com o
    ``ProcessUploadUseCase`` (para a lógica de pipeline),
    ``ABNTRetriever`` (RAG normativo), ``LLMCostRepository``
    (persistência de custos) e ``BudgetGuard`` (proteção de orçamento).

    Args:
        job_repo: Repositório de jobs/steps.
        upload_uc: Use case de processamento de upload.
        abnt_retriever: Retriever de normas ABNT (opcional).
        cost_repo: Repositório de custos LLM.
        budget_guard: Proteção de orçamento LLM.

    Returns:
        ProcessJobUseCase: caso de uso pronto para execução.
    """
    from app.application.use_cases.process_job import ProcessJobUseCase  # noqa: PLC0415

    return ProcessJobUseCase(
        job_repo=job_repo,
        upload_use_case=upload_uc,
        abnt_retriever=abnt_retriever,
        cost_repository=cost_repo,
        budget_guard=budget_guard,
    )
