"""Rastreabilidade de custo e uso de LLM por endpoint/fluxo.

Camada de observabilidade que registra cada chamada real ao LLM ou
embedding, incluindo tokens consumidos, custo estimado, duração e
metadados de contexto (job, equipamento, etapa).

Uso::

    from app.infrastructure.llm_cost_tracker import get_tracker, LLMUsageRecord

    tracker = get_tracker()

    # Registrar uma chamada
    tracker.record(LLMUsageRecord(
        flow="process_job",
        step="per_equipment_narrative",
        provider="openrouter",
        model="openai/gpt-4o",
        call_type="generation",
        input_tokens=1500,
        output_tokens=800,
        duration_ms=3200,
        success=True,
        job_id="abc-123",
        equipment_name="Moinho de Martelos",
    ))

    # Agregar métricas
    summary = tracker.summarize()
    by_flow = tracker.summarize_by_flow()

Dados sāo mantidos em memória no processo e opcionalmente
persistidos em arquivo JSON para análise posterior.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger


# ---------------------------------------------------------------------------
# Tabela de custos por modelo (USD por 1K tokens)
# ---------------------------------------------------------------------------

MODEL_PRICING: dict[str, dict[str, float]] = {
    # ── OpenRouter / OpenAI ────────────────────────────────────────
    "openai/gpt-4o": {
        "input_per_1k": 0.0025,
        "output_per_1k": 0.010,
    },
    "openai/gpt-4o-mini": {
        "input_per_1k": 0.00015,
        "output_per_1k": 0.0006,
    },
    "openai/gpt-4-turbo": {
        "input_per_1k": 0.01,
        "output_per_1k": 0.03,
    },
    "openai/gpt-4.1": {
        "input_per_1k": 0.002,
        "output_per_1k": 0.008,
    },
    "openai/gpt-4.1-mini": {
        "input_per_1k": 0.0004,
        "output_per_1k": 0.0016,
    },
    "openai/gpt-4.1-nano": {
        "input_per_1k": 0.0001,
        "output_per_1k": 0.0004,
    },
    # ── Anthropic ──────────────────────────────────────────────────
    "anthropic/claude-3.5-sonnet": {
        "input_per_1k": 0.003,
        "output_per_1k": 0.015,
    },
    "anthropic/claude-3-haiku": {
        "input_per_1k": 0.00025,
        "output_per_1k": 0.00125,
    },
    # ── Google ─────────────────────────────────────────────────────
    "google/gemini-pro-1.5": {
        "input_per_1k": 0.00125,
        "output_per_1k": 0.005,
    },
    "google/gemini-flash-1.5": {
        "input_per_1k": 0.000075,
        "output_per_1k": 0.0003,
    },
    "google/gemini-2.5-flash": {
        "input_per_1k": 0.0003,
        "output_per_1k": 0.0025,
    },
    # ── DeepSeek ───────────────────────────────────────────────────
    "deepseek/deepseek-chat-v3-0324": {
        "input_per_1k": 0.0002,
        "output_per_1k": 0.00077,
    },
    # ── Embedding ──────────────────────────────────────────────────
    "text-embedding-3-small": {
        "input_per_1k": 0.00002,
        "output_per_1k": 0.0,
    },    # OpenRouter usa prefixo "openai/" — mantemos o mesmo custo
    "openai/text-embedding-3-small": {
        "input_per_1k": 0.00002,
        "output_per_1k": 0.0,
    },    "text-embedding-3-large": {
        "input_per_1k": 0.00013,
        "output_per_1k": 0.0,
    },
    "text-embedding-ada-002": {
        "input_per_1k": 0.0001,
        "output_per_1k": 0.0,
    },
}

# Pricing fallback para modelos desconhecidos (USA GPT-4o como referência)
_FALLBACK_PRICING = {"input_per_1k": 0.0025, "output_per_1k": 0.010}

# Estimativa de tokens por caractere (para quando não há dados reais)
_CHARS_PER_TOKEN_ESTIMATE = 4.0


def estimate_tokens(text: str) -> int:
    """Estima número de tokens a partir do comprimento do texto.

    Usa a heurística de ~4 caracteres por token para modelos GPT/
    compatíveis. Para português técnico, essa proporção é uma
    aproximação razoável.

    Esta é uma ESTIMATIVA. Para dados reais, use os valores retornados
    pelo provider na resposta da API.

    Args:
        text: Texto de entrada.

    Returns:
        Número estimado de tokens.
    """
    if not text:
        return 0
    return max(1, int(len(text) / _CHARS_PER_TOKEN_ESTIMATE))


def get_model_pricing(model: str) -> dict[str, float]:
    """Retorna pricing para um modelo específico.

    Args:
        model: Identificador do modelo (e.g. ``openai/gpt-4o``).

    Returns:
        Dict com ``input_per_1k`` e ``output_per_1k`` em USD.
    """
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]

    # Tenta match parcial
    for key, pricing in MODEL_PRICING.items():
        if key in model or model in key:
            return pricing

    return _FALLBACK_PRICING


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Calcula custo em USD para uma chamada LLM.

    Args:
        model: Identificador do modelo.
        input_tokens: Número de tokens de entrada.
        output_tokens: Número de tokens de saída.

    Returns:
        Custo estimado em USD.
    """
    pricing = get_model_pricing(model)
    input_cost = (input_tokens / 1000) * pricing["input_per_1k"]
    output_cost = (output_tokens / 1000) * pricing["output_per_1k"]
    return round(input_cost + output_cost, 8)


# ---------------------------------------------------------------------------
# Registro de uso
# ---------------------------------------------------------------------------


@dataclass
class LLMUsageRecord:
    """Registro individual de uma chamada LLM/embedding.

    Attributes:
        flow: Nome do fluxo/endpoint (e.g. ``process_job``, ``upload``).
        step: Etapa dentro do fluxo (e.g. ``global_sections``,
            ``per_equipment_narrative``, ``rag_embedding``).
        provider: Nome do provider (``openrouter``, ``openai``).
        model: Identificador do modelo utilizado.
        call_type: Tipo da chamada: ``generation``, ``embedding``.
        input_tokens: Tokens de entrada (real se disponível, senão estimativa).
        output_tokens: Tokens de saída (real se disponível, senão 0 para embedding).
        total_tokens: Total de tokens (input + output).
        estimated_cost_usd: Custo estimado em USD.
        duration_ms: Duração da chamada em milissegundos.
        success: Se a chamada foi bem-sucedida.
        error_message: Mensagem de erro, se aplicável.
        timestamp: ISO timestamp da chamada.
        job_id: ID do job associado (se aplicável).
        equipment_name: Nome do equipamento (se chamada per-equipment).
        report_id: ID do relatório (se aplicável).
        tokens_source: ``"api"`` se tokens vieram da resposta, ``"estimate"`` se estimados.
        prompt_chars: Comprimento do prompt em caracteres.
        response_chars: Comprimento da resposta em caracteres.
    """

    flow: str
    step: str
    provider: str
    model: str
    call_type: str  # "generation" | "embedding"
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    duration_ms: float = 0.0
    success: bool = True
    error_message: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    job_id: str = ""
    equipment_name: str = ""
    report_id: str = ""
    tokens_source: str = "estimate"
    prompt_chars: int = 0
    response_chars: int = 0
    retry_attempt: int | None = None

    def __post_init__(self) -> None:
        """Calcula campos derivados se não fornecidos."""
        if self.total_tokens == 0 and (self.input_tokens or self.output_tokens):
            self.total_tokens = self.input_tokens + self.output_tokens
        if self.estimated_cost_usd == 0.0 and self.total_tokens > 0:
            self.estimated_cost_usd = calculate_cost(
                self.model, self.input_tokens, self.output_tokens
            )


# ---------------------------------------------------------------------------
# Tracker principal
# ---------------------------------------------------------------------------


class LLMCostTracker:
    """Registra e agrega chamadas LLM para rastreabilidade de custo.

    Thread-safe via lock. Mantém registros em memória e opcionalmente
    persiste em arquivo JSON a cada N registros.

    Attributes:
        records: Lista de todos os registros capturados.
        persist_path: Caminho do arquivo JSON de persistência.
        auto_persist_interval: Persiste a cada N registros (0 = desabilitado).
    """

    def __init__(
        self,
        *,
        persist_path: str | Path | None = None,
        auto_persist_interval: int = 10,
    ) -> None:
        self._records: list[LLMUsageRecord] = []
        self._lock = threading.Lock()
        self._persist_path = Path(persist_path) if persist_path else None
        self._auto_persist_interval = auto_persist_interval

    @property
    def records(self) -> list[LLMUsageRecord]:
        """Retorna cópia dos registros (thread-safe)."""
        with self._lock:
            return list(self._records)

    def record(self, usage: LLMUsageRecord) -> None:
        """Registra uma chamada LLM.

        Args:
            usage: Registro de uso preenchido.
        """
        with self._lock:
            self._records.append(usage)
            count = len(self._records)

        # Log estruturado
        logger.info(
            "LLM_COST | flow={} | step={} | model={} | type={} | "
            "in_tok={} | out_tok={} | total_tok={} | cost=${:.6f} | "
            "duration={}ms | success={} | tokens_src={} | "
            "job={} | equip={}",
            usage.flow,
            usage.step,
            usage.model,
            usage.call_type,
            usage.input_tokens,
            usage.output_tokens,
            usage.total_tokens,
            usage.estimated_cost_usd,
            int(usage.duration_ms),
            usage.success,
            usage.tokens_source,
            usage.job_id or "-",
            usage.equipment_name or "-",
        )

        # Auto-persist
        if (
            self._persist_path
            and self._auto_persist_interval > 0
            and count % self._auto_persist_interval == 0
        ):
            self._persist()

    def record_generation(
        self,
        *,
        flow: str,
        step: str,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        prompt_text: str = "",
        response_text: str = "",
        duration_ms: float = 0.0,
        success: bool = True,
        error_message: str = "",
        job_id: str = "",
        equipment_name: str = "",
        tokens_source: str = "estimate",
        api_usage: dict[str, Any] | None = None,
    ) -> LLMUsageRecord:
        """Registra uma chamada de geração LLM com cálculo automático.

        Se ``api_usage`` for fornecido (dados do provider), usa tokens reais.
        Caso contrário, estima a partir do comprimento dos textos.

        Args:
            flow: Nome do fluxo.
            step: Etapa do fluxo.
            provider: Nome do provider.
            model: Modelo utilizado.
            input_tokens: Tokens de entrada (0 = estimar).
            output_tokens: Tokens de saída (0 = estimar).
            prompt_text: Texto do prompt (para estimativa se tokens=0).
            response_text: Texto da resposta (para estimativa se tokens=0).
            duration_ms: Duração em ms.
            success: Se obteve sucesso.
            error_message: Mensagem de erro.
            job_id: ID do job.
            equipment_name: Nome do equipamento.
            tokens_source: Fonte dos dados de token.
            api_usage: Dict com ``prompt_tokens``, ``completion_tokens``
                retornado pela API.

        Returns:
            O registro criado.
        """
        if api_usage:
            input_tokens = api_usage.get("prompt_tokens", input_tokens)
            output_tokens = api_usage.get("completion_tokens", output_tokens)
            tokens_source = "api"

        if input_tokens == 0 and prompt_text:
            input_tokens = estimate_tokens(prompt_text)
            tokens_source = "estimate"
        if output_tokens == 0 and response_text:
            output_tokens = estimate_tokens(response_text)
            if tokens_source != "api":
                tokens_source = "estimate"

        record = LLMUsageRecord(
            flow=flow,
            step=step,
            provider=provider,
            model=model,
            call_type="generation",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            success=success,
            error_message=error_message,
            job_id=job_id,
            equipment_name=equipment_name,
            tokens_source=tokens_source,
            prompt_chars=len(prompt_text),
            response_chars=len(response_text),
        )
        self.record(record)
        return record

    def record_embedding(
        self,
        *,
        flow: str,
        step: str,
        provider: str,
        model: str,
        input_tokens: int = 0,
        input_text: str = "",
        duration_ms: float = 0.0,
        success: bool = True,
        error_message: str = "",
        job_id: str = "",
        equipment_name: str = "",
        tokens_source: str = "estimate",
        api_usage: dict[str, Any] | None = None,
    ) -> LLMUsageRecord:
        """Registra uma chamada de embedding com cálculo automático.

        Args:
            flow: Nome do fluxo.
            step: Etapa do fluxo.
            provider: Nome do provider.
            model: Modelo de embedding.
            input_tokens: Tokens de entrada (0 = estimar).
            input_text: Texto de entrada (para estimativa).
            duration_ms: Duração em ms.
            success: Se obteve sucesso.
            error_message: Mensagem de erro.
            job_id: ID do job.
            equipment_name: Nome do equipamento.
            tokens_source: Fonte dos tokens.
            api_usage: Dict com ``total_tokens`` retornado pela API.

        Returns:
            O registro criado.
        """
        if api_usage:
            input_tokens = api_usage.get("total_tokens", input_tokens)
            tokens_source = "api"

        if input_tokens == 0 and input_text:
            input_tokens = estimate_tokens(input_text)
            tokens_source = "estimate"

        record = LLMUsageRecord(
            flow=flow,
            step=step,
            provider=provider,
            model=model,
            call_type="embedding",
            input_tokens=input_tokens,
            output_tokens=0,
            duration_ms=duration_ms,
            success=success,
            error_message=error_message,
            job_id=job_id,
            equipment_name=equipment_name,
            tokens_source=tokens_source,
            prompt_chars=len(input_text),
        )
        self.record(record)
        return record

    # ------------------------------------------------------------------
    # Agregação
    # ------------------------------------------------------------------

    def summarize(self) -> dict[str, Any]:
        """Retorna sumário geral de todas as chamadas registradas.

        Returns:
            Dict com métricas agregadas.
        """
        records = self.records
        if not records:
            return {"total_records": 0, "total_cost_usd": 0.0}

        total_cost = sum(r.estimated_cost_usd for r in records)
        total_input = sum(r.input_tokens for r in records)
        total_output = sum(r.output_tokens for r in records)
        total_duration = sum(r.duration_ms for r in records)
        success_count = sum(1 for r in records if r.success)
        generation_count = sum(1 for r in records if r.call_type == "generation")
        embedding_count = sum(1 for r in records if r.call_type == "embedding")

        return {
            "total_records": len(records),
            "total_cost_usd": round(total_cost, 6),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "total_duration_ms": round(total_duration, 1),
            "avg_cost_per_call_usd": round(total_cost / len(records), 6),
            "avg_duration_ms": round(total_duration / len(records), 1),
            "success_count": success_count,
            "error_count": len(records) - success_count,
            "generation_calls": generation_count,
            "embedding_calls": embedding_count,
            "models_used": sorted(set(r.model for r in records)),
            "tokens_from_api": sum(1 for r in records if r.tokens_source == "api"),
            "tokens_estimated": sum(1 for r in records if r.tokens_source == "estimate"),
        }

    def summarize_by_flow(self) -> dict[str, Any]:
        """Agrega métricas por fluxo (endpoint/job type).

        Returns:
            Dict com chaves = nome do fluxo, valores = métricas agregadas.
        """
        records = self.records
        flows: dict[str, list[LLMUsageRecord]] = {}
        for r in records:
            flows.setdefault(r.flow, []).append(r)

        result: dict[str, Any] = {}
        for flow_name, flow_records in flows.items():
            result[flow_name] = self._aggregate_records(flow_records)
        return result

    def summarize_by_step(self) -> dict[str, Any]:
        """Agrega métricas por etapa (step).

        Returns:
            Dict com chaves = nome da etapa, valores = métricas agregadas.
        """
        records = self.records
        steps: dict[str, list[LLMUsageRecord]] = {}
        for r in records:
            steps.setdefault(r.step, []).append(r)

        result: dict[str, Any] = {}
        for step_name, step_records in steps.items():
            result[step_name] = self._aggregate_records(step_records)
        return result

    def summarize_by_model(self) -> dict[str, Any]:
        """Agrega métricas por modelo.

        Returns:
            Dict com chaves = nome do modelo, valores = métricas agregadas.
        """
        records = self.records
        models: dict[str, list[LLMUsageRecord]] = {}
        for r in records:
            models.setdefault(r.model, []).append(r)

        result: dict[str, Any] = {}
        for model_name, model_records in models.items():
            result[model_name] = self._aggregate_records(model_records)
        return result

    def summarize_by_job(self) -> dict[str, Any]:
        """Agrega métricas por job_id.

        Returns:
            Dict com chaves = job_id, valores = métricas agregadas.
        """
        records = self.records
        jobs: dict[str, list[LLMUsageRecord]] = {}
        for r in records:
            key = r.job_id or "(sem job)"
            jobs.setdefault(key, []).append(r)

        result: dict[str, Any] = {}
        for job_id, job_records in jobs.items():
            agg = self._aggregate_records(job_records)
            # Adicionar detalhes por equipamento
            equip_map: dict[str, list[LLMUsageRecord]] = {}
            for r in job_records:
                if r.equipment_name:
                    equip_map.setdefault(r.equipment_name, []).append(r)
            if equip_map:
                agg["per_equipment"] = {
                    name: self._aggregate_records(recs)
                    for name, recs in equip_map.items()
                }
            result[job_id] = agg
        return result

    def get_cost_ranking(self, top_n: int = 20) -> list[dict[str, Any]]:
        """Retorna as chamadas mais caras ordenadas por custo.

        Args:
            top_n: Número de registros a retornar.

        Returns:
            Lista de dicts com os registros mais caros.
        """
        records = sorted(
            self.records,
            key=lambda r: r.estimated_cost_usd,
            reverse=True,
        )
        return [asdict(r) for r in records[:top_n]]

    def export_records_json(self) -> str:
        """Exporta todos os registros como JSON string.

        Returns:
            JSON string formatada.
        """
        records = self.records
        return json.dumps(
            [asdict(r) for r in records],
            indent=2,
            ensure_ascii=False,
        )

    def export_records_csv(self) -> str:
        """Exporta todos os registros como CSV string.

        Returns:
            CSV string com header.
        """
        if not self._records:
            return ""

        fields = [
            "timestamp", "flow", "step", "provider", "model", "call_type",
            "input_tokens", "output_tokens", "total_tokens",
            "estimated_cost_usd", "duration_ms", "success",
            "tokens_source", "job_id", "equipment_name",
            "prompt_chars", "response_chars", "error_message",
        ]

        lines = [",".join(fields)]
        for r in self.records:
            d = asdict(r)
            row = []
            for f in fields:
                val = d.get(f, "")
                val_str = str(val)
                if "," in val_str or '"' in val_str:
                    val_str = f'"{val_str}"'
                row.append(val_str)
            lines.append(",".join(row))

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate_records(records: list[LLMUsageRecord]) -> dict[str, Any]:
        """Agrega métricas de uma lista de registros.

        Args:
            records: Lista de registros para agregar.

        Returns:
            Dict com métricas agregadas.
        """
        if not records:
            return {"count": 0, "total_cost_usd": 0.0}

        total_cost = sum(r.estimated_cost_usd for r in records)
        total_input = sum(r.input_tokens for r in records)
        total_output = sum(r.output_tokens for r in records)
        total_duration = sum(r.duration_ms for r in records)
        gen_count = sum(1 for r in records if r.call_type == "generation")
        emb_count = sum(1 for r in records if r.call_type == "embedding")
        success_count = sum(1 for r in records if r.success)

        return {
            "count": len(records),
            "total_cost_usd": round(total_cost, 6),
            "avg_cost_usd": round(total_cost / len(records), 6) if records else 0,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "avg_input_tokens": round(total_input / len(records)),
            "avg_output_tokens": round(total_output / len(records)),
            "total_duration_ms": round(total_duration, 1),
            "avg_duration_ms": round(total_duration / len(records), 1),
            "generation_calls": gen_count,
            "embedding_calls": emb_count,
            "success_rate": round(success_count / len(records), 3),
            "models": sorted(set(r.model for r in records)),
        }

    def _persist(self) -> None:
        """Persiste registros em arquivo JSON."""
        if not self._persist_path:
            return
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "summary": self.summarize(),
                "records": [asdict(r) for r in self._records],
            }
            self._persist_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.debug(
                "LLM_COST | Registros persistidos em {} | total={}",
                self._persist_path,
                len(self._records),
            )
        except Exception as exc:
            logger.warning(
                "LLM_COST | Falha ao persistir registros: {}",
                str(exc),
            )

    def persist_now(self) -> None:
        """Força persistência imediata dos registros."""
        self._persist()

    def clear(self) -> None:
        """Limpa todos os registros em memória."""
        with self._lock:
            self._records.clear()

    def clear_records_for_job(self, job_id: str) -> None:
        """Remove registros de um job específico da memória.

        Chamado após persistência bem-sucedida no banco.
        Evita acúmulo de registros em servidores de longa duração.

        Args:
            job_id: ID do job cujos registros devem ser removidos.
        """
        with self._lock:
            before = len(self._records)
            self._records = [r for r in self._records if r.job_id != job_id]
            removed = before - len(self._records)
        logger.debug(
            "CostTracker: limpou {} registros do job {} (restantes: {})",
            removed,
            job_id,
            len(self._records),
        )


# ---------------------------------------------------------------------------
# Timer context manager para medir duração
# ---------------------------------------------------------------------------


class CostTimer:
    """Context manager para medir duração de chamadas LLM.

    Uso::

        timer = CostTimer()
        with timer:
            response = await client.post(...)
        print(timer.duration_ms)
    """

    def __init__(self) -> None:
        self._start: float = 0.0
        self._end: float = 0.0

    def __enter__(self) -> "CostTimer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args: Any) -> None:
        self._end = time.perf_counter()

    @property
    def duration_ms(self) -> float:
        """Duração em milissegundos."""
        return round((self._end - self._start) * 1000, 1)


# ---------------------------------------------------------------------------
# Singleton global
# ---------------------------------------------------------------------------

_tracker_instance: LLMCostTracker | None = None
_tracker_lock = threading.Lock()


def get_tracker() -> LLMCostTracker:
    """Retorna o tracker singleton.

    O tracker é inicializado na primeira chamada com persistência
    no diretório ``output/`` do projeto.

    Returns:
        LLMCostTracker: Instância global do tracker.
    """
    global _tracker_instance  # noqa: PLW0603
    if _tracker_instance is None:
        with _tracker_lock:
            if _tracker_instance is None:
                persist_path = (
                    Path(__file__).resolve().parents[2]
                    / "output"
                    / "llm_usage_log.json"
                )
                _tracker_instance = LLMCostTracker(
                    persist_path=persist_path,
                    auto_persist_interval=5,
                )
                logger.info(
                    "LLM_COST | Tracker inicializado | persist={}",
                    persist_path,
                )
    return _tracker_instance
