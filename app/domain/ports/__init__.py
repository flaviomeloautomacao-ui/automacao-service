"""Portas (interfaces / protocolos).

Definem contratos que os adaptadores secundários devem implementar
(ex.: repositórios, serviços de storage, LLM, etc.).
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

from app.domain.entities import (
    GeneratedReport,
    MachineRiskRow,
    ReportDraft,
)


# ---------------------------------------------------------------------------
# SpreadsheetParserPort
# ---------------------------------------------------------------------------

@runtime_checkable
class SpreadsheetParserPort(Protocol):
    """Converte bytes de uma planilha em linhas normalizadas de risco."""

    def parse(self, file_bytes: bytes, filename: str) -> list[MachineRiskRow]:
        """Lê os bytes do arquivo e retorna uma lista de linhas normalizadas.

        Args:
            file_bytes: conteúdo cru do arquivo.
            filename: nome original (usado para inferir formato).

        Returns:
            Lista de ``MachineRiskRow`` extraídas da planilha.

        Raises:
            ValidationError: se o formato/conteúdo for inválido.
        """
        ...


# ---------------------------------------------------------------------------
# SpreadsheetValidatorPort
# ---------------------------------------------------------------------------

@runtime_checkable
class SpreadsheetValidatorPort(Protocol):
    """Valida regras de negócio sobre as linhas extraídas da planilha."""

    def validate(self, rows: list[MachineRiskRow]) -> None:
        """Valida a lista de linhas.

        Não retorna nada em caso de sucesso.

        Raises:
            ValidationError: se alguma regra de negócio for violada.
        """
        ...


# ---------------------------------------------------------------------------
# ReportRepositoryPort
# ---------------------------------------------------------------------------

@runtime_checkable
class ReportRepositoryPort(Protocol):
    """Persistência de rascunhos e relatórios gerados."""

    async def save_draft(self, draft: ReportDraft) -> str:
        """Persiste um rascunho e retorna o ID.

        Returns:
            O ``draft.id`` persistido.

        Raises:
            DBError: em caso de falha de persistência.
        """
        ...

    async def save_generated(self, report: GeneratedReport) -> str:
        """Persiste metadados do relatório gerado.

        Returns:
            O ``report.report_id`` persistido.

        Raises:
            DBError: em caso de falha de persistência.
        """
        ...

    async def get_draft(self, draft_id: str) -> Optional[ReportDraft]:
        """Recupera rascunho pelo ID (ou ``None`` se inexistente).

        Raises:
            DBError: em caso de falha de leitura.
        """
        ...

    async def get_generated(self, report_id: str) -> Optional[GeneratedReport]:
        """Recupera relatório gerado pelo ID (ou ``None`` se inexistente).

        Raises:
            DBError: em caso de falha de leitura.
        """
        ...


# ---------------------------------------------------------------------------
# StoragePort
# ---------------------------------------------------------------------------

@runtime_checkable
class StoragePort(Protocol):
    """Abstração de object-storage (S3, GCS, local, etc.)."""

    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Armazena um objeto e retorna a key final.

        Raises:
            StorageError: em caso de falha de upload.
        """
        ...

    async def get(self, key: str) -> bytes:
        """Recupera o conteúdo de um objeto pelo key.

        Raises:
            StorageError: se o objeto não existir ou falhar a leitura.
        """
        ...

    async def signed_url(self, key: str, expires_in: int = 3600) -> str:
        """Gera URL assinada (pré-autenticada) para download.

        Args:
            key: identificador do objeto.
            expires_in: validade da URL em segundos (padrão 1 h).

        Returns:
            URL assinada como string.

        Raises:
            StorageError: se a geração falhar.
        """
        ...


# ---------------------------------------------------------------------------
# LLMPort
# ---------------------------------------------------------------------------

@runtime_checkable
class LLMPort(Protocol):
    """Interface com serviço de LLM (OpenAI, Anthropic, local, etc.)."""

    async def generate_sections(self, context: dict[str, Any]) -> dict[str, str]:
        """Gera seções textuais do laudo a partir do contexto fornecido.

        Args:
            context: dicionário com dados do draft, riscos, normas, etc.

        Returns:
            Mapa ``{nome_secao: conteúdo_html_ou_markdown}``.

        Raises:
            LLMError: em caso de falha de comunicação ou resposta inválida.
        """
        ...


# ---------------------------------------------------------------------------
# PdfRendererPort
# ---------------------------------------------------------------------------

@runtime_checkable
class PdfRendererPort(Protocol):
    """Renderiza HTML + assets em PDF."""

    def render(self, html: str, assets: dict[str, bytes] | None = None) -> bytes:
        """Converte HTML em bytes de PDF.

        Args:
            html: string com o conteúdo HTML completo.
            assets: mapa opcional ``{nome_arquivo: conteúdo}`` de imagens /
                    fontes referenciadas no HTML.

        Returns:
            Bytes do PDF gerado.

        Raises:
            TemplateError: se a renderização falhar.
        """
        ...


# ---------------------------------------------------------------------------
# NormsProviderPort
# ---------------------------------------------------------------------------

@runtime_checkable
class NormsProviderPort(Protocol):
    """Fornece regras / trechos normativos relevantes para o contexto."""

    async def get_rules(self, context: dict[str, Any]) -> dict[str, Any]:
        """Retorna normas aplicáveis dado o contexto de riscos.

        Args:
            context: informações sobre equipamentos, perigos, área, etc.

        Returns:
            Dicionário estruturado com trechos normativos, referências e
            recomendações extraídas de bases normativas (NR-12, ISO 12100…).

        Raises:
            DomainError: se a consulta normativa falhar.
        """
        ...


# ---------------------------------------------------------------------------
# Re-exports
# ---------------------------------------------------------------------------

__all__ = [
    "SpreadsheetParserPort",
    "SpreadsheetValidatorPort",
    "ReportRepositoryPort",
    "StoragePort",
    "LLMPort",
    "PdfRendererPort",
    "NormsProviderPort",
]
