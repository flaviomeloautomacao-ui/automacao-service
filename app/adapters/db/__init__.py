"""Adaptador de banco de dados.

Implementa repositórios e acesso a dados persistentes.
"""

from app.adapters.db.models import Base, GeneratedReport, ReportDraft, Upload
from app.adapters.db.repository import ReportRepository

__all__ = [
    "Base",
    "GeneratedReport",
    "ReportDraft",
    "ReportRepository",
    "Upload",
]
