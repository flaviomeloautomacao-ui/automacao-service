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
    """

    # Identificação
    area: str = Field(..., description="Área / setor onde o equipamento se encontra")
    equipamento: str = Field(..., description="Nome ou tag do equipamento")

    # Perigo e causas
    perigo: str = Field(..., description="Descrição do perigo identificado")
    causa: str = Field(..., description="Causa-raiz ou fator contribuinte")
    consequencia: str = Field(..., description="Consequência potencial do perigo")

    # Avaliação de risco
    risco: RiskLevel = Field(..., description="Nível de risco avaliado")
    probabilidade: Optional[str] = Field(None, description="Probabilidade de ocorrência (texto livre ou escala)")
    severidade: Optional[str] = Field(None, description="Severidade do dano (texto livre ou escala)")

    # Normas e recomendações
    norma_ref: Optional[str] = Field(None, description="Referência normativa (ex.: NR-12, ISO 12100)")
    recomendacao: Optional[str] = Field(None, description="Ação recomendada para mitigar o risco")
    prioridade: Optional[PriorityLevel] = Field(None, description="Prioridade da recomendação")

    # Metadados opcionais
    foto_ref: Optional[str] = Field(None, description="Referência à foto / evidência (path ou URL)")
    observacoes: Optional[str] = Field(None, description="Observações extras")

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# ReportDraft
# ---------------------------------------------------------------------------

class CompanyMetadata(BaseModel):
    """Dados da empresa / site avaliado."""

    razao_social: str = Field(..., description="Razão social da empresa")
    cnpj: Optional[str] = Field(None, description="CNPJ")
    site: Optional[str] = Field(None, description="Unidade / planta avaliada")
    endereco: Optional[str] = Field(None, description="Endereço da unidade")
    responsavel: Optional[str] = Field(None, description="Responsável técnico")
    data_avaliacao: Optional[datetime] = Field(None, description="Data da avaliação em campo")

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
