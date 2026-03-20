"""Provider de embeddings para busca vetorial de normas.

Abstração desacoplada do provedor concreto (OpenAI, OpenRouter, etc.).
O retriever recebe um provider e não conhece detalhes de transporte.

Uso::

    provider = OpenAIEmbeddingProvider(api_key="sk-...")
    vector = await provider.embed_text("texto para busca")
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import httpx
from loguru import logger

from app.infrastructure.llm_cost_tracker import CostTimer, get_tracker


# ---------------------------------------------------------------------------
# Protocolo — interface abstrata
# ---------------------------------------------------------------------------


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Interface para geração de embeddings de texto."""

    async def embed_text(self, text: str) -> list[float]:
        """Gera embedding vetorial para um texto.

        Args:
            text: Texto de entrada (query ou documento).

        Returns:
            Lista de floats representando o vetor de embedding.

        Raises:
            EmbeddingError: Se a geração falhar.
        """
        ...


# ---------------------------------------------------------------------------
# Erro específico
# ---------------------------------------------------------------------------


class EmbeddingError(Exception):
    """Erro na geração de embedding."""

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause


# ---------------------------------------------------------------------------
# Implementação concreta — OpenAI-compatible API
# ---------------------------------------------------------------------------


class OpenAIEmbeddingProvider:
    """Provider de embeddings via API compatível com OpenAI.

    Funciona com OpenAI diretamente e com qualquer API que siga
    o mesmo contrato (e.g., endpoints self-hosted, Azure OpenAI).

    Args:
        api_key: Chave de API.
        base_url: URL base da API (padrão: OpenAI).
        model: Modelo de embedding (padrão: text-embedding-3-small).
        timeout: Timeout HTTP em segundos.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "text-embedding-3-small",
        timeout: float = 30.0,
    ) -> None:
        if not api_key:
            raise EmbeddingError("API key para embedding não configurada.")

        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._tracker = get_tracker()

        # Contexto de tracking (setado externamente)
        self._tracking_context: dict[str, str] = {}

        logger.debug(
            "OpenAIEmbeddingProvider inicializado | model={} | base_url={}",
            self._model,
            self._base_url,
        )

    def set_tracking_context(
        self,
        *,
        flow: str = "",
        step: str = "",
        job_id: str = "",
        equipment_name: str = "",
    ) -> None:
        """Define o contexto de tracking para as próximas chamadas."""
        self._tracking_context = {
            "flow": flow,
            "step": step,
            "job_id": job_id,
            "equipment_name": equipment_name,
        }

    async def embed_text(self, text: str) -> list[float]:
        """Gera embedding via API OpenAI-compatible.

        Args:
            text: Texto de entrada.

        Returns:
            Vetor de embedding como lista de floats.

        Raises:
            EmbeddingError: Se a chamada HTTP falhar ou retornar erro.
        """
        if not text or not text.strip():
            raise EmbeddingError("Texto vazio fornecido para embedding.")

        url = f"{self._base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "input": text.strip(),
            "model": self._model,
        }

        ctx = self._tracking_context
        timer = CostTimer()

        try:
            with timer:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(url, json=payload, headers=headers)

                    if response.status_code != 200:
                        detail = response.text[:500]
                        logger.error(
                            "Embedding API error | status={} | detail={}",
                            response.status_code,
                            detail,
                        )
                        raise EmbeddingError(
                            f"Embedding API retornou status {response.status_code}: {detail}"
                        )

                    data = response.json()
                    embedding = data["data"][0]["embedding"]

                    # Capturar usage da API
                    api_usage = data.get("usage")

                    logger.debug(
                        "Embedding gerado | model={} | dims={} | input_chars={}",
                        self._model,
                        len(embedding),
                        len(text),
                    )

            # Registrar uso com sucesso
            self._tracker.record_embedding(
                flow=ctx.get("flow", "unknown"),
                step=ctx.get("step", "rag_embedding"),
                provider="openai",
                model=self._model,
                input_text=text,
                duration_ms=timer.duration_ms,
                success=True,
                job_id=ctx.get("job_id", ""),
                equipment_name=ctx.get("equipment_name", ""),
                api_usage=api_usage,
                tokens_source="api" if api_usage else "estimate",
            )

            return embedding

        except EmbeddingError:
            self._tracker.record_embedding(
                flow=ctx.get("flow", "unknown"),
                step=ctx.get("step", "rag_embedding"),
                provider="openai",
                model=self._model,
                input_text=text,
                duration_ms=timer.duration_ms,
                success=False,
                error_message="Embedding API error",
                job_id=ctx.get("job_id", ""),
                equipment_name=ctx.get("equipment_name", ""),
            )
            raise
        except httpx.TimeoutException as exc:
            self._tracker.record_embedding(
                flow=ctx.get("flow", "unknown"),
                step=ctx.get("step", "rag_embedding"),
                provider="openai",
                model=self._model,
                input_text=text,
                duration_ms=timer.duration_ms,
                success=False,
                error_message=str(exc),
                job_id=ctx.get("job_id", ""),
                equipment_name=ctx.get("equipment_name", ""),
            )
            raise EmbeddingError(
                "Timeout ao gerar embedding",
                cause=exc,
            ) from exc
        except KeyError as exc:
            self._tracker.record_embedding(
                flow=ctx.get("flow", "unknown"),
                step=ctx.get("step", "rag_embedding"),
                provider="openai",
                model=self._model,
                input_text=text,
                duration_ms=timer.duration_ms,
                success=False,
                error_message=str(exc),
                job_id=ctx.get("job_id", ""),
                equipment_name=ctx.get("equipment_name", ""),
            )
            raise EmbeddingError(
                f"Resposta inesperada da API de embedding: campo ausente ({exc})",
                cause=exc,
            ) from exc
        except Exception as exc:
            self._tracker.record_embedding(
                flow=ctx.get("flow", "unknown"),
                step=ctx.get("step", "rag_embedding"),
                provider="openai",
                model=self._model,
                input_text=text,
                duration_ms=timer.duration_ms,
                success=False,
                error_message=str(exc),
                job_id=ctx.get("job_id", ""),
                equipment_name=ctx.get("equipment_name", ""),
            )
            raise EmbeddingError(
                f"Erro inesperado ao gerar embedding: {exc}",
                cause=exc,
            ) from exc
