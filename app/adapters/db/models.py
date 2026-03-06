"""Modelos SQLAlchemy 2.0 (Mapped / declarative) para persistência.

Tabelas:

* ``uploads`` — metadados de planilhas enviadas.
* ``report_drafts`` — rascunhos normalizados (rows + metadata JSONB).
* ``generated_reports`` — laudos finais em PDF.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


# ---------------------------------------------------------------------------
# Base declarativa
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """Base compartilhada para todos os modelos ORM."""

    pass


# ---------------------------------------------------------------------------
# uploads
# ---------------------------------------------------------------------------

class Upload(Base):
    """Registro de uma planilha enviada pelo usuário."""

    __tablename__ = "uploads"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(256), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    # relacionamento 1→N com report_drafts
    drafts: Mapped[list["ReportDraft"]] = relationship(
        back_populates="upload",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Upload id={self.id} filename={self.filename!r}>"


# ---------------------------------------------------------------------------
# report_drafts
# ---------------------------------------------------------------------------

class ReportDraft(Base):
    """Rascunho normalizado — contém metadados e linhas de risco em JSONB."""

    __tablename__ = "report_drafts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    upload_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("uploads.id", ondelete="CASCADE"),
        nullable=False,
    )
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        default=None,
    )
    rows_json: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # relacionamentos
    upload: Mapped["Upload"] = relationship(back_populates="drafts")
    generated_reports: Mapped[list["GeneratedReport"]] = relationship(
        back_populates="draft",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<ReportDraft id={self.id} upload_id={self.upload_id}>"


# ---------------------------------------------------------------------------
# generated_reports
# ---------------------------------------------------------------------------

class GeneratedReport(Base):
    """Metadados de um laudo PDF gerado."""

    __tablename__ = "generated_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    draft_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("report_drafts.id", ondelete="CASCADE"),
        nullable=False,
    )
    pdf_storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    # relacionamento
    draft: Mapped["ReportDraft"] = relationship(back_populates="generated_reports")

    def __repr__(self) -> str:
        return f"<GeneratedReport id={self.id} version={self.version}>"
