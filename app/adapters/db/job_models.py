"""Modelos SQLAlchemy para as tabelas ``jobs`` e ``job_steps``.

Estas tabelas são gerenciadas pelo Prisma (Next.js), mas este serviço
precisa lê-las e atualizá-las para reportar progresso de processamento.

IMPORTANTE: Não altere a estrutura destas tabelas aqui — as migrations
são responsabilidade do Prisma no projeto Next.js.
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
from sqlalchemy.dialects.postgresql import ENUM as PgEnum, UUID
from sqlalchemy.orm import Mapped, mapped_column

# Enum nativo do PostgreSQL criado pelo Prisma
_job_status_enum = PgEnum(
    "queued", "processing", "done", "error",
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
