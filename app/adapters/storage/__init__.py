"""Adaptador de storage (armazenamento de arquivos).

Implementa operações de leitura/escrita no Supabase Storage via REST API.
"""

from app.adapters.storage.paths import (  # noqa: F401
    report_pdf_path,
    upload_clone_path,
    upload_original_path,
)
from app.adapters.storage.supabase_storage import SupabaseStorage  # noqa: F401

__all__ = [
    "SupabaseStorage",
    "upload_original_path",
    "upload_clone_path",
    "report_pdf_path",
]
