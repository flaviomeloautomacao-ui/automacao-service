"""Repositório de consulta vetorial para chunks normativos ABNT.

Implementa a busca vetorial usando a base ``konis_db`` existente
(ou tabela equivalente) via SQLAlchemy raw SQL com pgvector.

A consulta usa o operador ``<=>`` (cosine distance) do pgvector
para ordenar chunks por similaridade ao embedding da query.

Uso::

    from app.adapters.norms.norm_repository import NormVectorRepository

    repo = NormVectorRepository(session)
    rows = await repo.search_by_embedding(query_embedding, top_k=5)
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# Nome da tabela e coluna de embedding no banco vetorial
# ---------------------------------------------------------------------------

DEFAULT_TABLE_NAME = "konis_db"
DEFAULT_EMBEDDING_COLUMN = "embedding"
DEFAULT_CONTENT_COLUMN = "content"
DEFAULT_METADATA_COLUMN = "metadata"


# ---------------------------------------------------------------------------
# Repositório de normas vetoriais
# ---------------------------------------------------------------------------


class NormVectorRepository:
    """Repositório para busca vetorial em chunks normativos ABNT.

    Usa a tabela vetorial existente no banco (``konis_db``), que contém:
    - ``id``: identificador do chunk
    - ``content``: texto bruto do chunk
    - ``metadata``: JSON com metadados de origem
    - ``embedding``: vetor para busca semântica (pgvector)

    A busca é feita por cosine similarity usando o operador ``<=>``
    do pgvector.

    Args:
        session: Sessão SQLAlchemy assíncrona.
        table_name: Nome da tabela de chunks (padrão: ``"konis_db"``).
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        table_name: str = DEFAULT_TABLE_NAME,
    ) -> None:
        self._session = session
        self._table_name = table_name

    def set_table_name(self, table_name: str) -> None:
        """Atualiza a tabela vetorial alvo para o retrieval corrente."""
        self._table_name = table_name

    async def search_by_embedding(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 5,
        min_content_length: int = 30,
    ) -> list[dict[str, Any]]:
        """Busca chunks mais similares ao embedding da query.

        Usa cosine distance (``<=>``) do pgvector para ordenar.
        Retorna os ``top_k`` mais próximos com score de similaridade.

        Args:
            query_embedding: Vetor de embedding da query contextual.
            top_k: Quantidade máxima de resultados (padrão: 5).
            min_content_length: Tamanho mínimo do content para incluir
                no resultado (padrão: 30 chars).

        Returns:
            Lista de dicts com campos:
                - ``id``: ID do chunk
                - ``content``: texto bruto
                - ``metadata``: JSON de metadados
                - ``similarity``: score de similaridade (1 - cosine_distance)

        Raises:
            Exception: Se a consulta SQL falhar.
        """
        # Converter lista de floats para representação textual pgvector
        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        # Query com cosine similarity via pgvector
        # 1 - (embedding <=> query) = cosine similarity (0 a 1)
        sql = text(f"""
            SELECT
                id,
                {DEFAULT_CONTENT_COLUMN} AS content,
                {DEFAULT_METADATA_COLUMN} AS metadata,
                1 - ({DEFAULT_EMBEDDING_COLUMN} <=> (:query_embedding)::vector) AS similarity
            FROM "{self._table_name}"
            WHERE {DEFAULT_CONTENT_COLUMN} IS NOT NULL
              AND LENGTH({DEFAULT_CONTENT_COLUMN}) >= :min_len
            ORDER BY {DEFAULT_EMBEDDING_COLUMN} <=> (:query_embedding)::vector
            LIMIT :top_k
        """)

        try:
            result = await self._session.execute(
                sql,
                {
                    "query_embedding": embedding_str,
                    "min_len": min_content_length,
                    "top_k": top_k,
                },
            )

            rows = []
            for row in result.mappings().all():
                rows.append({
                    "id": row["id"],
                    "content": row["content"],
                    "metadata": row["metadata"],
                    "similarity": float(row["similarity"]) if row["similarity"] is not None else None,
                })

            logger.debug(
                "Busca vetorial concluída | table={} | top_k={} | resultados={}",
                self._table_name,
                top_k,
                len(rows),
            )

            return rows

        except Exception:
            logger.exception(
                "Falha na busca vetorial | table={} | top_k={}",
                self._table_name,
                top_k,
            )
            # Rollback para limpar estado de transação falha no PostgreSQL,
            # evitando InFailedSQLTransactionError em queries subsequentes.
            await self._session.rollback()
            raise

    async def search_by_embedding_with_filter(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 5,
        min_content_length: int = 30,
        title_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Busca com filtro opcional por título da norma no metadata.

        Extensão futura: permite filtrar por norma específica
        (e.g. ``"ABNT NBR 16385"``).

        Args:
            query_embedding: Vetor de embedding da query.
            top_k: Quantidade máxima de resultados.
            min_content_length: Tamanho mínimo do content.
            title_filter: String parcial para filtrar por ``metadata->>'title'``.
                Se ``None``, não aplica filtro.

        Returns:
            Lista de dicts com campos ``id``, ``content``, ``metadata``,
            ``similarity``.
        """
        if title_filter is None:
            return await self.search_by_embedding(
                query_embedding,
                top_k=top_k,
                min_content_length=min_content_length,
            )

        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        sql = text(f"""
            SELECT
                id,
                {DEFAULT_CONTENT_COLUMN} AS content,
                {DEFAULT_METADATA_COLUMN} AS metadata,
                1 - ({DEFAULT_EMBEDDING_COLUMN} <=> (:query_embedding)::vector) AS similarity
            FROM {self._table_name}
            WHERE {DEFAULT_CONTENT_COLUMN} IS NOT NULL
              AND LENGTH({DEFAULT_CONTENT_COLUMN}) >= :min_len
              AND {DEFAULT_METADATA_COLUMN}->>'title' ILIKE :title_filter
            ORDER BY {DEFAULT_EMBEDDING_COLUMN} <=> (:query_embedding)::vector
            LIMIT :top_k
        """)

        try:
            result = await self._session.execute(
                sql,
                {
                    "query_embedding": embedding_str,
                    "min_len": min_content_length,
                    "top_k": top_k,
                    "title_filter": f"%{title_filter}%",
                },
            )

            rows = []
            for row in result.mappings().all():
                rows.append({
                    "id": row["id"],
                    "content": row["content"],
                    "metadata": row["metadata"],
                    "similarity": float(row["similarity"]) if row["similarity"] is not None else None,
                })

            logger.debug(
                "Busca vetorial com filtro concluída | table={} | filter={} | resultados={}",
                self._table_name,
                title_filter,
                len(rows),
            )

            return rows

        except Exception:
            logger.exception(
                "Falha na busca vetorial com filtro | table={} | filter={}",
                self._table_name,
                title_filter,
            )
            await self._session.rollback()
            raise
