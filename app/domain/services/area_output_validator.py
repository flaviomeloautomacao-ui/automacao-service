"""Validador de saída LLM — Classificação de Áreas.

Valida o JSON retornado pelo LLM nas duas modalidades:
  • Global: {introducao, escopo, consideracoes_gerais, metodologia,
             recomendacoes, conclusao}
  • Per-área: {justificativa_zona, analise_ventilacao,
               recomendacoes_especificas[]}

Também provê fallbacks determinísticos quando o LLM falha.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.domain.entities.area_classification import AreaClassificationContext


# ---------------------------------------------------------------------------
# Modelos de saída
# ---------------------------------------------------------------------------

class AreaGlobalOutput(BaseModel):
    """Seções narrativas globais do relatório."""
    introducao: str = Field(default="", min_length=0)
    escopo: str = Field(default="", min_length=0)
    consideracoes_gerais: str = Field(default="", min_length=0)
    metodologia: str = Field(default="", min_length=0)
    recomendacoes: str = Field(default="", min_length=0)
    conclusao: str = Field(default="", min_length=0)


class AreaRecomendacaoEspecifica(BaseModel):
    numero: int = Field(default=1, ge=1)
    texto: str = Field(default="")
    norma_referencia: str = Field(default="")


class AreaPerAreaOutput(BaseModel):
    """Análise técnica por equipamento/área."""
    justificativa_zona: str = Field(default="")
    analise_ventilacao: str = Field(default="")
    recomendacoes_especificas: list[AreaRecomendacaoEspecifica] = Field(
        default_factory=list,
    )


class AreaValidationResult:
    """Resultado da validação de uma resposta LLM."""

    __slots__ = ("success", "output", "reason", "needs_retry")

    def __init__(
        self,
        success: bool,
        output: BaseModel | None,
        reason: str = "",
        needs_retry: bool = False,
    ) -> None:
        self.success = success
        self.output = output
        self.reason = reason
        self.needs_retry = needs_retry


# ---------------------------------------------------------------------------
# Extração robusta de JSON
# ---------------------------------------------------------------------------

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(raw: str) -> dict[str, Any] | None:
    """Extrai o primeiro objeto JSON de um texto bruto do LLM."""
    if not raw:
        return None
    s = raw.strip()
    # Remove cercas markdown
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*```\s*$", "", s)
    # Tenta parse direto
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # Tenta extrair maior bloco { ... }
    m = _JSON_RE.search(s)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


# ---------------------------------------------------------------------------
# Validação — Global
# ---------------------------------------------------------------------------

def validate_global_output(raw: str) -> AreaValidationResult:
    """Valida JSON da chamada global do LLM."""
    parsed = _extract_json(raw)
    if parsed is None:
        return AreaValidationResult(
            success=False, output=None,
            reason="JSON inválido ou ausente", needs_retry=True,
        )
    try:
        out = AreaGlobalOutput(**parsed)
    except ValidationError as e:
        return AreaValidationResult(
            success=False, output=None,
            reason=f"Schema global inválido: {e}", needs_retry=True,
        )
    return AreaValidationResult(success=True, output=out)


def build_global_fallback() -> AreaGlobalOutput:
    """Fallback determinístico para seções globais."""
    return AreaGlobalOutput(
        introducao=(
            "Este relatório apresenta o estudo de classificação de áreas com "
            "atmosferas explosivas executado na unidade objeto da avaliação, "
            "em conformidade com as normas ABNT NBR IEC 60079-10-1 e "
            "ABNT NBR IEC 60079-10-2. O estudo tem por finalidade subsidiar "
            "a seleção e instalação de equipamentos elétricos adequados, "
            "bem como a definição de procedimentos operacionais que mitiguem "
            "o risco de incêndio e explosão."
        ),
        escopo=(
            "O escopo do estudo abrange a identificação das fontes de "
            "liberação de substâncias inflamáveis ou poeiras combustíveis, "
            "a classificação das zonas resultantes (Zonas 0, 1 e 2 para "
            "gases/vapores; Zonas 20, 21 e 22 para poeiras) e a determinação "
            "das respectivas extensões."
        ),
        consideracoes_gerais=(
            "As condições operacionais, características das substâncias "
            "presentes e premissas de ventilação adotadas estão consolidadas "
            "na tabela de classificação. Quaisquer alterações nestes parâmetros "
            "implicam em reavaliação do estudo."
        ),
        metodologia=(
            "A metodologia adotada segue as diretrizes da ABNT NBR IEC "
            "60079-10-1 e 60079-10-2, contemplando: (1) caracterização das "
            "substâncias e propriedades de inflamabilidade; (2) identificação "
            "de fontes de emissão; (3) avaliação do grau e disponibilidade "
            "da ventilação; (4) determinação do grau das fontes de liberação; "
            "(5) classificação das zonas; (6) determinação das extensões."
        ),
        recomendacoes=(
            "• Selecionar equipamentos elétricos certificados Ex conforme a "
            "zona, grupo IEC e classe de temperatura aplicáveis (IEC 60079-14).\n"
            "• Manter a continuidade da ventilação considerada no estudo.\n"
            "• Implementar inspeções periódicas conforme IEC 60079-17.\n"
            "• Treinar a equipe operacional conforme NR-20."
        ),
        conclusao=(
            "O presente estudo constitui referência técnica para a gestão "
            "do risco de explosão na unidade. As classificações apresentadas "
            "permanecem válidas enquanto as premissas operacionais e de "
            "ventilação forem mantidas."
        ),
    )


# ---------------------------------------------------------------------------
# Validação — Per-Área
# ---------------------------------------------------------------------------

def validate_per_area_output(raw: str) -> AreaValidationResult:
    """Valida JSON da chamada per-área do LLM."""
    parsed = _extract_json(raw)
    if parsed is None:
        return AreaValidationResult(
            success=False, output=None,
            reason="JSON inválido ou ausente", needs_retry=True,
        )
    try:
        out = AreaPerAreaOutput(**parsed)
    except ValidationError as e:
        return AreaValidationResult(
            success=False, output=None,
            reason=f"Schema per-área inválido: {e}", needs_retry=True,
        )
    return AreaValidationResult(success=True, output=out)


def build_per_area_fallback(ctx: AreaClassificationContext) -> AreaPerAreaOutput:
    """Fallback determinístico para análise per-área."""
    grp = (ctx.grupo or "").upper()
    norma_principal = (
        "ABNT NBR IEC 60079-10-2" if grp.startswith("III") else "ABNT NBR IEC 60079-10-1"
    )
    fontes_descr = ", ".join(
        f"{f.descricao} ({f.grau})" for f in ctx.fontes_liberacao
    ) or "as fontes registradas"

    return AreaPerAreaOutput(
        justificativa_zona=(
            f"As classificações de zona apresentadas para o equipamento "
            f"{ctx.identificacao} decorrem da análise das fontes de "
            f"liberação identificadas — {fontes_descr} — em conformidade com "
            f"{norma_principal}. Fontes de grau Contínuo originam Zonas 0/20; "
            f"de grau Primário, Zonas 1/21; e de grau Secundário, Zonas 2/22."
        ),
        analise_ventilacao=(
            "O grau e a disponibilidade da ventilação considerados nesta "
            "classificação influenciam diretamente a extensão e o tipo das "
            "zonas resultantes. A manutenção das condições de ventilação "
            "adotadas é premissa essencial para a validade do estudo."
        ),
        recomendacoes_especificas=[
            AreaRecomendacaoEspecifica(
                numero=1,
                texto=(
                    "Equipamentos elétricos instalados nas zonas classificadas "
                    "devem possuir certificação Ex compatível com o grupo IEC "
                    f"({ctx.grupo or 'aplicável'}) e classe de temperatura "
                    f"({ctx.classe_temperatura or 'aplicável'})."
                ),
                norma_referencia="ABNT NBR IEC 60079-14",
            ),
            AreaRecomendacaoEspecifica(
                numero=2,
                texto=(
                    "Implementar inspeção periódica das condições de "
                    "estanqueidade das fontes de liberação identificadas."
                ),
                norma_referencia="ABNT NBR IEC 60079-17",
            ),
        ],
    )


__all__ = [
    "AreaGlobalOutput",
    "AreaPerAreaOutput",
    "AreaRecomendacaoEspecifica",
    "AreaValidationResult",
    "validate_global_output",
    "validate_per_area_output",
    "build_global_fallback",
    "build_per_area_fallback",
]
