"""Repositório concreto — implementa ``ReportRepositoryPort`` com SQLAlchemy async.

Todos os métodos recebem uma ``AsyncSession`` (injetada via Depends no FastAPI)
e traduzem entidades de domínio ↔ modelos ORM.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.db.models import (
    GeneratedReport as GeneratedReportModel,
    ReportDraft as ReportDraftModel,
    Upload as UploadModel,
)
from app.domain.errors import DBError


class ReportRepository:
    """Implementação concreta de ``ReportRepositoryPort``.

    Recebe a sessão do banco no construtor — isso facilita a
    injeção de dependência via FastAPI Depends.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # uploads
    # ------------------------------------------------------------------

    async def create_upload(
        self,
        *,
        filename: str,
        content_type: str,
        size_bytes: int,
        storage_path: str,
        expires_at: datetime | None = None,
    ) -> str:
        """Persiste um registro de upload e retorna o UUID gerado.

        Args:
            filename: Nome original do arquivo enviado pelo usuário.
            content_type: MIME type do arquivo.
            size_bytes: Tamanho em bytes.
            storage_path: Chave / caminho no object-storage.
            expires_at: Data/hora de expiração (UTC). ``None`` = sem expiração.

        Returns:
            UUID do upload como string.

        Raises:
            DBError: Falha de persistência.
        """
        try:
            upload = UploadModel(
                filename=filename,
                content_type=content_type,
                size_bytes=size_bytes,
                storage_path=storage_path,
                expires_at=expires_at,
            )
            self._session.add(upload)
            await self._session.flush()
            return str(upload.id)
        except Exception as exc:
            raise DBError(f"Falha ao criar upload: {exc}") from exc

    # ------------------------------------------------------------------
    # report_drafts
    # ------------------------------------------------------------------

    async def create_draft(
        self,
        *,
        upload_id: str,
        metadata: dict[str, Any] | None = None,
        rows_json: list[dict[str, Any]] | None = None,
    ) -> str:
        """Persiste um rascunho de laudo e retorna o UUID gerado.

        Args:
            upload_id: UUID do upload que originou o draft.
            metadata: Metadados JSONB (dados da empresa, contexto, etc.).
            rows_json: Lista de linhas de risco serializadas em JSON.

        Returns:
            UUID do draft como string.

        Raises:
            DBError: Falha de persistência.
        """
        try:
            draft = ReportDraftModel(
                upload_id=uuid.UUID(upload_id),
                metadata_=metadata,
                rows_json=rows_json,
            )
            self._session.add(draft)
            await self._session.flush()
            return str(draft.id)
        except Exception as exc:
            raise DBError(f"Falha ao criar draft: {exc}") from exc

    # ------------------------------------------------------------------
    # generated_reports
    # ------------------------------------------------------------------

    async def create_generated(
        self,
        *,
        draft_id: str,
        pdf_storage_path: str,
        pdf_url: str | None = None,
        checksum: str,
        version: int = 1,
        expires_at: datetime | None = None,
    ) -> str:
        """Persiste metadados de um relatório gerado e retorna o UUID.

        Args:
            draft_id: UUID do draft de origem.
            pdf_storage_path: Caminho no storage para o PDF.
            pdf_url: URL pública / assinada (opcional).
            checksum: SHA-256 do PDF.
            version: Versão do laudo (padrão 1).
            expires_at: Data/hora de expiração (UTC). ``None`` = sem expiração.

        Returns:
            UUID do relatório gerado como string.

        Raises:
            DBError: Falha de persistência.
        """
        try:
            report = GeneratedReportModel(
                draft_id=uuid.UUID(draft_id),
                pdf_storage_path=pdf_storage_path,
                pdf_url=pdf_url,
                checksum=checksum,
                version=version,
                expires_at=expires_at,
            )
            self._session.add(report)
            await self._session.flush()
            return str(report.id)
        except Exception as exc:
            raise DBError(f"Falha ao criar generated report: {exc}") from exc

    # ------------------------------------------------------------------
    # leitura
    # ------------------------------------------------------------------

    async def get_draft(self, draft_id: str) -> Optional[dict[str, Any]]:
        """Recupera um draft pelo UUID.

        Returns:
            Dicionário com os campos do draft, ou ``None`` se inexistente.

        Raises:
            DBError: Falha de leitura.
        """
        try:
            stmt = select(ReportDraftModel).where(
                ReportDraftModel.id == uuid.UUID(draft_id)
            )
            result = await self._session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return {
                "id": str(row.id),
                "upload_id": str(row.upload_id),
                "metadata": row.metadata_,
                "rows_json": row.rows_json,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        except DBError:
            raise
        except Exception as exc:
            raise DBError(f"Falha ao buscar draft {draft_id}: {exc}") from exc

    async def get_generated(self, report_id: str) -> Optional[dict[str, Any]]:
        """Recupera um relatório gerado pelo UUID.

        Returns:
            Dicionário com os campos do relatório, ou ``None`` se inexistente.

        Raises:
            DBError: Falha de leitura.
        """
        try:
            stmt = select(GeneratedReportModel).where(
                GeneratedReportModel.id == uuid.UUID(report_id)
            )
            result = await self._session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return {
                "id": str(row.id),
                "draft_id": str(row.draft_id),
                "pdf_storage_path": row.pdf_storage_path,
                "pdf_url": row.pdf_url,
                "checksum": row.checksum,
                "version": row.version,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        except DBError:
            raise
        except Exception as exc:
            raise DBError(f"Falha ao buscar report {report_id}: {exc}") from exc
