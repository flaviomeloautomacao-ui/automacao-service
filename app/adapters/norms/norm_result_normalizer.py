"""Normalização de chunks vetoriais para entidades de domínio.

Converte resultados brutos da consulta vetorial (dicts com campos
do banco) em modelos estruturados usados pela aplicação, separando
o formato do banco do formato do domínio.

Uso::

    from app.adapters.norms.norm_result_normalizer import (
        RetrievedNormChunk,
        normalize_chunks,
        chunk_to_normative_excerpt,
    )

    normalized = normalize_chunks(raw_rows)
    excerpts = [chunk_to_normative_excerpt(c) for c in normalized]
"""

from __future__ import annotations

import re
from typing import Any, Optional

from loguru import logger
from pydantic import BaseModel, Field

from app.domain.entities import NormativeExcerpt


# ---------------------------------------------------------------------------
# Modelo intermediário — chunk normalizado
# ---------------------------------------------------------------------------


class RetrievedNormChunk(BaseModel):
    """Chunk normativo recuperado e normalizado.

    Separa o formato do banco (metadata JSON, campos brutos)
    do formato usado pela aplicação, evitando acoplamento direto.

    Attributes:
        chunk_id: Identificador do chunk no banco.
        source_title: Título da norma de origem (ex.: ``"ABNT NBR 16385.pdf"``).
        source_type: Formato do documento (ex.: ``"text/plain"``).
        source_url: URL de origem, se disponível.
        line_from: Linha inicial do trecho no documento original.
        line_to: Linha final do trecho no documento original.
        content: Texto bruto do chunk normativo.
        relevance_score: Score de similaridade (0.0–1.0), se disponível.
    """

    chunk_id: int | str
    source_title: str = "Norma não identificada"
    source_type: Optional[str] = None
    source_url: Optional[str] = None
    line_from: Optional[int] = None
    line_to: Optional[int] = None
    content: str
    relevance_score: Optional[float] = None

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# Rastreabilidade — citação normativa por chunk
# ---------------------------------------------------------------------------


class NormCitation(BaseModel):
    """Registro de citação normativa para rastreabilidade.

    Permite auditar quais chunks embasaram cada geração LLM.

    Attributes:
        chunk_id: ID do chunk no banco vetorial.
        source_title: Título da norma.
        line_from: Linha de início no documento original.
        line_to: Linha de fim no documento original.
        relevance_score: Score da busca vetorial.
    """

    chunk_id: int | str
    source_title: str
    line_from: Optional[int] = None
    line_to: Optional[int] = None
    relevance_score: Optional[float] = None

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# Contexto normativo recuperado — agrupa query + chunks por equipamento
# ---------------------------------------------------------------------------


class RetrievedNormContext(BaseModel):
    """Contexto normativo completo recuperado para um equipamento.

    Attributes:
        equipment_name: Nome do equipamento consultado.
        query_text: Texto da query semântica utilizada.
        chunks: Lista de chunks normalizados e filtrados.
        citations: Registros de citação para rastreabilidade.
    """

    equipment_name: str
    query_text: str
    chunks: list[RetrievedNormChunk] = Field(default_factory=list)
    citations: list[NormCitation] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Filtros de qualidade — chunks a descartar
# ---------------------------------------------------------------------------

_NOISE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ISBN\s*[\d\-]+", re.IGNORECASE),
    re.compile(r"Todos os direitos reservados", re.IGNORECASE),
    re.compile(r"^Prefácio\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^Sumário\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"© ABNT\b", re.IGNORECASE),
    re.compile(r"ABNT — Associação Brasileira de Normas Técnicas", re.IGNORECASE),
    re.compile(r"Esta Norma foi elaborada no Comitê", re.IGNORECASE),
    re.compile(r"^Índice\s*$", re.IGNORECASE | re.MULTILINE),
]

# Tamanho mínimo para considerar um chunk útil
_MIN_CONTENT_LENGTH = 40


# ---------------------------------------------------------------------------
# Funções públicas
# ---------------------------------------------------------------------------


def normalize_chunk(
    row: dict[str, Any],
    *,
    score: float | None = None,
) -> RetrievedNormChunk | None:
    """Normaliza uma linha bruta do banco em ``RetrievedNormChunk``.

    Extrai campos de ``metadata`` (JSON) e ``content``, tolerando
    campos parciais ou ausentes.

    Args:
        row: Dicionário com campos do banco (``id``, ``content``,
            ``metadata``, opcionalmente ``score``/``similarity``).
        score: Score de similaridade externo (sobrescreve o do row).

    Returns:
        ``RetrievedNormChunk`` normalizado, ou ``None`` se o chunk
        for inválido (vazio, muito curto, etc.).
    """
    content = (row.get("content") or "").strip()
    if not content or len(content) < _MIN_CONTENT_LENGTH:
        return None

    chunk_id = row.get("id", 0)

    # Extrair metadata (pode ser dict ou None)
    metadata = row.get("metadata") or {}
    if isinstance(metadata, str):
        import json
        try:
            metadata = json.loads(metadata)
        except (json.JSONDecodeError, TypeError):
            metadata = {}

    # Extrair campos do metadata
    source_title = metadata.get("title", "Norma não identificada")
    source_type = metadata.get("blobType")
    source_url = metadata.get("url", "")

    # Localização por linhas
    loc = metadata.get("loc", {})
    lines = loc.get("lines", {}) if isinstance(loc, dict) else {}
    line_from = lines.get("from") if isinstance(lines, dict) else None
    line_to = lines.get("to") if isinstance(lines, dict) else None

    # Score: priorizar argumento externo > campo do row
    final_score = score
    if final_score is None:
        final_score = row.get("score") or row.get("similarity")

    # Normalizar score para 0–1 se necessário
    if final_score is not None:
        try:
            final_score = float(final_score)
            # Cosine similarity pode ser negativo ou > 1 em edge cases
            final_score = max(0.0, min(1.0, final_score))
        except (TypeError, ValueError):
            final_score = None

    return RetrievedNormChunk(
        chunk_id=chunk_id,
        source_title=source_title or "Norma não identificada",
        source_type=source_type,
        source_url=source_url or None,
        line_from=line_from,
        line_to=line_to,
        content=content,
        relevance_score=final_score,
    )


def normalize_chunks(
    rows: list[dict[str, Any]],
) -> list[RetrievedNormChunk]:
    """Normaliza uma lista de linhas brutas do banco.

    Filtra chunks inválidos e retorna apenas os que passaram.

    Args:
        rows: Lista de dicts do banco vetorial.

    Returns:
        Lista de ``RetrievedNormChunk`` válidos.
    """
    results: list[RetrievedNormChunk] = []
    for row in rows:
        chunk = normalize_chunk(row)
        if chunk is not None:
            results.append(chunk)
    return results


def is_noise_chunk(chunk: RetrievedNormChunk) -> bool:
    """Verifica se um chunk é ruído editorial (capa, ISBN, prefácio etc.).

    Usa heurísticas simples de pattern matching para detectar
    chunks que não contêm requisitos técnicos normativos.

    Args:
        chunk: Chunk normalizado.

    Returns:
        ``True`` se o chunk parece ser ruído editorial.
    """
    content = chunk.content

    # Contar quantos padrões de ruído aparecem no conteúdo
    noise_hits = sum(
        1 for pattern in _NOISE_PATTERNS
        if pattern.search(content)
    )

    # Se mais de 1 padrão de ruído, considerar como noise
    if noise_hits >= 2:
        return True

    # Se score é baixo E tem 1 hit de ruído, considerar noise
    if noise_hits >= 1 and chunk.relevance_score is not None:
        if chunk.relevance_score < 0.3:
            return True

    return False


def filter_quality_chunks(
    chunks: list[RetrievedNormChunk],
    *,
    max_chunks: int = 6,
    min_score: float | None = None,
) -> list[RetrievedNormChunk]:
    """Filtra chunks por qualidade e limita quantidade.

    Aplica filtros de ruído editorial e score mínimo, depois
    limita ao ``max_chunks`` mais relevantes.

    Args:
        chunks: Lista de chunks normalizados.
        max_chunks: Quantidade máxima de chunks a retornar.
        min_score: Score mínimo de relevância (descarta abaixo).

    Returns:
        Lista filtrada e limitada de chunks.
    """
    filtered: list[RetrievedNormChunk] = []

    for chunk in chunks:
        # Filtro de score mínimo
        if min_score is not None and chunk.relevance_score is not None:
            if chunk.relevance_score < min_score:
                logger.info(
                    "Chunk descartado (score baixo) | id={} | title={} | score={:.3f} | min_score={}",
                    chunk.chunk_id,
                    chunk.source_title,
                    chunk.relevance_score,
                    min_score,
                )
                continue

        # Filtro de ruído editorial
        if is_noise_chunk(chunk):
            logger.debug(
                "Chunk descartado (ruído) | id={} | title={} | score={}",
                chunk.chunk_id,
                chunk.source_title,
                chunk.relevance_score,
            )
            continue

        filtered.append(chunk)

    # Limitar ao max_chunks mais relevantes
    if len(filtered) > max_chunks:
        filtered = filtered[:max_chunks]

    return filtered


def chunk_to_normative_excerpt(chunk: RetrievedNormChunk) -> NormativeExcerpt:
    """Converte um chunk normalizado para ``NormativeExcerpt`` do domínio.

    O ``NormativeExcerpt`` é o formato aceito pelo ``EquipmentLLMInput``
    e usado na montagem do prompt.

    Args:
        chunk: Chunk normalizado.

    Returns:
        ``NormativeExcerpt`` pronto para injeção no pipeline.
    """
    # Derivar seção a partir da localização por linhas, se disponível
    section: str | None = None
    if chunk.line_from is not None and chunk.line_to is not None:
        section = f"linhas {chunk.line_from}–{chunk.line_to}"

    # Truncar content para o limite do NormativeExcerpt (2000 chars)
    text = chunk.content
    if len(text) > 2000:
        text = text[:1997] + "…"

    # Limitar source ao max_length de NormativeExcerpt (200 chars)
    source = chunk.source_title
    if len(source) > 200:
        source = source[:197] + "…"

    return NormativeExcerpt(
        source=source,
        section=section,
        text=text,
        relevance_score=chunk.relevance_score,
    )


def chunks_to_normative_excerpts(
    chunks: list[RetrievedNormChunk],
) -> list[NormativeExcerpt]:
    """Converte lista de chunks normalizados para ``NormativeExcerpt[]``.

    Args:
        chunks: Lista de chunks normalizados.

    Returns:
        Lista de ``NormativeExcerpt`` para injeção no ``EquipmentLLMInput``.
    """
    return [chunk_to_normative_excerpt(c) for c in chunks]


def chunks_to_citations(
    chunks: list[RetrievedNormChunk],
) -> list[NormCitation]:
    """Converte chunks em registros de citação para rastreabilidade.

    Args:
        chunks: Chunks que foram efetivamente usados na geração.

    Returns:
        Lista de ``NormCitation`` para log/auditoria.
    """
    return [
        NormCitation(
            chunk_id=c.chunk_id,
            source_title=c.source_title,
            line_from=c.line_from,
            line_to=c.line_to,
            relevance_score=c.relevance_score,
        )
        for c in chunks
    ]
