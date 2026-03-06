"""Configuração de banco de dados.

Engine assíncrono (SQLAlchemy 2.0 + asyncpg), sessionmaker
e utilitário ``get_session`` para injeção de dependência via FastAPI.

Exemplo de uso::

    from app.infrastructure.db import get_session

    async for session in get_session():
        result = await session.execute(select(Upload))
"""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.infrastructure.config import get_settings

# ---------------------------------------------------------------------------
# Engine & SessionLocal (lazy — criados na primeira chamada)
# ---------------------------------------------------------------------------

_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_engine() -> AsyncEngine:
    """Cria (ou retorna) o ``AsyncEngine`` singleton.

    A connection string vem de ``Settings.DATABASE_URL``.
    Para PostgreSQL + asyncpg ela deve ter o formato::

        postgresql+asyncpg://user:password@host:5432/dbname

    Returns:
        AsyncEngine configurado.
    """
    global _engine  # noqa: PLW0603
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=(settings.ENV == "development"),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Retorna o ``async_sessionmaker`` singleton."""
    global _async_session_factory  # noqa: PLW0603
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_factory


# ---------------------------------------------------------------------------
# Dependência FastAPI — async generator
# ---------------------------------------------------------------------------


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Async generator que fornece uma ``AsyncSession`` por requisição.

    Uso com FastAPI ``Depends``::

        @router.get("/items")
        async def list_items(session: AsyncSession = Depends(get_session)):
            ...

    Yields:
        AsyncSession: sessão aberta; sofre commit/rollback conforme necessário.
    """
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------


def get_engine() -> AsyncEngine:
    """Acesso público ao engine (útil para scripts como ``init_db``)."""
    return _get_engine()
