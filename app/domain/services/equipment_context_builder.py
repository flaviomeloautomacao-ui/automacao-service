"""Serviço de domínio — constrói contextos estruturados por equipamento.

Agrupa linhas da planilha (``MachineRiskRow``) por nome de equipamento e
produz uma coleção normalizada de ``EquipmentContext``, cada qual contendo
**exclusivamente** os dados de um único equipamento.

Este módulo substitui a função ``group_rows_by_equipment`` como fonte
primária de dados para o pipeline LLM per-equipment. A função legada
continua disponível em ``process_upload.py`` para compatibilidade com
o template Jinja2.

Contrato de referência: ``docs/equipment_llm_contract.md``, §2.

──────────────────────────────────────────────────────────────────────
 REGRAS DE AGRUPAMENTO
──────────────────────────────────────────────────────────────────────

 1. Chave de agrupamento = ``equipamento`` (case-insensitive, trimmed).
 2. Ordem de saída = ordem de primeira aparição na planilha.
 3. Campos de lista (perigos, causas, …) são deduplicated, preservando
    a ordem de inserção.
 4. Severidade e risco são consolidados para o **valor mais alto**
    entre todas as linhas do equipamento (não o primeiro encontrado).
 5. Descrição da operação = o valor mais longo entre as linhas.
 6. Cada string individual é trimmed; strings vazias são descartadas.
──────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any

from loguru import logger

from app.domain.entities import EquipmentContext, RiskClassification
from app.domain.services.text_utils import split_field as _split_field, append_unique as _append_unique

# ---------------------------------------------------------------------------
# Constantes — Ordenação de severidade/risco (ascendente)
# ---------------------------------------------------------------------------

#: Hierarquia de severidade (índice maior = mais grave).
#: Usada para consolidar múltiplas linhas → valor mais alto.
SEVERITY_ORDER: dict[str, int] = {
    "baixa": 0,
    "média": 1,
    "media": 1,          # normalização sem acento
    "média para alta": 2,
    "media para alta": 2,
    "alta": 3,
    "muito alta": 4,
}

#: Hierarquia de risco (índice maior = mais grave).
RISK_ORDER: dict[str, int] = {
    "baixo": 0,
    "médio": 1,
    "medio": 1,
    "alto": 2,
    "muito alto": 3,
}

# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _highest_severity(current: str, candidate: str) -> str:
    """Retorna a severidade mais alta entre duas strings.

    Comparação case-insensitive. Valores desconhecidos são tratados como
    prioridade -1 (nunca sobrescrevem um valor conhecido).
    """
    cur_rank = SEVERITY_ORDER.get(current.lower().strip(), -1)
    cand_rank = SEVERITY_ORDER.get(candidate.lower().strip(), -1)
    return candidate if cand_rank > cur_rank else current


def _highest_risk(current: str, candidate: str) -> str:
    """Retorna o risco mais alto entre duas strings."""
    cur_rank = RISK_ORDER.get(current.lower().strip(), -1)
    cand_rank = RISK_ORDER.get(candidate.lower().strip(), -1)
    return candidate if cand_rank > cur_rank else current


# ---------------------------------------------------------------------------
# Builder público
# ---------------------------------------------------------------------------

def build_equipment_contexts(
    rows_dicts: list[dict[str, Any]],
) -> list[EquipmentContext]:
    """Agrupa linhas da planilha e produz um ``EquipmentContext`` por equipamento.

    Implementa as regras de agrupamento definidas no docstring do módulo e
    no contrato ``docs/equipment_llm_contract.md``, §2.3.

    Args:
        rows_dicts: Linhas normalizadas da planilha
            (``MachineRiskRow.model_dump()``). Cada dict deve conter ao
            menos ``equipamento`` e ``perigo``.

    Returns:
        Lista ordenada de ``EquipmentContext``, um por equipamento distinto,
        na ordem de primeira aparição na planilha. O campo ``index`` é
        sequencial a partir de 1.

    Raises:
        ValueError: Se ``rows_dicts`` estiver vazia.

    Example::

        rows = [row.model_dump(mode="json") for row in parsed_rows]
        contexts = build_equipment_contexts(rows)
        for ctx in contexts:
            print(ctx.equipment_name, len(ctx.identificacao_dos_perigos))
    """
    if not rows_dicts:
        raise ValueError("rows_dicts não pode estar vazio")

    # ── Fase 1: Agrupar linhas por equipamento ────────────────────
    #
    # Usamos OrderedDict para preservar a ordem de primeira aparição,
    # garantindo determinismo independente da implementação de dict.

    groups: OrderedDict[str, _EquipmentAccumulator] = OrderedDict()

    for row in rows_dicts:
        name = (row.get("equipamento") or "").strip()
        if not name:
            logger.warning(
                "Linha ignorada — campo 'equipamento' vazio | row={}",
                row,
            )
            continue

        key = name.lower()

        if key not in groups:
            groups[key] = _EquipmentAccumulator(display_name=name)

        groups[key].absorb(row)

    # ── Fase 2: Converter acumuladores → EquipmentContext ─────────

    contexts: list[EquipmentContext] = []
    for idx, (_, acc) in enumerate(groups.items(), start=1):
        ctx = acc.to_context(index=idx)
        if ctx is not None:
            contexts.append(ctx)

    logger.info(
        "EquipmentContexts construídos | total_rows={} | equipamentos={}",
        len(rows_dicts),
        len(contexts),
    )

    return contexts


# ---------------------------------------------------------------------------
# Acumulador interno (mutable, usado apenas durante o build)
# ---------------------------------------------------------------------------

class _EquipmentAccumulator:
    """Acumula dados de múltiplas linhas para um mesmo equipamento.

    Uso exclusivamente interno — não faz parte da API pública. Após
    o agrupamento, é convertido em ``EquipmentContext`` (imutável)
    via ``to_context()``.
    """

    __slots__ = (
        "display_name",
        "descricao",
        "perigos",
        "causas",
        "consequencias",
        "severidade",
        "risco",
        "medidas_existentes",
        "medidas_implementar",
        "observacoes",
        "riscos_desc",
        "row_count",
    )

    def __init__(self, display_name: str) -> None:
        self.display_name = display_name
        self.descricao: str = ""
        self.perigos: list[str] = []
        self.causas: list[str] = []
        self.consequencias: list[str] = []
        self.severidade: str = ""
        self.risco: str = ""
        self.medidas_existentes: list[str] = []
        self.medidas_implementar: list[str] = []
        self.observacoes: list[str] = []
        self.riscos_desc: list[str] = []
        self.row_count: int = 0

    def absorb(self, row: dict[str, Any]) -> None:
        """Absorve uma linha da planilha dentro do acumulador.

        Aplica as regras de deduplicação, severidade máxima e
        seleção de descrição mais longa.
        """
        self.row_count += 1

        # Descrição: manter a mais longa
        desc = (row.get("descricao_equipamento") or "").strip()
        if desc and len(desc) > len(self.descricao):
            self.descricao = desc

        # Severidade: consolidar para o mais alto (não o primeiro)
        sev = (row.get("categoria_severidade") or "").strip()
        if sev:
            self.severidade = (
                _highest_severity(self.severidade, sev)
                if self.severidade
                else sev
            )

        # Risco: consolidar para o mais alto
        risco = (row.get("categoria_risco") or "").strip()
        if risco:
            self.risco = (
                _highest_risk(self.risco, risco)
                if self.risco
                else risco
            )

        # Campos multivalorados — split + dedup
        _append_unique(self.perigos, _split_field(row.get("perigo")))
        _append_unique(self.causas, _split_field(row.get("causas")))
        _append_unique(self.consequencias, _split_field(row.get("consequencias")))
        _append_unique(
            self.medidas_existentes,
            _split_field(row.get("medidas_existentes")),
        )
        _append_unique(
            self.medidas_implementar,
            _split_field(row.get("medidas_implementar")),
        )
        _append_unique(self.riscos_desc, _split_field(row.get("riscos")))

        obs = (row.get("observacoes") or "").strip()
        if obs and obs not in self.observacoes:
            self.observacoes.append(obs)

    def to_context(self, *, index: int) -> EquipmentContext | None:
        """Converte o acumulador em um ``EquipmentContext`` imutável.

        Retorna ``None`` se dados mínimos não forem atendidos
        (sem perigos identificados).
        """
        if not self.perigos:
            logger.warning(
                "Equipamento '{}' ignorado — nenhum perigo identificado",
                self.display_name,
            )
            return None

        if not self.causas:
            logger.warning(
                "Equipamento '{}' — nenhuma causa; usando placeholder",
                self.display_name,
            )
            self.causas = ["Causa não especificada na planilha"]

        if not self.consequencias:
            logger.warning(
                "Equipamento '{}' — nenhuma consequência; usando placeholder",
                self.display_name,
            )
            self.consequencias = ["Consequência não especificada na planilha"]

        return EquipmentContext(
            index=index,
            equipment_name=self.display_name,
            descricao_da_operacao=self.descricao or "Não informado",
            identificacao_dos_perigos=list(self.perigos),
            causas_possiveis=list(self.causas),
            consequencias_potenciais=list(self.consequencias),
            classificacao_do_risco=RiskClassification(
                categoria_severidade=self.severidade or "Não informada",
                categoria_risco=self.risco or "Não informado",
            ),
            medidas_preventivas_existentes=list(self.medidas_existentes),
            medidas_a_implementar=list(self.medidas_implementar),
            observacoes=list(self.observacoes),
            riscos_descricao=list(self.riscos_desc),
            row_count=self.row_count,
        )
