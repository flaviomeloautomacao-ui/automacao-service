"""Modelos SQLAlchemy para as tabelas gerenciadas pelo Prisma.

Estas tabelas são gerenciadas pelo Prisma (Next.js), mas este serviço
precisa lê-las e atualizá-las para reportar progresso de processamento.

Tabelas mapeadas:
  - ``jobs`` / ``job_steps`` — pipeline de processamento
  - ``reports`` / ``report_equipments`` / ``equipment_images`` — complementação
  - ``spreadsheet_uploads`` / ``spreadsheet_rows`` — dados brutos da planilha

IMPORTANTE: Não altere a estrutura destas tabelas aqui — as migrations
são responsabilidade do Prisma no projeto Next.js.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ENUM as PgEnum, JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Enum nativo do PostgreSQL criado pelo Prisma
_job_status_enum = PgEnum(
    "queued", "awaiting_complement", "processing", "done", "error",
    name="JobStatus",
    create_type=False,   # Prisma já criou o tipo; não recriar
)

from app.adapters.db.models import Base


class Job(Base):
    """Modelo ORM (somente leitura/update) para a tabela ``jobs``.

    Criado pelo Next.js via Prisma; Python atualiza status/progresso.
    """

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
    )
    filename: Mapped[str | None] = mapped_column(String, nullable=True)
    profile: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(_job_status_enum, nullable=False, default="queued")
    progress: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    current_step: Mapped[str | None] = mapped_column(String, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    archive_path: Mapped[str | None] = mapped_column(String, nullable=True)
    archive_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    pdf_path: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Campos de observabilidade (v2) ──
    input_hash: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    llm_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_call_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pipeline_version_id: Mapped[str | None] = mapped_column(String, nullable=True)
    dedup_source_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=True,
    )

    def __repr__(self) -> str:
        return f"<Job id={self.id} status={self.status}>"


class JobStep(Base):
    """Modelo ORM (somente leitura/update) para a tabela ``job_steps``."""

    __tablename__ = "job_steps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(_job_status_enum, nullable=False, default="queued")
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<JobStep id={self.id} name={self.name} status={self.status}>"


# ======================================================================
# Tabelas de planilha (Prisma: SpreadsheetUpload / SpreadsheetRow)
# ======================================================================


class SpreadsheetUploadModel(Base):
    """Modelo ORM (somente leitura) para ``spreadsheet_uploads``."""

    __tablename__ = "spreadsheet_uploads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    mime_type: Mapped[str] = mapped_column(String, nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    rows: Mapped[list["SpreadsheetRowModel"]] = relationship(
        back_populates="upload", lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<SpreadsheetUploadModel id={self.id} job_id={self.job_id}>"


class SpreadsheetRowModel(Base):
    """Modelo ORM (somente leitura) para ``spreadsheet_rows``."""

    __tablename__ = "spreadsheet_rows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    upload_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("spreadsheet_uploads.id", ondelete="CASCADE"),
        nullable=False,
    )
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    equipment_name: Mapped[str | None] = mapped_column(String, nullable=True)
    equipment_description: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    normalized_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    upload: Mapped["SpreadsheetUploadModel"] = relationship(back_populates="rows")

    def __repr__(self) -> str:
        return f"<SpreadsheetRowModel id={self.id} row_index={self.row_index}>"


# ======================================================================
# Tabelas de complementação (Prisma: Report / ReportEquipment / EquipmentImage)
# ======================================================================


class ReportModel(Base):
    """Modelo ORM (somente leitura) para ``reports``."""

    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    razao_social: Mapped[str | None] = mapped_column(String, nullable=True)
    cnpj: Mapped[str | None] = mapped_column(String, nullable=True)
    site: Mapped[str | None] = mapped_column(String, nullable=True)
    endereco: Mapped[str | None] = mapped_column(String, nullable=True)
    local_vistoriado: Mapped[str | None] = mapped_column(String, nullable=True)
    data_avaliacao: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    contrato: Mapped[str | None] = mapped_column(String, nullable=True)
    elaboracao: Mapped[str | None] = mapped_column(String, nullable=True)
    responsavel: Mapped[str | None] = mapped_column(String, nullable=True)
    registro_profissional: Mapped[str | None] = mapped_column(String, nullable=True)
    observacoes_gerais: Mapped[str | None] = mapped_column(Text, nullable=True)
    observacoes_gerais_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Novos campos (Fase 1) ──
    cover_image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    cover_image_public_id: Mapped[str | None] = mapped_column(String, nullable=True)
    art_numero: Mapped[str | None] = mapped_column(String, nullable=True)
    codigo_documento: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )

    equipments: Mapped[list["ReportEquipmentModel"]] = relationship(
        back_populates="report", lazy="selectin",
    )
    revisions: Mapped[list["ReportRevisionModel"]] = relationship(
        back_populates="report", lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<ReportModel id={self.id} job_id={self.job_id}>"


class ReportRevisionModel(Base):
    """Modelo ORM (somente leitura) para ``report_revisions``."""

    __tablename__ = "report_revisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reports.id", ondelete="CASCADE"),
        nullable=False,
    )

    version: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[str] = mapped_column(String, nullable=False)
    author: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    report: Mapped["ReportModel"] = relationship(back_populates="revisions")

    def __repr__(self) -> str:
        return f"<ReportRevisionModel id={self.id} version={self.version}>"


class ReportEquipmentModel(Base):
    """Modelo ORM (somente leitura) para ``report_equipments``."""

    __tablename__ = "report_equipments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reports.id", ondelete="CASCADE"),
        nullable=False,
    )

    equipment_name: Mapped[str] = mapped_column(String, nullable=False)
    equipment_description: Mapped[str | None] = mapped_column(String, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    local_instalacao: Mapped[str | None] = mapped_column(String, nullable=True)
    funcao_operacional: Mapped[str | None] = mapped_column(String, nullable=True)
    observacoes_extras: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )

    report: Mapped["ReportModel"] = relationship(back_populates="equipments")
    images: Mapped[list["EquipmentImageModel"]] = relationship(
        back_populates="equipment", lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<ReportEquipmentModel id={self.id} name={self.equipment_name}>"


class EquipmentImageModel(Base):
    """Modelo ORM (somente leitura) para ``equipment_images``."""

    __tablename__ = "equipment_images"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    equipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("report_equipments.id", ondelete="CASCADE"),
        nullable=False,
    )

    public_id: Mapped[str] = mapped_column(String, nullable=False)
    secure_url: Mapped[str] = mapped_column(String, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    equipment: Mapped["ReportEquipmentModel"] = relationship(back_populates="images")

    def __repr__(self) -> str:
        return f"<EquipmentImageModel id={self.id} equipment_id={self.equipment_id}>"


# ======================================================================
# Tabelas de observabilidade LLM (v2)
# ======================================================================


class LlmUsageLogModel(Base):
    """Mirror SQLAlchemy da tabela ``llm_usage_logs`` (Prisma-managed)."""

    __tablename__ = "llm_usage_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )

    flow: Mapped[str] = mapped_column(String, nullable=False)
    step: Mapped[str] = mapped_column(String, nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    call_type: Mapped[str] = mapped_column(String, nullable=False)

    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_source: Mapped[str] = mapped_column(String, nullable=False, default="estimate")

    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)

    equipment_name: Mapped[str | None] = mapped_column(String, nullable=True)

    prompt_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    def __repr__(self) -> str:
        return f"<LlmUsageLogModel id={self.id} job_id={self.job_id} step={self.step}>"


class PipelineVersionModel(Base):
    """Mirror SQLAlchemy da tabela ``pipeline_versions`` (Prisma-managed)."""

    __tablename__ = "pipeline_versions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    prompt_version: Mapped[str] = mapped_column(String, nullable=False)
    schema_version: Mapped[str] = mapped_column(String, nullable=False)
    rag_strategy: Mapped[str] = mapped_column(String, nullable=False)
    llm_model: Mapped[str] = mapped_column(String, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String, nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String, nullable=False)
    schema_hash: Mapped[str] = mapped_column(String, nullable=False)
    rag_top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    rag_max_chunks: Mapped[int] = mapped_column(Integer, nullable=False)
    rag_min_score: Mapped[float] = mapped_column(Float, nullable=False)
    config_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    def __repr__(self) -> str:
        return f"<PipelineVersionModel id={self.id} llm_model={self.llm_model}>"
