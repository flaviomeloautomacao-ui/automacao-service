"""Client LLM mock para desenvolvimento e testes sem custo.

Retorna respostas determinísticas sem fazer chamadas reais à API.
Usado quando ``LLM_MOCK_ENABLED=true``.

Custo: $0.00 | Latência: ~1ms

Uso::

    from app.adapters.llm.mock_client import MockLLMClient

    client = MockLLMClient()
    result = await client.generate_sections(context)
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from loguru import logger


class MockLLMClient:
    """Client LLM que retorna respostas determinísticas sem API call.

    Compatível com a interface ``LLMPort`` / ``OpenRouterClient``.
    """

    def __init__(self) -> None:
        logger.warning("MockLLMClient ativo — respostas NÃO são reais")
        self._tracking_context: dict[str, str] = {}

    def set_tracking_context(self, **kwargs: str) -> None:
        """Define contexto de tracking (no-op funcional — armazena para logging)."""
        self._tracking_context.update(kwargs)

    async def call_chat(self, system: str, user: str) -> str:
        """Retorna resposta mock baseada no tipo de prompt detectado.

        Args:
            system: System prompt.
            user: User prompt.

        Returns:
            JSON string com resposta mock.
        """
        await asyncio.sleep(0.01)  # simula latência mínima

        if "seções globais" in system.lower() or "introdução" in system.lower():
            return json.dumps(
                {
                    "introducao": "<p>[MOCK] Introdução do laudo técnico.</p>",
                    "objetivo": "<p>[MOCK] Objetivo da análise de risco.</p>",
                    "metodologia": "<p>[MOCK] Metodologia aplicada conforme normas vigentes.</p>",
                    "conclusao": "<p>[MOCK] Conclusão do laudo com recomendações gerais.</p>",
                    "materiais_utilizados": "<p>[MOCK] Materiais e equipamentos utilizados na avaliação.</p>",
                },
                ensure_ascii=False,
            )
        else:
            return json.dumps(
                {
                    "recomendacoes": (
                        "<p>[MOCK] Recomendações técnicas para o equipamento avaliado, "
                        "incluindo medidas de proteção coletiva e individual conforme NR-12.</p>"
                    ),
                    "justificativas": (
                        "<p>[MOCK] Justificativas normativas baseadas em NR-12, ISO 12100 "
                        "e demais normas aplicáveis ao perfil de risco identificado.</p>"
                    ),
                },
                ensure_ascii=False,
            )

    async def generate_sections(self, context: dict[str, Any]) -> dict[str, str]:
        """Retorna seções mock para compatibilidade com ProcessUploadUseCase.

        Args:
            context: Contexto de geração (ignorado no mock).

        Returns:
            Dict com seções do laudo.
        """
        return {
            "introducao": "<p>[MOCK] Introdução.</p>",
            "objetivo": "<p>[MOCK] Objetivo.</p>",
            "metodologia": "<p>[MOCK] Metodologia.</p>",
            "conclusao": "<p>[MOCK] Conclusão.</p>",
            "materiais_utilizados": "<p>[MOCK] Materiais.</p>",
        }
