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

from typing import TYPE_CHECKING, Any

from app.infrastructure.config import Settings
from app.infrastructure.config import get_settings as _get_settings
from app.infrastructure.logging import setup_logging

if TYPE_CHECKING:
    from loguru import Logger


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


# ── Placeholders (implementar quando adapters estiverem prontos) ─


def get_db() -> Any | None:
    """Placeholder — retorna a sessão/conexão com o banco de dados.

    Será implementado quando o adapter de banco de dados estiver pronto.
    Por enquanto retorna ``None``.

    Returns:
        None: Ainda não implementado.
    """
    return None


def get_storage() -> Any | None:
    """Placeholder — retorna o client de storage (Supabase).

    Será implementado quando o adapter de storage estiver pronto.
    Por enquanto retorna ``None``.

    Returns:
        None: Ainda não implementado.
    """
    return None


def get_llm() -> Any | None:
    """Placeholder — retorna o client de LLM (OpenRouter).

    Será implementado quando o adapter de LLM estiver pronto.
    Por enquanto retorna ``None``.

    Returns:
        None: Ainda não implementado.
    """
    return None
