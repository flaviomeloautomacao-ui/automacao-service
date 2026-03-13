"""Adaptador de banco de dados.

Implementa repositórios e acesso a dados persistentes.
"""

from app.adapters.db.models import Base, GeneratedReport, ReportDraft, Upload
from app.adapters.db.repository import ReportRepository
from app.adapters.db.job_models import (
    EquipmentImageModel,
    Job,
    JobStep,
    ReportEquipmentModel,
    ReportModel,
    SpreadsheetRowModel,
    SpreadsheetUploadModel,
)
from app.adapters.db.job_repository import JobRepository

__all__ = [
    "Base",
    "EquipmentImageModel",
    "GeneratedReport",
    "Job",
    "JobRepository",
    "JobStep",
    "ReportDraft",
    "ReportEquipmentModel",
    "ReportModel",
    "ReportRepository",
    "SpreadsheetRowModel",
    "SpreadsheetUploadModel",
    "Upload",
]
