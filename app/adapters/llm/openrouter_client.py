"""Cliente OpenRouter para geração de seções do laudo via LLM.

Implementa ``LLMPort`` utilizando httpx ``AsyncClient`` para chamadas
à API do OpenRouter (compatível com OpenAI ``/chat/completions``).

Recursos:
- Retry automático com *tenacity* para timeout, 429 e 5xx.
- Validação JSON da resposta com 1 retry usando prompt reforçado.
- Logging estruturado (sem vazar API key).

Exemplo de uso::

    from app.adapters.llm.openrouter_client import OpenRouterClient

    client = OpenRouterClient(
        api_key="sk-or-...",
        base_url="https://openrouter.ai/api/v1",
        model="openai/gpt-4o",
    )
    sections = await client.generate_sections(context)
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from loguru import logger
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.adapters.llm.prompts import (
    build_system_prompt,
    build_system_prompt_retry,
    build_user_prompt,
)
from app.domain.errors import LLMError
from app.infrastructure.llm_cost_tracker import CostTimer, get_tracker

# ---------------------------------------------------------------------------
# Exceções internas para retry
# ---------------------------------------------------------------------------


class _RetryableHTTPError(Exception):
    """Erro HTTP retryável (429 / 5xx / timeout)."""


class CircuitOpenError(LLMError):
    """Circuit breaker aberto — chamadas LLM temporariamente bloqueadas."""

    def __init__(self, consecutive_failures: int) -> None:
        super().__init__(
            f"Circuit breaker aberto após {consecutive_failures} falhas consecutivas."
        )
        self.consecutive_failures = consecutive_failures


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_CHAT_COMPLETIONS_PATH: str = "/chat/completions"

# Chaves obrigatórias no JSON retornado pelo LLM.
# "materiais" é opcional (depende do perfil).
_REQUIRED_KEYS: set[str] = {"introducao", "metodologia", "conclusao"}

# Mascarar chave nos logs: exibir apenas últimos 4 caracteres
_KEY_MASK_LEN: int = 4


def _mask_key(key: str) -> str:
    """Retorna versão mascarada da API key para logging seguro."""
    if len(key) <= _KEY_MASK_LEN:
        return "****"
    return f"****{key[-_KEY_MASK_LEN:]}"


# ---------------------------------------------------------------------------
# OpenRouterClient
# ---------------------------------------------------------------------------


class OpenRouterClient:
    """Adaptador LLM via OpenRouter — implementa ``LLMPort``.

    Attributes:
        api_key: Chave de API do OpenRouter.
        base_url: URL base da API (padrão: ``https://openrouter.ai/api/v1``).
        model: Identificador do modelo (ex.: ``openai/gpt-4o``).
        timeout: Timeout HTTP em segundos.
        max_retries: Máximo de tentativas para erros retryáveis.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "openai/gpt-4o",
        timeout: float = 120.0,
        max_retries: int = 3,
        temperature: float = 0.15,
        top_p: float = 0.85,
    ) -> None:
        if not api_key:
            raise LLMError("OPENROUTER_API_KEY não configurada.")

        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._max_retries = max_retries
        self._temperature = temperature
        self._top_p = top_p
        self._tracker = get_tracker()

        # Contexto de tracking (setado externamente por quem chama)
        self._tracking_context: dict[str, str] = {}

        # Circuit breaker state
        self._consecutive_failures: int = 0
        self._circuit_breaker_threshold: int = 5  # abre após N falhas seguidas

        logger.info(
            "OpenRouterClient inicializado | model={} | base_url={} | key={}",
            self._model,
            self._base_url,
            _mask_key(self._api_key),
        )

    def set_tracking_context(
        self,
        *,
        flow: str = "",
        step: str = "",
        job_id: str = "",
        equipment_name: str = "",
    ) -> None:
        """Define o contexto de tracking para as próximas chamadas.

        Deve ser chamado antes de ``generate_sections`` ou ``call_chat``
        para associar a chamada ao fluxo/job correto.

        Args:
            flow: Nome do fluxo (e.g. ``process_job``).
            step: Etapa do fluxo (e.g. ``global_sections``).
            job_id: ID do job.
            equipment_name: Nome do equipamento.
        """
        self._tracking_context = {
            "flow": flow,
            "step": step,
            "job_id": job_id,
            "equipment_name": equipment_name,
        }

    # ------------------------------------------------------------------
    # Método público — porta LLMPort
    # ------------------------------------------------------------------

    async def generate_sections(
        self,
        context: dict[str, Any],
        *,
        model_override: str | None = None,
    ) -> dict[str, Any]:
        """Gera seções narrativas do laudo a partir do contexto.

        Fluxo:
        1. Monta prompts (system + user) via ``prompts.py``, usando o perfil.
        2. Chama OpenRouter ``/chat/completions`` com retry.
        3. Tenta parsear JSON da resposta.
        4. Se JSON inválido, faz 1 retry com system prompt reforçado.

        Args:
            context: Dicionário com ``company``, ``rows``, ``profile``,
                     ``grouped_equipment``, etc.
            model_override: Modelo específico para esta chamada (CP-01).
                Se ``None``, usa o modelo padrão do client.

        Returns:
            Dicionário com chaves ``introducao``, ``metodologia``, ``conclusao``
            e opcionalmente ``materiais``.

        Raises:
            LLMError: Se a chamada falhar após retries ou se o JSON for inválido
                      mesmo após retry de formato.
        """
        profile = context.get("profile")
        user_prompt = build_user_prompt(context)
        system_prompt = build_system_prompt(profile)

        effective_model = model_override or self._model
        logger.info(
            "Gerando seções do laudo | model={} | profile={} | linhas_de_risco={}",
            effective_model,
            profile or "default",
            len(context.get("rows", [])),
        )

        # --- Primeira tentativa ---
        raw_content = await self._call_chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_override=model_override,
        )

        parsed = self._try_parse_json(raw_content)
        if parsed is not None:
            return parsed

        # --- Retry de formato (JSON inválido na 1ª resposta) ---
        logger.warning(
            "Resposta do LLM não é JSON válido. Reenviando com prompt reforçado."
        )

        retry_system = build_system_prompt_retry(profile)
        raw_content_retry = await self._call_chat(
            system_prompt=retry_system,
            user_prompt=user_prompt,
            model_override=model_override,
        )

        parsed_retry = self._try_parse_json(raw_content_retry)
        if parsed_retry is not None:
            return parsed_retry

        raise LLMError(
            "Resposta do LLM não é JSON válido após retry de formato.",
            detail=raw_content_retry[:500],
        )

    async def call_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model_override: str | None = None,
    ) -> str:
        """Chamada pública ao LLM — interface para uso per-equipment.

        Expõe ``_call_chat`` com assinatura compatível com
        ``LLMCallFn = Callable[[str, str], Awaitable[str]]``.

        Args:
            system_prompt: Prompt de sistema.
            user_prompt: Prompt do usuário.
            model_override: Modelo específico a usar nesta chamada.
                Se ``None``, usa o modelo padrão do client (``self._model``).

        Returns:
            Conteúdo textual cru da resposta do LLM.

        Raises:
            LLMError: Em caso de falha HTTP / timeout.
        """
        return await self._call_chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_override=model_override,
        )

    # ------------------------------------------------------------------
    # Chamada HTTP com retry (tenacity)
    # ------------------------------------------------------------------

    async def _call_chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model_override: str | None = None,
    ) -> str:
        """Executa chamada POST ao endpoint de chat completions.

        Args:
            system_prompt: Prompt de sistema.
            user_prompt: Prompt do usuário.
            model_override: Modelo específico para esta chamada.
                Se ``None``, usa ``self._model``.

        Retorna o conteúdo textual da primeira ``choice``.

        Raises:
            LLMError: Após esgotar retries ou em caso de erro inesperado.
        """
        effective_model = model_override or self._model

        @retry(
            retry=retry_if_exception_type(_RetryableHTTPError),
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            reraise=True,
        )
        async def _do_request() -> str:
            url = f"{self._base_url}{_CHAT_COMPLETIONS_PATH}"
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }
            payload: dict[str, Any] = {
                "model": effective_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": self._temperature,
                "top_p": self._top_p,
                "response_format": {"type": "json_object"},
            }

            logger.debug(
                "POST {} | model={} | prompt_len={}",
                url,
                effective_model,
                len(user_prompt),
            )

            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, headers=headers, json=payload)

            status = response.status_code

            # Retryáveis: 429 (rate limit) e 5xx (erro de servidor)
            if status == 429 or status >= 500:
                body_preview = response.text[:300]
                logger.warning(
                    "OpenRouter retornou status {} — será retentado | body={}",
                    status,
                    body_preview,
                )
                raise _RetryableHTTPError(
                    f"HTTP {status}: {body_preview}"
                )

            # Erros não retryáveis (4xx exceto 429)
            if status >= 400:
                body_preview = response.text[:500]
                logger.error(
                    "OpenRouter erro não retryável | status={} | body={}",
                    status,
                    body_preview,
                )
                raise LLMError(
                    f"OpenRouter retornou HTTP {status}.",
                    detail=body_preview,
                )

            # Sucesso — extrair conteúdo
            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                raise LLMError(
                    "Resposta do OpenRouter sem choices.",
                    detail=str(data)[:500],
                )

            content: str = choices[0].get("message", {}).get("content", "")
            if not content.strip():
                raise LLMError(
                    "Resposta do OpenRouter com content vazio.",
                    detail=str(data)[:500],
                )

            # ── Capturar usage da API para tracking de custo ────
            api_usage = data.get("usage")

            logger.debug(
                "Resposta recebida | status={} | content_len={}",
                status,
                len(content),
            )
            return content, api_usage

        ctx = self._tracking_context
        timer = CostTimer()

        # ── Circuit breaker check ──
        if self._consecutive_failures >= self._circuit_breaker_threshold:
            logger.error(
                "CIRCUIT_BREAKER | OPEN | {} falhas consecutivas — bloqueando chamada",
                self._consecutive_failures,
            )
            raise CircuitOpenError(self._consecutive_failures)

        try:
            with timer:
                result_tuple = await _do_request()
            content_result, api_usage = result_tuple

            # ── Reset circuit breaker on success ──
            self._consecutive_failures = 0

            # ── Registrar uso com sucesso ─────────────────────
            self._tracker.record_generation(
                flow=ctx.get("flow", "unknown"),
                step=ctx.get("step", "unknown"),
                provider="openrouter",
                model=effective_model,
                prompt_text=system_prompt + user_prompt,
                response_text=content_result,
                duration_ms=timer.duration_ms,
                success=True,
                job_id=ctx.get("job_id", ""),
                equipment_name=ctx.get("equipment_name", ""),
                api_usage=api_usage,
                tokens_source="api" if api_usage else "estimate",
            )
            return content_result

        except _RetryableHTTPError as exc:
            self._consecutive_failures += 1
            self._tracker.record_generation(
                flow=ctx.get("flow", "unknown"),
                step=ctx.get("step", "unknown"),
                provider="openrouter",
                model=effective_model,
                prompt_text=system_prompt + user_prompt,
                duration_ms=timer.duration_ms,
                success=False,
                error_message=str(exc),
                job_id=ctx.get("job_id", ""),
                equipment_name=ctx.get("equipment_name", ""),
            )
            raise LLMError(
                "OpenRouter indisponível após retries.",
                detail=str(exc),
            ) from exc
        except RetryError as exc:
            self._consecutive_failures += 1
            self._tracker.record_generation(
                flow=ctx.get("flow", "unknown"),
                step=ctx.get("step", "unknown"),
                provider="openrouter",
                model=effective_model,
                prompt_text=system_prompt + user_prompt,
                duration_ms=timer.duration_ms,
                success=False,
                error_message=str(exc),
                job_id=ctx.get("job_id", ""),
                equipment_name=ctx.get("equipment_name", ""),
            )
            raise LLMError(
                "OpenRouter indisponível após retries.",
                detail=str(exc),
            ) from exc
        except httpx.TimeoutException as exc:
            self._consecutive_failures += 1
            self._tracker.record_generation(
                flow=ctx.get("flow", "unknown"),
                step=ctx.get("step", "unknown"),
                provider="openrouter",
                model=effective_model,
                prompt_text=system_prompt + user_prompt,
                duration_ms=timer.duration_ms,
                success=False,
                error_message=str(exc),
                job_id=ctx.get("job_id", ""),
                equipment_name=ctx.get("equipment_name", ""),
            )
            raise LLMError(
                f"Timeout ao chamar OpenRouter ({self._timeout}s).",
                detail=str(exc),
            ) from exc
        except httpx.HTTPError as exc:
            self._consecutive_failures += 1
            self._tracker.record_generation(
                flow=ctx.get("flow", "unknown"),
                step=ctx.get("step", "unknown"),
                provider="openrouter",
                model=effective_model,
                prompt_text=system_prompt + user_prompt,
                duration_ms=timer.duration_ms,
                success=False,
                error_message=str(exc),
                job_id=ctx.get("job_id", ""),
                equipment_name=ctx.get("equipment_name", ""),
            )
            raise LLMError(
                "Erro de rede ao chamar OpenRouter.",
                detail=str(exc),
            ) from exc

    # ------------------------------------------------------------------
    # Parsing e validação de JSON
    # ------------------------------------------------------------------

    @staticmethod
    def _try_parse_json(raw: str) -> dict[str, Any] | None:
        """Tenta parsear a string como JSON e validar as chaves esperadas.

        Lida com respostas que contenham blocos de código markdown
        (ex.: ```json ... ```).

        Args:
            raw: Conteúdo textual retornado pelo modelo.

        Returns:
            Dicionário validado ou ``None`` se falhar.
        """
        from app.domain.services.json_utils import parse_llm_json

        data = parse_llm_json(raw)
        if data is None:
            return None

        missing = _REQUIRED_KEYS - set(data.keys())
        if missing:
            logger.warning(
                "Resposta LLM com chaves faltantes: {}",
                missing,
            )
            return None

        return data
