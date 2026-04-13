"""Roteador de modelos LLM — seleciona o modelo ideal por contexto.

Implementa o roteamento tiered (por nível de risco) conforme o plano
de otimização de custos LLM. Quando habilitado, equipamentos de alto
risco usam um modelo mais capaz (GPT-4.1), enquanto os demais usam
um modelo mais econômico (GPT-4.1-mini).

Uso::

    from app.infrastructure.model_router import ModelRouter, get_model_router

    router = get_model_router()

    # Para seções globais (CP-01)
    model = router.resolve_global()

    # Para equipamentos (CP-02) — roteamento baseado em risco
    model = router.resolve_equipment(risk_classification)

    # Modelo de fallback
    model = router.resolve_fallback(failed_model)

Configuração via variáveis de ambiente / .env::

    LLM_MODEL_GLOBAL=openai/gpt-4.1-mini
    LLM_MODEL_PER_EQUIPMENT=openai/gpt-4.1-mini
    LLM_MODEL_PER_EQUIPMENT_HIGH=openai/gpt-4.1
    LLM_MODEL_FALLBACK=openai/gpt-4.1-mini
    LLM_HIGH_RISK_KEYWORDS=muito alto,intolerável,substancial
    LLM_TIERED_ROUTING_ENABLED=true
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from loguru import logger

from app.domain.entities import RiskClassification


# ---------------------------------------------------------------------------
# Tipos de call point
# ---------------------------------------------------------------------------

class CallPoint:
    """Identificadores dos pontos de chamada LLM no pipeline."""

    GLOBAL_SECTIONS = "global_sections"       # CP-01: introdução, metodologia, conclusão
    PER_EQUIPMENT = "per_equipment_narrative"  # CP-02: narrativas por equipamento


# ---------------------------------------------------------------------------
# Resultado do roteamento
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RoutingDecision:
    """Resultado de uma decisão de roteamento.

    Attributes:
        model: Identificador do modelo selecionado.
        call_point: Ponto de chamada (CP-01, CP-02).
        reason: Justificativa legível da escolha.
        is_high_risk: Se o equipamento foi classificado como alto risco.
    """

    model: str
    call_point: str
    reason: str
    is_high_risk: bool = False


# ---------------------------------------------------------------------------
# ModelRouter
# ---------------------------------------------------------------------------


class ModelRouter:
    """Seleciona o modelo LLM adequado para cada ponto de chamada.

    Quando ``tiered_enabled=False``, retorna o ``default_model`` para
    todas as chamadas (comportamento legado).

    Quando ``tiered_enabled=True``, usa modelos diferenciados:
    - CP-01 (global): ``model_global``
    - CP-02 risco alto: ``model_per_equipment_high``
    - CP-02 risco normal: ``model_per_equipment``
    - Fallback: ``model_fallback``

    Args:
        default_model: Modelo padrão (usado quando tiered está off).
        model_global: Modelo para seções globais (CP-01).
        model_per_equipment: Modelo para equipamentos risco médio/baixo.
        model_per_equipment_high: Modelo para equipamentos risco alto.
        model_fallback: Modelo de fallback quando o primário falha.
        high_risk_keywords: Palavras-chave que indicam risco alto.
        tiered_enabled: Habilita roteamento por risco.
    """

    def __init__(
        self,
        *,
        default_model: str = "openai/gpt-4.1-mini",
        model_global: str = "openai/gpt-4.1-mini",
        model_per_equipment: str = "openai/gpt-4.1-mini",
        model_per_equipment_high: str = "openai/gpt-4.1",
        model_fallback: str = "openai/gpt-4.1-mini",
        high_risk_keywords: list[str] | None = None,
        tiered_enabled: bool = True,
    ) -> None:
        self._default_model = default_model
        self._model_global = model_global
        self._model_per_equipment = model_per_equipment
        self._model_per_equipment_high = model_per_equipment_high
        self._model_fallback = model_fallback
        self._tiered_enabled = tiered_enabled

        # Normaliza keywords para lowercase para comparação
        if high_risk_keywords is None:
            high_risk_keywords = ["muito alto", "intolerável", "substancial"]
        self._high_risk_keywords: list[str] = [
            kw.strip().lower() for kw in high_risk_keywords if kw.strip()
        ]

        logger.info(
            "ModelRouter inicializado | tiered={} | global={} | equip={} | "
            "equip_high={} | fallback={} | risk_keywords={}",
            self._tiered_enabled,
            self._model_global,
            self._model_per_equipment,
            self._model_per_equipment_high,
            self._model_fallback,
            self._high_risk_keywords,
        )

    # ------------------------------------------------------------------
    # Propriedades
    # ------------------------------------------------------------------

    @property
    def tiered_enabled(self) -> bool:
        """Se o roteamento tiered está habilitado."""
        return self._tiered_enabled

    @property
    def default_model(self) -> str:
        """Modelo padrão (quando tiered está off)."""
        return self._default_model

    # ------------------------------------------------------------------
    # Resolução de modelo
    # ------------------------------------------------------------------

    def resolve_global(self) -> RoutingDecision:
        """Seleciona modelo para seções globais (CP-01).

        Returns:
            RoutingDecision com o modelo escolhido.
        """
        if not self._tiered_enabled:
            return RoutingDecision(
                model=self._default_model,
                call_point=CallPoint.GLOBAL_SECTIONS,
                reason="Roteamento tiered desabilitado — usando modelo padrão",
            )

        return RoutingDecision(
            model=self._model_global,
            call_point=CallPoint.GLOBAL_SECTIONS,
            reason=f"CP-01 global sections → {self._model_global}",
        )

    def resolve_equipment(
        self,
        risk_classification: RiskClassification | None = None,
    ) -> RoutingDecision:
        """Seleciona modelo para narrativa per-equipment (CP-02).

        Equipamentos com ``classificacao_risco`` contendo keywords de
        alto risco usam o modelo premium. Os demais usam o modelo econômico.

        Args:
            risk_classification: Classificação de risco do equipamento.

        Returns:
            RoutingDecision com o modelo escolhido.
        """
        if not self._tiered_enabled:
            return RoutingDecision(
                model=self._default_model,
                call_point=CallPoint.PER_EQUIPMENT,
                reason="Roteamento tiered desabilitado — usando modelo padrão",
            )

        is_high = self._is_high_risk(risk_classification)

        if is_high:
            return RoutingDecision(
                model=self._model_per_equipment_high,
                call_point=CallPoint.PER_EQUIPMENT,
                reason=(
                    f"Risco alto detectado "
                    f"({risk_classification.classificacao_risco if risk_classification else '?'}) "
                    f"→ {self._model_per_equipment_high}"
                ),
                is_high_risk=True,
            )

        return RoutingDecision(
            model=self._model_per_equipment,
            call_point=CallPoint.PER_EQUIPMENT,
            reason=(
                f"Risco normal "
                f"({risk_classification.classificacao_risco if risk_classification else 'N/A'}) "
                f"→ {self._model_per_equipment}"
            ),
        )

    def resolve_fallback(self, failed_model: str) -> RoutingDecision:
        """Retorna modelo de fallback quando o primário falha.

        Args:
            failed_model: O modelo que falhou.

        Returns:
            RoutingDecision com o modelo de fallback.
        """
        # Se o fallback é o mesmo que falhou, sem alternativa
        if self._model_fallback == failed_model:
            logger.warning(
                "Modelo fallback ({}) é o mesmo que falhou — sem alternativa",
                failed_model,
            )

        return RoutingDecision(
            model=self._model_fallback,
            call_point="fallback",
            reason=f"Fallback após falha de {failed_model} → {self._model_fallback}",
        )

    # ------------------------------------------------------------------
    # Classificação de risco
    # ------------------------------------------------------------------

    def _is_high_risk(
        self,
        risk_classification: RiskClassification | None,
    ) -> bool:
        """Verifica se a classificação de risco é considerada 'alta'.

        Compara ``classificacao_risco`` e ``categoria_severidade``
        contra as keywords configuradas.

        Args:
            risk_classification: Classificação consolidada do equipamento.

        Returns:
            True se o equipamento é de alto risco.
        """
        if risk_classification is None:
            return False

        # Campos a verificar (lowercase)
        fields_to_check: list[str] = []

        risco = (risk_classification.classificacao_risco or "").strip().lower()
        if risco:
            fields_to_check.append(risco)

        severidade = (risk_classification.categoria_severidade or "").strip().lower()
        if severidade:
            fields_to_check.append(severidade)

        for field_val in fields_to_check:
            for keyword in self._high_risk_keywords:
                if keyword in field_val:
                    return True

        return False

    # ------------------------------------------------------------------
    # Métricas
    # ------------------------------------------------------------------

    def get_config_summary(self) -> dict[str, str | bool | list[str]]:
        """Retorna resumo da configuração para logging/debug."""
        return {
            "tiered_enabled": self._tiered_enabled,
            "default_model": self._default_model,
            "model_global": self._model_global,
            "model_per_equipment": self._model_per_equipment,
            "model_per_equipment_high": self._model_per_equipment_high,
            "model_fallback": self._model_fallback,
            "high_risk_keywords": self._high_risk_keywords,
        }


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_model_router() -> ModelRouter:
    """Cria e retorna o ModelRouter singleton baseado nas settings.

    Returns:
        Instância configurada de ModelRouter.
    """
    from app.infrastructure.config import get_settings  # noqa: PLC0415

    settings = get_settings()

    # Parse keywords (comma-separated string → list)
    keywords = [
        kw.strip()
        for kw in settings.LLM_HIGH_RISK_KEYWORDS.split(",")
        if kw.strip()
    ]

    return ModelRouter(
        default_model=settings.LLM_MODEL,
        model_global=settings.LLM_MODEL_GLOBAL,
        model_per_equipment=settings.LLM_MODEL_PER_EQUIPMENT,
        model_per_equipment_high=settings.LLM_MODEL_PER_EQUIPMENT_HIGH,
        model_fallback=settings.LLM_MODEL_FALLBACK,
        high_risk_keywords=keywords,
        tiered_enabled=settings.LLM_TIERED_ROUTING_ENABLED,
    )
