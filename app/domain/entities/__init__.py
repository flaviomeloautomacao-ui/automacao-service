"""Entidades de domínio — modelos ricos que encapsulam regras de negócio."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

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
    "CompanyMetadata",
    "Attachment",
    "ReportDraft",
    "GeneratedReport",
]
