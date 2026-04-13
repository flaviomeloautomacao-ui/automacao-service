"""Caso de uso — processa um Job com atualização de progresso.

Orquestra o pipeline de geração de laudo reportando cada etapa
diretamente no banco via ``JobRepository``.

O pipeline busca TODOS os dados do banco (planilha, metadados do
relatório, equipamentos e imagens) — não recebe mais arquivo.

Etapas do pipeline (mapeadas às steps criadas pelo Next.js):
  1. upload_storage  — já concluída pelo Next.js
  2. data_processing — leitura + validação + agrupamento de dados do banco
  3. llm_analysis    — geração de seções narrativas via LLM
  4. pdf_rendering   — renderização HTML → PDF
  5. report_storage  — armazenamento do PDF + metadados

O front-end faz polling a cada 3s em ``GET /api/jobs/:id``
e exibe progresso em tempo real.
"""

from __future__ import annotations

import os
import traceback
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from loguru import logger

from app.adapters.db.job_repository import JobRepository
from app.adapters.storage.paths import report_pdf_path
from app.application.use_cases.process_upload import (
    ProcessUploadUseCase,
)
from app.domain.errors import BudgetExceededError, DomainError
from app.domain.services.equipment_context_builder import build_equipment_contexts
from app.domain.services.equipment_prompt_context import (
    build_all_equipment_prompt_contexts,
)
from app.domain.services.equipment_narrative_generator import (
    generate_all_equipment_narratives,
)
from app.domain.services.input_hasher import compute_input_hash
from app.domain.services.version_snapshot import compute_version_fingerprint
from app.infrastructure.llm_cost_tracker import get_tracker
from app.infrastructure.model_router import get_model_router

if TYPE_CHECKING:
    from app.adapters.db.llm_cost_repository import LLMCostRepository
    from app.adapters.norms.abnt_retriever import ABNTRetriever
    from app.domain.services.budget_guard import BudgetGuard


class ProcessJobUseCase:
    """Processa um job com atualização de progresso em tempo real.

    Delega a lógica de pipeline ao ``ProcessUploadUseCase`` existente
    mas intercepta cada etapa para reportar progresso.

    Args:
        job_repo: Repositório de jobs/steps.
        upload_use_case: Caso de uso original de processamento.
        abnt_retriever: Retriever de normas ABNT (opcional — RAG vetorial).
    """

    def __init__(
        self,
        *,
        job_repo: JobRepository,
        upload_use_case: ProcessUploadUseCase,
        abnt_retriever: "ABNTRetriever | None" = None,
        cost_repository: "LLMCostRepository | None" = None,
        budget_guard: "BudgetGuard | None" = None,
    ) -> None:
        self._job_repo = job_repo
        self._uc = upload_use_case
        self._abnt_retriever = abnt_retriever
        self._cost_repo = cost_repository
        self._budget_guard = budget_guard

    async def execute(
        self,
        job_id: str,
    ) -> dict[str, str]:
        """Executa o pipeline completo com reportagem de progresso.

        Busca todos os dados do banco de dados:
        - ``spreadsheet_rows`` → rows da planilha
        - ``reports`` → company_metadata (dados de capa)
        - ``report_equipments`` + ``equipment_images`` → equipamentos enriquecidos

        Args:
            job_id: UUID do job (criado pelo Next.js).

        Returns:
            Dicionário com report_id, pdf_url, pdf_path.
        """
        try:
            # ── Buscar dados do job ───────────────────────────────
            job = await self._job_repo.get_job(job_id)
            if job is None:
                raise DomainError(f"Job {job_id} não encontrado")

            profile = job.get("profile")

            # Validate profile is one of the expected values
            valid_profiles = {"dust", "gas", "vapors"}
            if not profile or profile not in valid_profiles:
                logger.warning(
                    "Job {} | Perfil inv\u00e1lido ou ausente: '{}' \u2014 usando 'dust' como default",
                    job_id, profile,
                )
                profile = "dust"

            # ── Iniciar processamento ─────────────────────────────
            await self._job_repo.update_job(
                job_id,
                status="processing",
                progress=10,
                current_step="Iniciando processamento…",
                started_at=datetime.now(timezone.utc),
            )

            # ── Step 2: data_processing ───────────────────────────
            await self._job_repo.start_step(job_id, "data_processing")
            await self._job_repo.update_job(
                job_id,
                progress=15,
                current_step="Lendo dados da planilha…",
            )

            # 2a) Busca rows da planilha do banco
            rows_dicts = await self._job_repo.get_spreadsheet_rows(job_id)
            logger.info(
                "Job {} | Rows carregados do banco | total={}",
                job_id,
                len(rows_dicts),
            )

            await self._job_repo.update_job(job_id, progress=20)

            # 2b) Busca metadados do relatório (company_metadata)
            company_metadata = await self._job_repo.get_report_metadata(job_id)
            logger.info(
                "Job {} | Report metadata carregado | has_data={}",
                job_id,
                company_metadata is not None,
            )

            # ── DEDUP CHECK: calcular hash do input e buscar duplicata ──
            try:
                input_hash = compute_input_hash(
                    rows_dicts, profile=profile, company_metadata=company_metadata
                )
                await self._job_repo.update_job(job_id, input_hash=input_hash)
                logger.info(
                    "Job {} | INPUT_HASH={}", job_id, input_hash[:16]
                )

                existing = await self._job_repo.find_done_job_by_hash(input_hash)
                if existing:
                    logger.info(
                        "Job {} | DEDUP_HIT | reutilizando resultado do job {}",
                        job_id,
                        existing["id"],
                    )
                    # Reutilizar PDF do job anterior
                    await self._job_repo.update_job(
                        job_id,
                        dedup_source_job_id=existing["id"],
                    )
                    await self._job_repo.mark_job_done(job_id, existing["pdf_path"])
                    return {
                        "report_id": "",
                        "pdf_url": "",
                        "pdf_path": existing["pdf_path"],
                        "dedup_source": existing["id"],
                    }
            except Exception:
                logger.warning(
                    "Job {} | DEDUP_CHECK falhou — continuando sem dedup",
                    job_id,
                )

            # ── BUDGET CHECK: verificar custo diário antes de prosseguir ──
            if self._budget_guard is not None:
                try:
                    from app.infrastructure.db import get_session as _get_budget_session  # noqa: PLC0415

                    session_gen = _get_budget_session()
                    budget_session = await session_gen.__anext__()
                    try:
                        await self._budget_guard.check_daily_budget(budget_session)
                    finally:
                        try:
                            await session_gen.__anext__()
                        except StopAsyncIteration:
                            pass
                except BudgetExceededError:
                    raise
                except Exception:
                    logger.warning(
                        "Job {} | DAILY_BUDGET_CHECK falhou — continuando",
                        job_id,
                    )

            # 2b.1) Injeta filename do job no metadata (para template)
            if company_metadata is None:
                company_metadata = {}
            raw_filename = job.get("filename") or ""
            # Remove extensão de arquivo para exibição no template
            company_metadata["filename"] = os.path.splitext(raw_filename)[0] if raw_filename else None

            await self._job_repo.update_job(
                job_id,
                progress=22,
                current_step="Carregando dados de equipamentos…",
            )

            # 2c) Busca equipamentos com imagens
            report_equipments = await self._job_repo.get_report_equipments_with_images(
                job_id
            )
            logger.info(
                "Job {} | Equipamentos carregados | total={}",
                job_id,
                len(report_equipments),
            )

            await self._job_repo.update_job(job_id, progress=25)

            # 2d) Constrói contextos estruturados por equipamento
            #     (fonte única de agrupamento para LLM e template)
            equipment_contexts = build_equipment_contexts(rows_dicts)
            logger.info(
                "Job {} | EquipmentContexts construídos | total={}",
                job_id,
                len(equipment_contexts),
            )

            # 2d.1) Converte contextos para formato dict do template Jinja2
            grouped_equipment = [ctx.to_template_dict() for ctx in equipment_contexts]

            # 2e) Enriquece equipamentos agrupados com dados de complementação
            grouped_equipment = self._enrich_equipments(
                grouped_equipment, report_equipments
            )

            # 2f) Recupera contexto normativo ABNT via RAG (se disponível)
            normative_contexts = None
            if self._abnt_retriever is not None:
                try:
                    logger.info(
                        "Job {} | RAG normativo — iniciando retrieval para {} equipamentos | profile={}",
                        job_id,
                        len(equipment_contexts),
                        profile,
                    )
                    await self._job_repo.update_job(
                        job_id,
                        progress=26,
                        current_step="Recuperando normas ABNT relevantes…",
                    )

                    # ── Setar contexto de tracking no embedding provider ──
                    if hasattr(self._abnt_retriever, '_embedding') and hasattr(self._abnt_retriever._embedding, 'set_tracking_context'):
                        self._abnt_retriever._embedding.set_tracking_context(
                            flow="process_job",
                            step="rag_embedding",
                            job_id=job_id,
                        )

                    normative_contexts = await self._abnt_retriever.retrieve_for_all_equipments(
                        equipment_contexts,
                        profile=profile,
                    )
                    equips_com_ctx = sum(1 for v in normative_contexts.values() if v)
                    total_excerpts = sum(len(v) for v in normative_contexts.values())
                    logger.info(
                        "Job {} | RAG normativo — concluído | {}/{} equipamentos com contexto | "
                        "total_excerpts={}",
                        job_id,
                        equips_com_ctx,
                        len(equipment_contexts),
                        total_excerpts,
                    )
                    if not normative_contexts:
                        logger.warning(
                            "Job {} | RAG normativo — nenhum contexto recuperado para nenhum equipamento",
                            job_id,
                        )
                except Exception:
                    logger.exception(
                        "Job {} | RAG normativo — ERRO — continuando pipeline sem contexto normativo",
                        job_id,
                    )
                    normative_contexts = None
            else:
                logger.info(
                    "Job {} | RAG normativo — desabilitado (retriever não configurado)",
                    job_id,
                )

            # 2g) Constrói payloads LLM per-equipment (validados + bounded)
            from app.adapters.llm.prompts import get_profile_config  # noqa: PLC0415

            profile_cfg = get_profile_config(profile)
            equipment_llm_inputs = build_all_equipment_prompt_contexts(
                equipment_contexts,
                normas_aplicaveis=profile_cfg["normas_principais"],
                normative_contexts=normative_contexts,
            )
            logger.info(
                "Job {} | EquipmentLLMInputs construídos | total={}",
                job_id,
                len(equipment_llm_inputs),
            )

            await self._job_repo.complete_step(job_id, "data_processing")
            await self._job_repo.update_job(
                job_id,
                progress=30,
                current_step="Dados processados com sucesso",
            )

            logger.info(
                "Job {} | data_processing concluído | {} equipamentos",
                job_id,
                len(grouped_equipment),
            )

            # ── Step 3: llm_analysis ──────────────────────────────
            await self._job_repo.start_step(job_id, "llm_analysis")
            await self._job_repo.update_job(
                job_id,
                progress=35,
                current_step="Gerando seções globais via IA…",
            )

            # 3a) Seções globais (introdução, metodologia, conclusão)
            # ── Setar contexto de tracking no LLM client ──
            if hasattr(self._uc._llm, 'set_tracking_context'):
                self._uc._llm.set_tracking_context(
                    flow="process_job",
                    step="global_sections",
                    job_id=job_id,
                )

            # ── Resolver modelo para seções globais (CP-01) ──
            model_router = get_model_router()
            global_decision = model_router.resolve_global()
            logger.info(
                "Job {} | MODEL_ROUTER CP-01 | model={} | reason={}",
                job_id, global_decision.model, global_decision.reason,
            )

            llm_sections = await self._uc._generate_llm_sections(
                rows_dicts,
                company_metadata,
                profile=profile,
                grouped_equipment=grouped_equipment,
                model_override=global_decision.model,
            )

            llm_sections_html = self._uc._normalize_llm_sections(llm_sections)

            await self._job_repo.update_job(
                job_id,
                progress=50,
                current_step="Gerando recomendações por equipamento…",
            )

            # 3b) Per-equipment generation (recomendações + justificativas)
            async def _on_equipment_progress(completed: int, total: int) -> None:
                # Map equipment progress to 50-70 range
                pct = 50 + int((completed / max(total, 1)) * 20)
                await self._job_repo.update_job(
                    job_id,
                    progress=pct,
                    current_step=f"Equipamento {completed}/{total}…",
                )

            from app.adapters.llm.openrouter_client import OpenRouterClient  # noqa: PLC0415

            llm_client = self._uc._llm
            if isinstance(llm_client, OpenRouterClient):
                # ── Setar contexto de tracking para per-equipment ──
                llm_client.set_tracking_context(
                    flow="process_job",
                    step="per_equipment_narrative",
                    job_id=job_id,
                )

                # ── Wrapper que aceita model_override como 3º argumento ──
                async def llm_call_fn(
                    system: str,
                    user: str,
                    model_override: str | None = None,
                ) -> str:
                    return await llm_client.call_chat(
                        system, user, model_override=model_override,
                    )
            else:
                # Fallback: wrap generate_sections (shouldn't happen in prod)
                async def llm_call_fn(  # type: ignore[misc]
                    system: str,
                    user: str,
                    model_override: str | None = None,
                ) -> str:
                    import json as _json  # noqa: PLC0415
                    ctx = {"rows": rows_dicts, "profile": profile}
                    result = await llm_client.generate_sections(ctx)
                    return _json.dumps(result)

            equipment_generation_results = await generate_all_equipment_narratives(
                llm_inputs=equipment_llm_inputs,
                llm_call=llm_call_fn,
                max_concurrency=1,
                on_progress=_on_equipment_progress,
                profile=profile,
                model_router=model_router,
            )

            # 3c) Attach results to grouped_equipment for template rendering
            grouped_equipment = self._attach_equipment_narratives(
                grouped_equipment,
                equipment_generation_results,
            )

            logger.info(
                "Job {} | Per-equipment geração concluída | total={} | fallbacks={}",
                job_id,
                len(equipment_generation_results),
                sum(1 for r in equipment_generation_results if r.source == "fallback"),
            )

            # ── Persistir tracking de custos e registrar log final ──
            cost_tracker = get_tracker()
            cost_tracker.persist_now()
            job_records = [r for r in cost_tracker.records if r.job_id == job_id]
            total_cost = 0.0
            total_tokens_used = 0
            total_calls = 0
            if job_records:
                total_cost = sum(r.estimated_cost_usd for r in job_records)
                total_calls = len(job_records)
                total_tokens_used = sum(r.total_tokens for r in job_records)
                gen_calls = sum(1 for r in job_records if r.call_type == "generation")
                emb_calls = sum(1 for r in job_records if r.call_type == "embedding")
                logger.info(
                    "Job {} | LLM_COST RESUMO | chamadas={} (gen={}, emb={}) | "
                    "custo_total=${:.6f}",
                    job_id, total_calls, gen_calls, emb_calls, total_cost,
                )

            # ── Flush custos para o banco de dados ──
            if self._cost_repo is not None and job_records:
                try:
                    saved = await self._cost_repo.save_batch(
                        cost_tracker.records, job_id
                    )
                    await self._cost_repo.update_job_cost_summary(
                        job_id=job_id,
                        total_cost_usd=total_cost,
                        total_tokens=total_tokens_used,
                        call_count=total_calls,
                    )
                    # Limpar registros do job na memória para evitar duplicatas
                    cost_tracker.clear_records_for_job(job_id)
                    logger.info(
                        "Job {} | COST_DB_FLUSH | saved={} records",
                        job_id,
                        saved,
                    )
                except Exception:
                    logger.warning(
                        "Job {} | COST_DB_FLUSH falhou — custos apenas em memória/arquivo",
                        job_id,
                    )

            # ── Budget check per-job (pós-execução) ──
            if self._budget_guard is not None:
                try:
                    self._budget_guard.check_job_budget(
                        current_cost=total_cost,
                        current_calls=total_calls,
                        job_id=job_id,
                    )
                except BudgetExceededError:
                    logger.warning(
                        "Job {} | BUDGET_EXCEEDED pós-LLM | cost=${:.4f} calls={}",
                        job_id,
                        total_cost,
                        total_calls,
                    )
                    # Job já foi processado — log warning mas não falha

            await self._job_repo.complete_step(job_id, "llm_analysis")
            await self._job_repo.update_job(
                job_id,
                progress=70,
                current_step="Recomendações geradas com sucesso",
            )

            logger.info("Job {} | llm_analysis concluído", job_id)

            # ── Step 4: pdf_rendering ─────────────────────────────
            await self._job_repo.start_step(job_id, "pdf_rendering")
            await self._job_repo.update_job(
                job_id,
                progress=75,
                current_step="Gerando PDF do laudo…",
            )

            pdf_bytes = self._uc._render_pdf(
                rows_dicts,
                llm_sections_html,
                company_metadata,
                profile=profile,
                grouped_equipment=grouped_equipment,
            )

            await self._job_repo.complete_step(job_id, "pdf_rendering")
            await self._job_repo.update_job(
                job_id,
                progress=85,
                current_step="PDF gerado com sucesso",
            )

            logger.info(
                "Job {} | pdf_rendering concluído | {} bytes",
                job_id,
                len(pdf_bytes),
            )

            # ── Step 5: report_storage ────────────────────────────
            await self._job_repo.start_step(job_id, "report_storage")
            await self._job_repo.update_job(
                job_id,
                progress=90,
                current_step="Armazenando relatório…",
            )

            # Armazena PDF diretamente no storage (sem tabela legada)
            report_id = str(uuid.uuid4())
            pdf_path = report_pdf_path(report_id, version=1)
            await self._uc._storage.put_bytes(
                self._uc._bucket,
                pdf_path,
                pdf_bytes,
                content_type="application/pdf",
            )
            pdf_url = await self._uc._storage.get_signed_url(
                self._uc._bucket,
                pdf_path,
            )
            logger.info(
                "Job {} | PDF armazenado | report_id={} | path={}",
                job_id,
                report_id,
                pdf_path,
            )

            await self._job_repo.complete_step(job_id, "report_storage")

            # ── Pipeline Version Snapshot ─────────────────────────
            if self._cost_repo is not None:
                try:
                    from app.adapters.llm.prompts import build_system_prompt  # noqa: PLC0415
                    from app.infrastructure.config import get_settings as _get_snap_settings  # noqa: PLC0415

                    snap_settings = _get_snap_settings()
                    sys_prompt = build_system_prompt(profile)
                    output_schema = {
                        "recomendacoes_tecnicas": "list",
                        "justificativas_tecnicas": "list",
                    }
                    rag_config = {
                        "top_k": snap_settings.RAG_TOP_K,
                        "max_chunks": snap_settings.RAG_MAX_CHUNKS,
                        "min_score": snap_settings.RAG_MIN_SCORE,
                    }

                    prompt_hash, schema_hash = compute_version_fingerprint(
                        system_prompt=sys_prompt,
                        output_schema=output_schema,
                        rag_config=rag_config,
                        llm_model=snap_settings.LLM_MODEL,
                        embedding_model=snap_settings.EMBEDDING_MODEL,
                    )

                    version_id = await self._cost_repo.find_or_create_pipeline_version(
                        prompt_version="1.0",
                        schema_version="1.0",
                        rag_strategy="abnt_vector" if self._abnt_retriever else "none",
                        llm_model=snap_settings.LLM_MODEL,
                        embedding_model=snap_settings.EMBEDDING_MODEL,
                        prompt_hash=prompt_hash,
                        schema_hash=schema_hash,
                        rag_top_k=snap_settings.RAG_TOP_K,
                        rag_max_chunks=snap_settings.RAG_MAX_CHUNKS,
                        rag_min_score=snap_settings.RAG_MIN_SCORE,
                        config_snapshot={
                            "llm_model": snap_settings.LLM_MODEL,
                            "embedding_model": snap_settings.EMBEDDING_MODEL,
                            "rag_enabled": snap_settings.RAG_ENABLED,
                            "rag_top_k": snap_settings.RAG_TOP_K,
                            "rag_max_chunks": snap_settings.RAG_MAX_CHUNKS,
                            "rag_min_score": snap_settings.RAG_MIN_SCORE,
                            "profile": profile,
                        },
                    )

                    if version_id:
                        await self._cost_repo.link_job_to_version(job_id, version_id)
                        logger.info(
                            "Job {} | VERSION_SNAPSHOT | version_id={}",
                            job_id,
                            version_id,
                        )
                except Exception:
                    logger.warning(
                        "Job {} | VERSION_SNAPSHOT falhou — continuando sem versionamento",
                        job_id,
                    )

            # ── Finalizar job ─────────────────────────────────────
            await self._job_repo.mark_job_done(job_id, pdf_path)

            logger.info(
                "Job {} | Pipeline CONCLUÍDO | report_id={} | pdf_path={}",
                job_id,
                report_id,
                pdf_path,
            )

            return {
                "report_id": report_id,
                "pdf_url": pdf_url,
                "pdf_path": pdf_path,
            }

        except BudgetExceededError as exc:
            logger.error("Job {} | Budget excedido: {}", job_id, str(exc))
            await self._fail_job(
                job_id,
                error_code="BUDGET_EXCEEDED",
                error_message=str(exc),
                step_name=await self._current_processing_step(job_id),
            )
            raise

        except DomainError as exc:
            logger.error("Job {} | Erro de domínio: {}", job_id, str(exc))
            await self._fail_job(
                job_id,
                error_code=type(exc).__name__.upper(),
                error_message=str(exc),
                step_name=await self._current_processing_step(job_id),
            )
            raise

        except Exception as exc:
            logger.error(
                "Job {} | Erro inesperado: {}\n{}",
                job_id,
                str(exc),
                traceback.format_exc(),
            )
            await self._fail_job(
                job_id,
                error_code="INTERNAL_ERROR",
                error_message=f"Erro inesperado: {str(exc)}",
                step_name=await self._current_processing_step(job_id),
            )
            raise

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _enrich_equipments(
        grouped_equipment: list[dict[str, Any]],
        report_equipments: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Enriquece equipamentos agrupados com dados de complementação.

        Mescla dados de ``report_equipments`` (complementação do usuário)
        nos equipamentos agrupados pela planilha. A ligação é feita por
        nome de equipamento (case-insensitive + strip).

        Adiciona aos equipamentos agrupados:
        - ``local_instalacao``, ``funcao_operacional``, ``observacoes_extras``
        - ``images``: lista de dicts com URLs de imagens do Cloudinary

        Args:
            grouped_equipment: Equipamentos agrupados das rows da planilha.
            report_equipments: Equipamentos do relatório com imagens.

        Returns:
            Lista de equipamentos enriquecidos.
        """
        # Cria mapa de lookup por nome (case-insensitive)
        report_map: dict[str, dict[str, Any]] = {}
        for req in report_equipments:
            key = (req.get("equipment_name") or "").strip().lower()
            if key:
                report_map[key] = req

        for eq in grouped_equipment:
            key = (eq.get("nome") or "").strip().lower()
            complement = report_map.get(key)
            if complement:
                eq["local_instalacao"] = complement.get("local_instalacao") or ""
                eq["funcao_operacional"] = complement.get("funcao_operacional") or ""
                eq["observacoes_extras"] = complement.get("observacoes_extras") or ""
                eq["images"] = complement.get("images", [])
            else:
                eq["local_instalacao"] = ""
                eq["funcao_operacional"] = ""
                eq["observacoes_extras"] = ""
                eq["images"] = []

        return grouped_equipment

    @staticmethod
    def _attach_equipment_narratives(
        grouped_equipment: list[dict[str, Any]],
        generation_results: list,
    ) -> list[dict[str, Any]]:
        """Anexa narrativas geradas pelo LLM aos equipamentos agrupados.

        Liga por nome de equipamento (case-insensitive). Cada equipamento
        recebe as chaves ``recomendacoes_tecnicas`` e ``justificativas_tecnicas``
        como listas de dicts prontas para o template Jinja2.

        Args:
            grouped_equipment: Equipamentos agrupados (mutáveis).
            generation_results: Lista de ``EquipmentGenerationResult``.

        Returns:
            Lista de equipamentos com narrativas anexadas.
        """
        # Mapa de lookup por nome (case-insensitive)
        result_map: dict[str, Any] = {}
        for gen_result in generation_results:
            key = gen_result.equipment_name.strip().lower()
            result_map[key] = gen_result

        for eq in grouped_equipment:
            key = (eq.get("nome") or "").strip().lower()
            gen_result = result_map.get(key)

            if gen_result is not None:
                output = gen_result.output
                eq["recomendacoes_tecnicas"] = [
                    r.model_dump() for r in output.recomendacoes_tecnicas
                ]
                eq["justificativas_tecnicas"] = [
                    j.model_dump() for j in output.justificativas_tecnicas
                ]
                eq["narrative_source"] = gen_result.source
            else:
                eq["recomendacoes_tecnicas"] = []
                eq["justificativas_tecnicas"] = []
                eq["narrative_source"] = "none"

        return grouped_equipment

    async def _fail_job(
        self,
        job_id: str,
        error_code: str,
        error_message: str,
        step_name: str | None = None,
    ) -> None:
        """Marca job e step corrente como falhos.

        Usa uma sessão NOVA para garantir que a gravação de erro funcione
        mesmo se a sessão original estiver em estado inválido (rollback pendente).
        """
        from app.infrastructure.db import get_session as _get_session  # noqa: PLC0415

        try:
            session_gen = _get_session()
            session = await session_gen.__anext__()
            try:
                fresh_repo = JobRepository(session)
                if step_name:
                    await fresh_repo.fail_step(job_id, step_name, error_message)
                await fresh_repo.mark_job_failed(job_id, error_code, error_message)
            finally:
                # Ensure generator cleanup runs (commit/rollback)
                try:
                    await session_gen.__anext__()
                except StopAsyncIteration:
                    pass
        except Exception as inner_exc:
            logger.error(
                "Job {} | Falha ao marcar job como error: {}",
                job_id,
                str(inner_exc),
            )

    async def _current_processing_step(self, job_id: str) -> str | None:
        """Retorna o nome da step atualmente em 'processing'.

        Usa sessão nova para funcionar mesmo quando a sessão principal
        está em estado inválido.
        """
        from app.infrastructure.db import get_session as _get_session  # noqa: PLC0415

        try:
            session_gen = _get_session()
            session = await session_gen.__anext__()
            try:
                fresh_repo = JobRepository(session)
                steps = await fresh_repo.get_steps(job_id)
                for step in steps:
                    if step["status"] == "processing":
                        return step["name"]
                return None
            finally:
                try:
                    await session_gen.__anext__()
                except StopAsyncIteration:
                    pass
        except Exception:
            return None
