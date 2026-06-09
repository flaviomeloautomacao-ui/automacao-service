"""Orquestrador de retrieval de normas ABNT para equipamentos.

Coordena o fluxo completo de recuperação de contexto normativo:
  1. Monta query semântica a partir do contexto do equipamento.
  2. Gera embedding da query via ``EmbeddingProvider``.
  3. Consulta a base vetorial via ``NormVectorRepository``.
  4. Normaliza e filtra resultados.
  5. Converte para ``NormativeExcerpt[]`` do domínio.
  6. Preserva rastreabilidade via ``NormCitation[]``.

Uso::

    retriever = ABNTRetriever(
        embedding_provider=provider,
        norm_repository=repo,
    )
    result = await retriever.retrieve_for_equipment(ctx, profile="dust")
    # result.excerpts → list[NormativeExcerpt]
    # result.citations → list[NormCitation]
    # result.norm_context → RetrievedNormContext

Integração com pipeline::

    # Em process_job.py, entre build_equipment_contexts
    # e build_all_equipment_prompt_contexts
    norm_map = await retriever.retrieve_for_all_equipments(
        equipment_contexts, profile=profile
    )
    equipment_llm_inputs = build_all_equipment_prompt_contexts(
        equipment_contexts,
        normas_aplicaveis=...,
        normative_contexts=norm_map,
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from app.domain.entities import EquipmentContext, NormativeExcerpt
from app.domain.entities.area_classification import AreaClassificationContext

from .area_norm_query_builder import build_area_norm_query
from .embedding_provider import EmbeddingError, EmbeddingProvider
from .norm_query_builder import build_equipment_norm_query
from .norm_repository import NormVectorRepository
from .norm_result_normalizer import (
    NormCitation,
    RetrievedNormChunk,
    RetrievedNormContext,
    chunks_to_citations,
    chunks_to_normative_excerpts,
    filter_quality_chunks,
    normalize_chunks,
)


# ---------------------------------------------------------------------------
# Configuração padrão do retriever
# ---------------------------------------------------------------------------

DEFAULT_TOP_K = 8
"""Quantidade de chunks buscados do banco (antes da filtragem)."""

DEFAULT_MAX_CHUNKS = 5
"""Quantidade máxima de chunks após filtragem de qualidade."""

DEFAULT_MIN_SCORE = 0.35
"""Score mínimo de similaridade para aceitar um chunk."""


# ---------------------------------------------------------------------------
# Resultado do retrieval por equipamento
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EquipmentRetrievalResult:
    """Resultado completo do retrieval normativo para um equipamento.

    Attributes:
        equipment_name: Nome do equipamento.
        excerpts: ``NormativeExcerpt[]`` para injeção no ``EquipmentLLMInput``.
        citations: ``NormCitation[]`` para log e rastreabilidade.
        norm_context: Contexto completo com query, chunks e metadados.
        query_text: Texto da query semântica usada.
        chunk_count: Quantidade de chunks retornados (após filtragem).
    """

    equipment_name: str
    excerpts: list[NormativeExcerpt] = field(default_factory=list)
    citations: list[NormCitation] = field(default_factory=list)
    norm_context: RetrievedNormContext | None = None
    query_text: str = ""
    chunk_count: int = 0


# ---------------------------------------------------------------------------
# Resultado do retrieval por área (Classificação de Áreas)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AreaRetrievalResult:
    """Resultado do retrieval normativo para uma área de classificação.

    Attributes:
        area_local: Identificação da área/local.
        excerpts: Lista de strings formatadas (norma + trecho) prontas para
            injeção em ``AreaClassificationContext.normative_context``.
        citations: ``NormCitation[]`` para auditoria e rastreabilidade.
        norm_context: Contexto completo com query, chunks e metadados.
        query_text: Texto da query semântica usada.
        chunk_count: Quantidade de chunks retornados (após filtragem).
    """

    area_local: str
    excerpts: list[str] = field(default_factory=list)
    citations: list[NormCitation] = field(default_factory=list)
    norm_context: RetrievedNormContext | None = None
    query_text: str = ""
    chunk_count: int = 0


# ---------------------------------------------------------------------------
# Retriever principal
# ---------------------------------------------------------------------------


class ABNTRetriever:
    """Retriever de normas ABNT com busca vetorial semântica.

    Responsável por:
    - Construir query contextual a partir do equipamento.
    - Gerar embedding da query.
    - Consultar a base vetorial.
    - Filtrar, normalizar e converter resultados.
    - Manter rastreabilidade dos chunks usados.

    O retriever é tolerante a falhas: se qualquer etapa falhar,
    retorna resultado vazio e loga o erro, sem interromper o pipeline.

    Args:
        embedding_provider: Provider de embeddings (OpenAI, etc.).
        norm_repository: Repositório vetorial de chunks normativos.
        top_k: Quantidade de chunks a buscar no banco.
        max_chunks: Quantidade máxima de chunks após filtragem.
        min_score: Score mínimo para aceitar um chunk.
    """

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        norm_repository: NormVectorRepository,
        top_k: int = DEFAULT_TOP_K,
        max_chunks: int = DEFAULT_MAX_CHUNKS,
        min_score: float = DEFAULT_MIN_SCORE,
    ) -> None:
        self._embedding = embedding_provider
        self._repo = norm_repository
        self._top_k = top_k
        self._max_chunks = max_chunks
        self._min_score = min_score

    def set_norm_table(self, table_name: str) -> None:
        """Seleciona a base vetorial adequada ao documento atual."""
        self._repo.set_table_name(table_name)

    async def retrieve_for_equipment(
        self,
        equipment_context: EquipmentContext,
        *,
        profile: str | None = None,
    ) -> EquipmentRetrievalResult:
        """Recupera contexto normativo para um único equipamento.

        Fluxo:
        1. Monta query semântica com base no contexto do equipamento.
        2. Gera embedding da query.
        3. Consulta a base vetorial.
        4. Normaliza e filtra chunks.
        5. Converte para ``NormativeExcerpt[]``.
        6. Gera ``NormCitation[]`` para rastreabilidade.

        Em caso de falha em qualquer etapa, retorna resultado vazio
        e loga o erro como warning, sem propagar exceções.

        Args:
            equipment_context: Contexto completo do equipamento.
            profile: Perfil de análise (para termos específicos).

        Returns:
            ``EquipmentRetrievalResult`` com excerpts e citações.
        """
        equip_name = equipment_context.equipment_name

        # 1. Montar query semântica
        try:
            query_text = build_equipment_norm_query(
                equipment_context,
                profile=profile,
            )
            logger.debug(
                "RAG | equip='{}' | query montada ({} chars): {}",
                equip_name,
                len(query_text),
                query_text[:200] + ("..." if len(query_text) > 200 else ""),
            )
        except Exception:
            logger.exception(
                "RAG | ERRO ao montar query | equip='{}'",
                equip_name,
            )
            return self._empty_result(equip_name)

        # 2. Gerar embedding da query
        try:
            logger.debug(
                "RAG | equip='{}' | gerando embedding...",
                equip_name,
            )
            query_embedding = await self._embedding.embed_text(query_text)
            logger.debug(
                "RAG | equip='{}' | embedding OK | dims={}",
                equip_name,
                len(query_embedding),
            )
        except EmbeddingError as exc:
            logger.warning(
                "RAG | ERRO embedding | equip='{}' | erro={}",
                equip_name,
                str(exc),
            )
            return self._empty_result(equip_name, query_text=query_text)
        except Exception:
            logger.exception(
                "RAG | ERRO inesperado no embedding | equip='{}'",
                equip_name,
            )
            return self._empty_result(equip_name, query_text=query_text)

        # 3. Consultar base vetorial
        try:
            logger.debug(
                "RAG | equip='{}' | buscando top_k={} na tabela '{}'",
                equip_name,
                self._top_k,
                self._repo._table_name,
            )
            raw_rows = await self._repo.search_by_embedding(
                query_embedding,
                top_k=self._top_k,
            )
            logger.debug(
                "RAG | equip='{}' | pgvector retornou {} rows",
                equip_name,
                len(raw_rows) if raw_rows else 0,
            )
        except Exception:
            logger.exception(
                "RAG | ERRO na busca vetorial (pgvector) | equip='{}'",
                equip_name,
            )
            return self._empty_result(equip_name, query_text=query_text)

        if not raw_rows:
            logger.info(
                "RAG | equip='{}' | nenhum chunk retornado pelo pgvector",
                equip_name,
            )
            return self._empty_result(equip_name, query_text=query_text)

        # 4. Normalizar e filtrar chunks
        normalized = normalize_chunks(raw_rows)
        filtered = filter_quality_chunks(
            normalized,
            max_chunks=self._max_chunks,
            min_score=self._min_score,
        )

        logger.debug(
            "RAG | equip='{}' | filtragem: {} raw → {} normalizados → {} após qualidade (min_score={})",
            equip_name,
            len(raw_rows),
            len(normalized),
            len(filtered),
            self._min_score,
        )

        if not filtered:
            logger.info(
                "RAG | equip='{}' | todos os {} chunks descartados na filtragem (score < {} ou ruído)",
                equip_name,
                len(raw_rows),
                self._min_score,
            )
            return self._empty_result(equip_name, query_text=query_text)

        # 5. Converter para NormativeExcerpt
        excerpts = chunks_to_normative_excerpts(filtered)

        # 6. Gerar citações para rastreabilidade
        citations = chunks_to_citations(filtered)

        # 7. Montar contexto completo
        norm_context = RetrievedNormContext(
            equipment_name=equip_name,
            query_text=query_text,
            chunks=filtered,
            citations=citations,
        )

        # Log detalhado de cada chunk aceito
        for i, c in enumerate(filtered, 1):
            score_str = f"{c.relevance_score:.3f}" if c.relevance_score is not None else "?"
            logger.info(
                "RAG | equip='{}' | chunk {}/{}: score={} fonte='{}' | trecho: '{}'",
                equip_name,
                i,
                len(filtered),
                score_str,
                c.source_title,
                c.content[:120].replace("\n", " ") + ("..." if len(c.content) > 120 else ""),
            )

        return EquipmentRetrievalResult(
            equipment_name=equip_name,
            excerpts=excerpts,
            citations=citations,
            norm_context=norm_context,
            query_text=query_text,
            chunk_count=len(filtered),
        )

    async def retrieve_for_all_equipments(
        self,
        equipment_contexts: list[EquipmentContext],
        *,
        profile: str | None = None,
    ) -> dict[str, list[NormativeExcerpt]]:
        """Recupera contexto normativo para todos os equipamentos.

        Retorna um mapa ``equipment_name → list[NormativeExcerpt]``
        compatível com o parâmetro ``normative_contexts`` de
        ``build_all_equipment_prompt_contexts()``.

        Em caso de falha para um equipamento, o mapa contém lista vazia
        para aquele equipamento (graceful degradation).

        Quando ``DEVLLM=true``, apenas o primeiro equipamento recebe
        retrieval real — os demais são ignorados (economia de chamadas).

        Args:
            equipment_contexts: Lista de contextos de equipamentos.
            profile: Perfil de análise.

        Returns:
            Dicionário com mapa de contexto normativo por equipamento.
        """
        norm_map: dict[str, list[NormativeExcerpt]] = {}
        retrieval_results: list[EquipmentRetrievalResult] = []

        total = len(equipment_contexts)

        # ── DEVLLM: RAG apenas para o 1º equipamento ─────────────
        from app.infrastructure.config import get_settings  # noqa: PLC0415

        devllm = get_settings().DEVLLM
        if devllm:
            logger.warning(
                "RAG | DEVLLM=true | Apenas o 1º equipamento usará retrieval RAG, "
                "os demais {} serão ignorados",
                max(total - 1, 0),
            )

        logger.info(
            "RAG ── INÍCIO ── | equipamentos={} | profile={} | "
            "top_k={} | max_chunks={} | min_score={}",
            total,
            profile,
            self._top_k,
            self._max_chunks,
            self._min_score,
        )

        for idx, ctx in enumerate(equipment_contexts):
            equip_name = ctx.equipment_name

            # DEVLLM: skip a partir do 2º equipamento
            if devllm and idx > 0:
                logger.info(
                    "RAG | [{}/{}] equip='{}' | DEVLLM skip — sem retrieval",
                    idx + 1,
                    total,
                    equip_name,
                )
                retrieval_results.append(self._empty_result(equip_name))
                continue

            logger.info(
                "RAG | [{}/{}] equip='{}' | iniciando retrieval...",
                idx + 1,
                total,
                equip_name,
            )

            result = await self.retrieve_for_equipment(ctx, profile=profile)
            retrieval_results.append(result)

            if result.excerpts:
                norm_map[equip_name.strip().lower()] = result.excerpts
                logger.info(
                    "RAG | [{}/{}] equip='{}' | OK — {} chunks recuperados | "
                    "fontes: {}",
                    idx + 1,
                    total,
                    equip_name,
                    result.chunk_count,
                    [c.source for c in result.excerpts],
                )
            else:
                logger.info(
                    "RAG | [{}/{}] equip='{}' | sem contexto normativo encontrado",
                    idx + 1,
                    total,
                    equip_name,
                )
            # Equipamentos sem retrieval não entram no mapa — isso é
            # intencional: build_all_equipment_prompt_contexts trata
            # chaves ausentes como lista vazia.

        # ── Resumo consolidado ────────────────────────────────────
        total_chunks = sum(r.chunk_count for r in retrieval_results)
        equipments_with_context = sum(1 for r in retrieval_results if r.chunk_count > 0)
        equipments_skipped = sum(1 for _ in range(1, total)) if devllm and total > 1 else 0
        all_sources: set[str] = set()
        for r in retrieval_results:
            if r.norm_context:
                for c in r.norm_context.chunks:
                    all_sources.add(c.source_title)

        logger.info(
            "RAG ── FIM ── | resultado: {}/{} equipamentos com contexto | "
            "total_chunks={} | fontes_únicas={}{}",
            equipments_with_context,
            total,
            total_chunks,
            sorted(all_sources) if all_sources else "(nenhuma)",
            f" | devllm_skipped={equipments_skipped}" if devllm else "",
        )

        return norm_map

    def get_retrieval_summary(
        self,
        results: list[EquipmentRetrievalResult],
    ) -> dict[str, Any]:
        """Gera resumo consolidado do retrieval para log/auditoria.

        Args:
            results: Lista de resultados do retrieval.

        Returns:
            Dicionário com métricas consolidadas.
        """
        total = len(results)
        with_context = sum(1 for r in results if r.chunk_count > 0)
        total_chunks = sum(r.chunk_count for r in results)

        sources: set[str] = set()
        for r in results:
            if r.norm_context:
                for c in r.norm_context.chunks:
                    sources.add(c.source_title)

        return {
            "total_equipments": total,
            "equipments_with_context": with_context,
            "equipments_without_context": total - with_context,
            "total_chunks_used": total_chunks,
            "unique_sources": sorted(sources),
            "per_equipment": {
                r.equipment_name: {
                    "chunks": r.chunk_count,
                    "query_chars": len(r.query_text),
                    "citations": len(r.citations),
                }
                for r in results
            },
        }

    @staticmethod
    def _empty_result(
        equip_name: str,
        *,
        query_text: str = "",
    ) -> EquipmentRetrievalResult:
        """Constrói resultado vazio (graceful degradation)."""
        return EquipmentRetrievalResult(
            equipment_name=equip_name,
            excerpts=[],
            citations=[],
            norm_context=None,
            query_text=query_text,
            chunk_count=0,
        )

    # =====================================================================
    # ÁREAS — Classificação de Áreas (IEC 60079-10-1/10-2)
    # =====================================================================

    async def retrieve_for_area(
        self,
        area_context: AreaClassificationContext,
        *,
        profile: str | None = "areas",
    ) -> AreaRetrievalResult:
        """Recupera contexto normativo para uma única área.

        Análogo a :meth:`retrieve_for_equipment`, porém orientado ao
        domínio de Classificação de Áreas. Em caso de falha em qualquer
        etapa, retorna resultado vazio sem propagar exceções.
        """
        area_name = area_context.area_local

        # 1. Montar query semântica
        try:
            query_text = build_area_norm_query(area_context, profile=profile)
            logger.debug(
                "RAG-Area | area='{}' | query montada ({} chars): {}",
                area_name,
                len(query_text),
                query_text[:200] + ("..." if len(query_text) > 200 else ""),
            )
        except Exception:
            logger.exception(
                "RAG-Area | ERRO ao montar query | area='{}'", area_name,
            )
            return self._empty_area_result(area_name)

        # 2. Gerar embedding
        try:
            query_embedding = await self._embedding.embed_text(query_text)
        except EmbeddingError as exc:
            logger.warning(
                "RAG-Area | ERRO embedding | area='{}' | erro={}",
                area_name, str(exc),
            )
            return self._empty_area_result(area_name, query_text=query_text)
        except Exception:
            logger.exception(
                "RAG-Area | ERRO inesperado no embedding | area='{}'", area_name,
            )
            return self._empty_area_result(area_name, query_text=query_text)

        # 3. Consultar base vetorial
        try:
            raw_rows = await self._repo.search_by_embedding(
                query_embedding, top_k=self._top_k,
            )
        except Exception:
            logger.exception(
                "RAG-Area | ERRO busca vetorial | area='{}'", area_name,
            )
            return self._empty_area_result(area_name, query_text=query_text)

        if not raw_rows:
            logger.info(
                "RAG-Area | area='{}' | nenhum chunk retornado pelo pgvector",
                area_name,
            )
            return self._empty_area_result(area_name, query_text=query_text)

        # 4. Normalizar/filtrar
        normalized = normalize_chunks(raw_rows)
        filtered = filter_quality_chunks(
            normalized,
            max_chunks=self._max_chunks,
            min_score=self._min_score,
        )

        if not filtered:
            logger.info(
                "RAG-Area | area='{}' | todos {} chunks descartados (min_score={})",
                area_name, len(raw_rows), self._min_score,
            )
            return self._empty_area_result(area_name, query_text=query_text)

        # 5. Converter chunks → strings legíveis para o prompt
        excerpts_str: list[str] = []
        for c in filtered:
            line_info = ""
            if c.line_from is not None and c.line_to is not None:
                line_info = f" (linhas {c.line_from}-{c.line_to})"
            excerpts_str.append(
                f"[{c.source_title}{line_info}] {c.content.strip()}"
            )

        # 6. Citações para rastreabilidade
        citations = chunks_to_citations(filtered)

        norm_context = RetrievedNormContext(
            equipment_name=area_name,
            query_text=query_text,
            chunks=filtered,
            citations=citations,
        )

        for i, c in enumerate(filtered, 1):
            score_str = (
                f"{c.relevance_score:.3f}" if c.relevance_score is not None else "?"
            )
            logger.info(
                "RAG-Area | area='{}' | chunk {}/{}: score={} fonte='{}' | trecho: '{}'",
                area_name, i, len(filtered), score_str, c.source_title,
                c.content[:120].replace("\n", " ") + ("..." if len(c.content) > 120 else ""),
            )

        return AreaRetrievalResult(
            area_local=area_name,
            excerpts=excerpts_str,
            citations=citations,
            norm_context=norm_context,
            query_text=query_text,
            chunk_count=len(filtered),
        )

    async def retrieve_for_all_areas(
        self,
        area_contexts: list[AreaClassificationContext],
        *,
        profile: str | None = "areas",
    ) -> dict[str, list[str]]:
        """Recupera contexto normativo para todas as áreas.

        Retorna um mapa ``area_local → list[str]`` com os trechos formatados
        prontos para preencher ``AreaClassificationContext.normative_context``.

        Em ``DEVLLM=true``, apenas a 1ª área recebe retrieval real.
        """
        from app.infrastructure.config import get_settings  # noqa: PLC0415

        norm_map: dict[str, list[str]] = {}
        results: list[AreaRetrievalResult] = []
        total = len(area_contexts)

        devllm = get_settings().DEVLLM
        if devllm:
            logger.warning(
                "RAG-Area | DEVLLM=true | Apenas a 1ª área usará retrieval RAG, "
                "as demais {} serão ignoradas",
                max(total - 1, 0),
            )

        logger.info(
            "RAG-Area ── INÍCIO ── | áreas={} | profile={} | "
            "top_k={} | max_chunks={} | min_score={}",
            total, profile, self._top_k, self._max_chunks, self._min_score,
        )

        for idx, ctx in enumerate(area_contexts):
            area_name = ctx.area_local

            if devllm and idx > 0:
                logger.info(
                    "RAG-Area | [{}/{}] area='{}' | DEVLLM skip",
                    idx + 1, total, area_name,
                )
                results.append(self._empty_area_result(area_name))
                continue

            logger.info(
                "RAG-Area | [{}/{}] area='{}' | iniciando retrieval...",
                idx + 1, total, area_name,
            )
            result = await self.retrieve_for_area(ctx, profile=profile)
            results.append(result)

            if result.excerpts:
                norm_map[area_name.strip().lower()] = result.excerpts
                logger.info(
                    "RAG-Area | [{}/{}] area='{}' | OK — {} chunks",
                    idx + 1, total, area_name, result.chunk_count,
                )
            else:
                logger.info(
                    "RAG-Area | [{}/{}] area='{}' | sem contexto normativo",
                    idx + 1, total, area_name,
                )

        # Resumo
        total_chunks = sum(r.chunk_count for r in results)
        areas_with_ctx = sum(1 for r in results if r.chunk_count > 0)
        all_sources: set[str] = set()
        for r in results:
            if r.norm_context:
                for c in r.norm_context.chunks:
                    all_sources.add(c.source_title)

        logger.info(
            "RAG-Area ── FIM ── | {}/{} áreas com contexto | "
            "total_chunks={} | fontes_únicas={}",
            areas_with_ctx, total, total_chunks,
            sorted(all_sources) if all_sources else "(nenhuma)",
        )

        return norm_map

    @staticmethod
    def _empty_area_result(
        area_name: str,
        *,
        query_text: str = "",
    ) -> AreaRetrievalResult:
        """Resultado vazio para retrieval de área (graceful degradation)."""
        return AreaRetrievalResult(
            area_local=area_name,
            excerpts=[],
            citations=[],
            norm_context=None,
            query_text=query_text,
            chunk_count=0,
        )
