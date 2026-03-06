"""Convenções de caminhos (paths) no object-storage.

Centraliza a geração de keys para uploads e relatórios,
garantindo consistência em todo o projeto.

Padrões:

* ``uploads/{upload_id}/{filename}``
* ``uploads/{upload_id}/clone_{YYYYMMDD}_{filename}``
* ``{report_id}/report_v{version}.pdf``
"""

from __future__ import annotations

from datetime import datetime, timezone


def upload_original_path(upload_id: str, filename: str) -> str:
    """Gera o path para o arquivo original de upload.

    Args:
        upload_id: UUID do upload.
        filename: nome original do arquivo enviado.

    Returns:
        Path no formato ``uploads/{upload_id}/{filename}``.

    Example::

        >>> upload_original_path("abc-123", "planilha.xlsx")
        'uploads/abc-123/planilha.xlsx'
    """
    return f"uploads/{upload_id}/{filename}"


def upload_clone_path(upload_id: str, filename: str, date: datetime | None = None) -> str:
    """Gera o path para uma cópia (clone) do arquivo de upload.

    Args:
        upload_id: UUID do upload.
        filename: nome original do arquivo enviado.
        date: data para compor o prefixo; usa ``utcnow`` se omitido.

    Returns:
        Path no formato ``uploads/{upload_id}/clone_{YYYYMMDD}_{filename}``.

    Example::

        >>> from datetime import datetime
        >>> upload_clone_path("abc-123", "planilha.xlsx", datetime(2026, 3, 5))
        'uploads/abc-123/clone_20260305_planilha.xlsx'
    """
    if date is None:
        date = datetime.now(timezone.utc)
    date_str = date.strftime("%Y%m%d")
    return f"uploads/{upload_id}/clone_{date_str}_{filename}"


def report_pdf_path(report_id: str, version: int = 1) -> str:
    """Gera o path para o PDF de um relatório gerado.

    Args:
        report_id: UUID do relatório gerado.
        version: número da versão do laudo.

    Returns:
        Path no formato ``{report_id}/report_v{version}.pdf``.

    Example::

        >>> report_pdf_path("def-456", version=2)
        'def-456/report_v2.pdf'
    """
    return f"{report_id}/report_v{version}.pdf"
