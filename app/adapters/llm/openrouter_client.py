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
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_RETRY,
    build_user_prompt,
)
from app.domain.errors import LLMError

# ---------------------------------------------------------------------------
# Exceções internas para retry
# ---------------------------------------------------------------------------


class _RetryableHTTPError(Exception):
    """Erro HTTP retryável (429 / 5xx / timeout)."""


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_CHAT_COMPLETIONS_PATH: str = "/chat/completions"

_REQUIRED_KEYS: set[str] = {"sumario", "recomendacoes", "justificativas"}

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
    ) -> None:
        if not api_key:
            raise LLMError("OPENROUTER_API_KEY não configurada.")

        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._max_retries = max_retries

        logger.info(
            "OpenRouterClient inicializado | model={} | base_url={} | key={}",
            self._model,
            self._base_url,
            _mask_key(self._api_key),
        )

    # ------------------------------------------------------------------
    # Método público — porta LLMPort
    # ------------------------------------------------------------------

    async def generate_sections(self, context: dict[str, Any]) -> dict[str, Any]:
        """Gera seções narrativas do laudo a partir do contexto.

        Fluxo:
        1. Monta prompts (system + user) via ``prompts.py``.
        2. Chama OpenRouter ``/chat/completions`` com retry.
        3. Tenta parsear JSON da resposta.
        4. Se JSON inválido, faz 1 retry com system prompt reforçado.

        Args:
            context: Dicionário com ``company``, ``rows``, ``normas``, etc.

        Returns:
            Dicionário com chaves ``sumario``, ``recomendacoes``, ``justificativas``.

        Raises:
            LLMError: Se a chamada falhar após retries ou se o JSON for inválido
                      mesmo após retry de formato.
        """
        user_prompt = build_user_prompt(context)

        logger.info(
            "Gerando seções do laudo | model={} | linhas_de_risco={}",
            self._model,
            len(context.get("rows", [])),
        )

        # --- Primeira tentativa ---
        raw_content = await self._call_chat(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        parsed = self._try_parse_json(raw_content)
        if parsed is not None:
            return parsed

        # --- Retry de formato (JSON inválido na 1ª resposta) ---
        logger.warning(
            "Resposta do LLM não é JSON válido. Reenviando com prompt reforçado."
        )

        raw_content_retry = await self._call_chat(
            system_prompt=SYSTEM_PROMPT_RETRY,
            user_prompt=user_prompt,
        )

        parsed_retry = self._try_parse_json(raw_content_retry)
        if parsed_retry is not None:
            return parsed_retry

        raise LLMError(
            "Resposta do LLM não é JSON válido após retry de formato.",
            detail=raw_content_retry[:500],
        )

    # ------------------------------------------------------------------
    # Chamada HTTP com retry (tenacity)
    # ------------------------------------------------------------------

    async def _call_chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """Executa chamada POST ao endpoint de chat completions.

        Retorna o conteúdo textual da primeira ``choice``.

        Raises:
            LLMError: Após esgotar retries ou em caso de erro inesperado.
        """

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
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
            }

            logger.debug(
                "POST {} | model={} | prompt_len={}",
                url,
                self._model,
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

            logger.debug(
                "Resposta recebida | status={} | content_len={}",
                status,
                len(content),
            )
            return content

        try:
            return await _do_request()
        except _RetryableHTTPError as exc:
            raise LLMError(
                "OpenRouter indisponível após retries.",
                detail=str(exc),
            ) from exc
        except RetryError as exc:
            raise LLMError(
                "OpenRouter indisponível após retries.",
                detail=str(exc),
            ) from exc
        except httpx.TimeoutException as exc:
            raise LLMError(
                f"Timeout ao chamar OpenRouter ({self._timeout}s).",
                detail=str(exc),
            ) from exc
        except httpx.HTTPError as exc:
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
        cleaned = raw.strip()

        # Remover blocos ``` caso o modelo envolva em markdown
        if cleaned.startswith("```"):
            # remover primeira e última linha de ```
            lines = cleaned.split("\n")
            # Encontrar primeira e última ocorrência de ```
            start = 1 if lines[0].startswith("```") else 0
            end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
            cleaned = "\n".join(lines[start:end]).strip()

        try:
            data = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Falha ao parsear JSON da resposta LLM.")
            return None

        if not isinstance(data, dict):
            logger.warning("Resposta LLM não é um objeto JSON (dict).")
            return None

        missing = _REQUIRED_KEYS - set(data.keys())
        if missing:
            logger.warning(
                "Resposta LLM com chaves faltantes: {}",
                missing,
            )
            return None

        return data
