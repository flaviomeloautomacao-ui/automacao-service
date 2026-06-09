"""Adaptador de normas técnicas — retrieval vetorial ABNT.

Consulta e validação contra bases de normas regulatórias/técnicas
usando busca vetorial semântica (RAG).

Módulos:
    abnt_retriever:         Orquestrador principal de retrieval.
    embedding_provider:     Abstração de geração de embeddings.
    norm_query_builder:     Montagem de query semântica contextual.
    norm_repository:        Consulta vetorial ao banco (pgvector).
    norm_result_normalizer: Normalização e filtragem de resultados.
"""

from .abnt_retriever import ABNTRetriever, AreaRetrievalResult, EquipmentRetrievalResult
from .area_norm_query_builder import build_area_norm_query
from .embedding_provider import EmbeddingError, EmbeddingProvider, OpenAIEmbeddingProvider
from .norm_query_builder import build_equipment_norm_query
from .norm_repository import NormVectorRepository
from .norm_result_normalizer import (
    NormCitation,
    RetrievedNormChunk,
    RetrievedNormContext,
    chunk_to_normative_excerpt,
    chunks_to_citations,
    chunks_to_normative_excerpts,
    filter_quality_chunks,
    normalize_chunks,
)

__all__ = [
    "ABNTRetriever",
    "AreaRetrievalResult",
    "EmbeddingError",
    "EmbeddingProvider",
    "EquipmentRetrievalResult",
    "NormCitation",
    "NormVectorRepository",
    "OpenAIEmbeddingProvider",
    "RetrievedNormChunk",
    "RetrievedNormContext",
    "build_area_norm_query",
    "build_equipment_norm_query",
    "chunk_to_normative_excerpt",
    "chunks_to_citations",
    "chunks_to_normative_excerpts",
    "filter_quality_chunks",
    "normalize_chunks",
]
