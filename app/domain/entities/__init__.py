"""Entidades de domínio — modelos ricos que encapsulam regras de negócio."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    """Retorna datetime UTC atual (compatível com Pydantic default_factory)."""
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# SpreadsheetUpload
# ---------------------------------------------------------------------------

class SpreadsheetUpload(BaseModel):
    """Metadados de um arquivo de planilha enviado pelo usuário."""

    id: str = Field(default_factory=_new_uuid, description="UUID do upload")
    filename: str = Field(..., description="Nome original do arquivo")
    content_type: str = Field(
        ..., description="MIME type (ex.: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)"
    )
    size_bytes: int = Field(..., ge=0, description="Tamanho do arquivo em bytes")
    uploaded_at: datetime = Field(default_factory=_utcnow, description="Timestamp UTC do upload")

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# Enums auxiliares
# ---------------------------------------------------------------------------

class RiskLevel(str, Enum):
    """Níveis de risco padronizados."""

    TRIVIAL = "trivial"
    TOLERAVEL = "tolerável"
    MODERADO = "moderado"
    SUBSTANCIAL = "substancial"
    INTOLERAVEL = "intolerável"


class PriorityLevel(str, Enum):
    """Prioridade da ação recomendada."""

    BAIXA = "baixa"
    MEDIA = "média"
    ALTA = "alta"
    URGENTE = "urgente"


# ---------------------------------------------------------------------------
# MachineRiskRow
# ---------------------------------------------------------------------------

class MachineRiskRow(BaseModel):
    """Linha normalizada da planilha de riscos de máquinas / equipamentos.

    Cada instância representa **um** perigo identificado para um equipamento.
    Campos mapeados a partir da planilha padrão de análise de risco.
    """

    # Identificação
    equipamento: str = Field(..., description="Nome ou tag do equipamento")
    descricao_equipamento: Optional[str] = Field(None, description="Descrição detalhada do equipamento")

    # Perigo e causas
    riscos: Optional[str] = Field(None, description="Descrição geral dos riscos associados")
    perigo: str = Field(..., description="Descrição do perigo identificado")
    causas: str = Field(..., description="Causas possíveis do perigo")
    consequencias: str = Field(..., description="Consequências potenciais do perigo")

    # Avaliação de risco
    categoria_severidade: Optional[str] = Field(None, description="Categoria da severidade (texto livre ou escala)")
    categoria_risco: Optional[str] = Field(None, description="Categoria do risco (texto livre ou escala)")

    # V3 — avaliação atual (campos explícitos)
    categoria_probabilidade: Optional[str] = Field(None, description="Categoria da Probabilidade (V3)")
    classificacao_risco: Optional[str] = Field(None, description="Classificação consolidada do Risco (V3)")

    # V3 — avaliação residual (pós-implementação das medidas preventivas)
    categoria_severidade_2: Optional[str] = Field(None, description="Severidade residual pós-implementação")
    categoria_probabilidade_2: Optional[str] = Field(None, description="Probabilidade residual pós-implementação")
    classificacao_risco_2: Optional[str] = Field(None, description="Classificação de risco residual pós-implementação")

    # Medidas preventivas
    medidas_existentes: Optional[str] = Field(None, description="Medidas preventivas já existentes")
    medidas_implementar: Optional[str] = Field(None, description="Medidas preventivas a implementar")

    # Metadados opcionais
    observacoes: Optional[str] = Field(None, description="Observações extras")

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# ReportDraft
# ---------------------------------------------------------------------------

class CompanyMetadata(BaseModel):
    """Dados da empresa / site avaliado.

    Estes campos aparecem na capa e no contexto do relatório.
    Campos opcionais são omitidos da capa quando ``None``.
    """

    razao_social: str = Field(..., description="Razão social / Nome do cliente")
    cnpj: Optional[str] = Field(None, description="CNPJ")
    site: Optional[str] = Field(None, description="Unidade / planta avaliada")
    endereco: Optional[str] = Field(None, description="Endereço da unidade")
    responsavel: Optional[str] = Field(None, description="Nome do responsável técnico")
    registro_profissional: Optional[str] = Field(None, description="CREA / registro profissional")
    elaboracao: Optional[str] = Field(None, description="Empresa que elaborou o relatório")
    local_vistoriado: Optional[str] = Field(None, description="Local / setor vistoriado")
    contrato: Optional[str] = Field(None, description="Número do contrato")
    data_avaliacao: Optional[datetime] = Field(None, description="Data da avaliação / vistoria")

    model_config = {"frozen": True}


class RiskClassification(BaseModel):
    """Classificação de risco consolidada de um equipamento.

    Representa os valores mais críticos (highest) entre todas as linhas
    de risco da planilha para um mesmo equipamento.
    """

    categoria_severidade: str = Field(
        ..., description="Severidade mais alta — ex.: 'Alta', 'Muito Alta'"
    )
    categoria_probabilidade: str = Field(
        ..., description="Probabilidade mais alta — ex.: 'Alto', 'Muito Alto'"
    )
    classificacao_risco: str = Field(
        ..., description="Classificação de risco consolidada — ex.: 'Alto', 'Muito Alto'"
    )

    # Compat: alias para código legado que usa categoria_risco
    @property
    def categoria_risco(self) -> str:
        """Alias de compatibilidade para categoria_probabilidade."""
        return self.categoria_probabilidade

    model_config = {"frozen": True}


class ResidualRiskClassification(BaseModel):
    """Classificação de risco residual — cenário pós-implementação das medidas preventivas."""

    categoria_severidade: Optional[str] = None
    categoria_probabilidade: Optional[str] = None
    classificacao_risco: Optional[str] = None

    model_config = {"frozen": True}


class EquipmentContext(BaseModel):
    """Contexto estruturado e normalizado de um único equipamento.

    Produzido pelo ``EquipmentContextBuilder`` após agrupar as linhas
    da planilha por equipamento. Cada instância contém **todos** os
    dados determinísticos necessários para:

    - Renderizar as sub-seções 4.N.1–4.N.7 do template PDF
    - Alimentar o LLM na geração per-equipment (Stage 5B)
    - Montar a tabela de recomendações

    Este objeto é **somente-leitura** após construção.

    Campos correspondem ao contrato definido em
    ``docs/equipment_llm_contract.md``, seção 2 (Input Schema).
    """

    # ── Identificação ─────────────────────────────────────────────
    index: int = Field(..., ge=1, description="Índice sequencial (1-based)")
    equipment_name: str = Field(..., min_length=1, description="Nome/tag do equipamento")
    descricao_da_operacao: str = Field(
        default="Não informado",
        description="Descrição funcional do equipamento",
    )

    # ── Análise de perigos (determinísticos da planilha) ──────────
    identificacao_dos_perigos: list[str] = Field(
        ..., min_length=1, description="Perigos identificados (≥ 1)"
    )
    causas_possiveis: list[str] = Field(
        ..., min_length=1, description="Causas possíveis (≥ 1)"
    )
    consequencias_potenciais: list[str] = Field(
        ..., min_length=1, description="Consequências potenciais (≥ 1)"
    )

    # ── Classificação do risco ────────────────────────────────────
    classificacao_do_risco: RiskClassification = Field(
        ..., description="Severidade, probabilidade e risco consolidados (highest)"
    )

    # ── Risco residual (V3 — pós-implementação) ─────────────────────
    classificacao_risco_residual: Optional[ResidualRiskClassification] = Field(
        None,
        description="Risco residual pós-implementação das medidas preventivas",
    )

    # ── Medidas existentes e seed de recomendações ────────────────
    medidas_preventivas_existentes: list[str] = Field(
        default_factory=list,
        description="Medidas já implementadas (pode ser vazio)",
    )
    medidas_a_implementar: list[str] = Field(
        default_factory=list,
        description="Seed de recomendações do analista (pode ser vazio)",
    )

    # ── Campos auxiliares (usados no template, não no LLM) ────────
    observacoes: list[str] = Field(
        default_factory=list,
        description="Observações da planilha",
    )
    riscos_descricao: list[str] = Field(
        default_factory=list,
        description="Descrições gerais de risco (coluna 'Riscos')",
    )

    # ── Contagem de linhas-fonte ──────────────────────────────────
    row_count: int = Field(
        ..., ge=1,
        description="Quantidade de linhas da planilha agregadas neste equipamento",
    )

    model_config = {"frozen": True}

    def to_template_dict(self) -> dict:
        """Convert to a dict compatible with the Jinja2 template format.

        Returns a dict with keys matching what the legacy
        ``group_rows_by_equipment()`` used to produce.
        """
        return {
            "index": self.index,
            "nome": self.equipment_name,
            "descricao": self.descricao_da_operacao,
            "perigos": list(self.identificacao_dos_perigos),
            "causas": list(self.causas_possiveis),
            "consequencias": list(self.consequencias_potenciais),
            "severidade": self.classificacao_do_risco.categoria_severidade,
            "risco": self.classificacao_do_risco.categoria_probabilidade,
            "probabilidade": self.classificacao_do_risco.categoria_probabilidade,
            "classificacao": self.classificacao_do_risco.classificacao_risco,
            # Bloco residual (None se não existir)
            "severidade_residual": self.classificacao_risco_residual.categoria_severidade if self.classificacao_risco_residual else None,
            "probabilidade_residual": self.classificacao_risco_residual.categoria_probabilidade if self.classificacao_risco_residual else None,
            "classificacao_residual": self.classificacao_risco_residual.classificacao_risco if self.classificacao_risco_residual else None,
            "medidas_existentes": list(self.medidas_preventivas_existentes),
            "medidas_implementar": list(self.medidas_a_implementar),
            "observacoes": list(self.observacoes),
            "riscos_desc": list(self.riscos_descricao),
            "row_count": self.row_count,
            # These will be filled by _enrich_equipments and _attach_equipment_narratives
            "local_instalacao": "",
            "funcao_operacional": "",
            "observacoes_extras": "",
            "images": [],
            "recomendacoes_tecnicas": [],
            "justificativas_tecnicas": [],
            "narrative_source": "none",
        }


# ---------------------------------------------------------------------------
# EquipmentLLMInput — payload exato enviado ao LLM
# ---------------------------------------------------------------------------

class EquipmentLLMInput(BaseModel):
    """Payload estruturado enviado ao LLM para um único equipamento.

    Contrato: ``docs/equipment_llm_contract.md``, §2.1.

    Este objeto é o *último ponto de contato* antes da chamada LLM.
    Todas as validações de input (IV-01…IV-09) e limites de tamanho
    (§5.1) já devem estar aplicados quando ele é construído.

    Imutável após criação.
    """

    # ── Identificação ─────────────────────────────────────────────
    equipment_name: str = Field(
        ..., min_length=1, max_length=200,
        description="Nome/tag do equipamento",
    )
    descricao_da_operacao: str = Field(
        ..., max_length=500,
        description="Descrição funcional — fallback 'Não informado'",
    )

    # ── Análise de perigos ────────────────────────────────────────
    identificacao_dos_perigos: list[str] = Field(
        ..., min_length=1, max_length=15,
        description="Perigos identificados (≥ 1, ≤ 15)",
    )
    causas_possiveis: list[str] = Field(
        ..., min_length=1, max_length=15,
        description="Causas possíveis (≥ 1, ≤ 15)",
    )
    consequencias_potenciais: list[str] = Field(
        ..., min_length=1, max_length=15,
        description="Consequências potenciais (≥ 1, ≤ 15)",
    )

    # ── Classificação do risco ────────────────────────────────────
    classificacao_do_risco: RiskClassification = Field(
        ..., description="Severidade, probabilidade e risco consolidados (highest)",
    )

    # ── Risco residual (V3) ───────────────────────────────────
    classificacao_risco_residual: Optional[ResidualRiskClassification] = Field(
        None,
        description="Risco residual pós-implementação (quando disponível)",
    )

    # ── Medidas ───────────────────────────────────────────────────
    medidas_preventivas_existentes: list[str] = Field(
        default_factory=list, max_length=15,
        description="Medidas já implementadas (pode ser [])",
    )
    medidas_a_implementar: list[str] = Field(
        default_factory=list, max_length=15,
        description="Seed de recomendações do analista (pode ser [])",
    )

    # ── Normas aplicáveis (do profile config) ─────────────────────
    normas_aplicaveis: list[str] = Field(
        ..., min_length=1, max_length=15,
        description="Normas do perfil de análise",
    )

    # ── Contexto externo opcional (RAG / retrieval futuro) ────────
    normative_context: list["NormativeExcerpt"] = Field(
        default_factory=list,
        max_length=10,
        description=(
            "Trechos normativos recuperados por RAG/retrieval, relevantes "
            "para este equipamento. Populado por adaptadores futuros "
            "(e.g. ABNT vector store). Quando vazio, o prompt não inclui "
            "bloco de contexto normativo."
        ),
    )
    literature_context: list["LiteratureExcerpt"] = Field(
        default_factory=list,
        max_length=10,
        description=(
            "Trechos de literatura técnica recuperados por RAG/retrieval. "
            "Populado por adaptadores futuros (e.g. corpus técnico). "
            "Quando vazio, o prompt não inclui bloco de literatura."
        ),
    )

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# External context excerpts (RAG / retrieval — future)
# ---------------------------------------------------------------------------


class NormativeExcerpt(BaseModel):
    """Trecho de norma técnica recuperado por RAG ou busca vetorial.

    Representa um fragmento relevante de uma norma ABNT, NFPA, IEC etc.
    que foi selecionado automaticamente como contexto adicional para a
    geração per-equipment.

    Campos:
        source: Identificador da norma (e.g. ``"NFPA 652:2022"``).
        section: Seção ou cláusula específica (e.g. ``"8.2.1"``).
            Opcional — pode ser ``None`` se o trecho não tem seção.
        text: Texto integral ou resumido do trecho normativo.
        relevance_score: Score de relevância retornado pelo retriever
            (0.0–1.0). Opcional — usado para ordenação/filtragem.
    """

    source: str = Field(..., min_length=1, max_length=200, description="Norma de origem")
    section: Optional[str] = Field(None, max_length=50, description="Seção/cláusula")
    text: str = Field(..., min_length=1, max_length=2000, description="Texto do trecho")
    relevance_score: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Score de relevância (0–1)"
    )

    model_config = {"frozen": True}


class LiteratureExcerpt(BaseModel):
    """Trecho de literatura técnica recuperado por RAG ou busca vetorial.

    Representa um fragmento de publicação técnica, artigo, manual ou
    guia de boas práticas selecionado como contexto adicional.

    Campos:
        source: Título ou referência bibliográfica da publicação.
        text: Texto integral ou resumido do trecho.
        relevance_score: Score de relevância (0.0–1.0). Opcional.
    """

    source: str = Field(..., min_length=1, max_length=300, description="Publicação de origem")
    text: str = Field(..., min_length=1, max_length=2000, description="Texto do trecho")
    relevance_score: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Score de relevância (0–1)"
    )

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# EquipmentLLMOutput — resposta estruturada do LLM per-equipment
# ---------------------------------------------------------------------------


class RecomendacaoTecnica(BaseModel):
    """Uma recomendação técnica numerada com referência normativa.

    Contrato: ``docs/equipment_llm_contract.md``, §3.1.

    Campos adicionais para rastreabilidade:
        tipo: ``"normativa"`` se fundamentada em trecho normativo explícito,
              ``"boa_pratica"`` se baseada em conhecimento técnico sem
              evidência normativa literal.
        trecho_normativo: Texto literal do trecho normativo que fundamenta
              a recomendação. Obrigatório quando ``tipo == 'normativa'``.
    """

    numero: int = Field(..., ge=1, description="Número sequencial (1-based)")
    texto: str = Field(..., min_length=1, description="Texto da recomendação")
    norma_referencia: str = Field(
        ..., min_length=1, description="Norma que fundamenta a recomendação"
    )
    tipo: Literal["normativa", "boa_pratica"] = Field(
        default="boa_pratica",
        description="Classificação: 'normativa' (com trecho) ou 'boa_pratica' (sem evidência normativa)",
    )
    trecho_normativo: Optional[str] = Field(
        None,
        max_length=2000,
        description="Texto literal do trecho normativo usado como fundamentação (obrigatório se tipo='normativa')",
    )

    model_config = {"frozen": True}


class JustificativaTecnica(BaseModel):
    """Uma justificativa técnica numerada, correspondente a uma recomendação.

    Contrato: ``docs/equipment_llm_contract.md``, §3.1.
    """

    numero: int = Field(..., ge=1, description="Número correspondente à recomendação")
    texto: str = Field(..., min_length=1, description="Texto da justificativa")

    model_config = {"frozen": True}


class EquipmentLLMOutput(BaseModel):
    """Saída estruturada do LLM para um único equipamento.

    Contrato: ``docs/equipment_llm_contract.md``, §3.

    Contém recomendações técnicas numeradas e justificativas técnicas
    correspondentes, com correspondência 1:1 por ``numero``.
    """

    recomendacoes_tecnicas: list[RecomendacaoTecnica] = Field(
        ..., min_length=2, max_length=10,
        description="Recomendações técnicas (2–10 itens)",
    )
    justificativas_tecnicas: list[JustificativaTecnica] = Field(
        ..., min_length=2, max_length=10,
        description="Justificativas técnicas (mesmo tamanho que recomendacoes)",
    )

    model_config = {"frozen": True}


class Attachment(BaseModel):
    """Referência a um anexo (foto, documento complementar, etc.)."""

    filename: str
    storage_key: str = Field(..., description="Chave no object-storage")
    content_type: Optional[str] = None
    description: Optional[str] = None


class ReportDraft(BaseModel):
    """Rascunho completo de um laudo — agrupa metadados, riscos e anexos.

    É o objeto central que alimenta a geração do relatório final.
    """

    id: str = Field(default_factory=_new_uuid)
    company: CompanyMetadata
    rows: list[MachineRiskRow] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: Optional[datetime] = None

    model_config = {"frozen": False}  # draft é mutável até gerar o relatório


# ---------------------------------------------------------------------------
# GeneratedReport
# ---------------------------------------------------------------------------

class GeneratedReport(BaseModel):
    """Relatório final gerado (PDF) — imutável após criação."""

    report_id: str = Field(default_factory=_new_uuid, description="UUID do relatório")
    draft_id: str = Field(..., description="ID do ReportDraft que originou o laudo")
    pdf_path: Optional[str] = Field(None, description="Caminho local ou key no storage")
    pdf_url: Optional[str] = Field(None, description="URL pública / assinada do PDF")
    created_at: datetime = Field(default_factory=_utcnow)
    checksum: str = Field(..., description="SHA-256 do PDF gerado")
    version: int = Field(default=1, ge=1, description="Versão do laudo")

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# Re-exports convenientes
# ---------------------------------------------------------------------------

__all__ = [
    "SpreadsheetUpload",
    "RiskLevel",
    "PriorityLevel",
    "MachineRiskRow",
    "RiskClassification",
    "ResidualRiskClassification",
    "EquipmentContext",
    "EquipmentLLMInput",
    "NormativeExcerpt",
    "LiteratureExcerpt",
    "RecomendacaoTecnica",
    "JustificativaTecnica",
    "EquipmentLLMOutput",
    "CompanyMetadata",
    "Attachment",
    "ReportDraft",
    "GeneratedReport",
]
