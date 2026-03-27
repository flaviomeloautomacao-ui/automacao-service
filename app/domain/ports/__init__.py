"""Portas (interfaces / protocolos).

Definem contratos que os adaptadores secundários devem implementar
(ex.: repositórios, serviços de storage, LLM, etc.).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Protocol, runtime_checkable

from app.domain.entities import (
    MachineRiskRow,
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
    """Persistência de uploads, rascunhos e relatórios gerados."""

    async def create_upload(
        self,
        *,
        filename: str,
        content_type: str,
        size_bytes: int,
        storage_path: str,
        expires_at: "datetime | None" = None,
    ) -> str:
        """Persiste um registro de upload e retorna o UUID.

        Args:
            filename: Nome original do arquivo.
            content_type: MIME type.
            size_bytes: Tamanho em bytes.
            storage_path: Caminho no object-storage.
            expires_at: Data/hora de expiração (UTC). ``None`` = sem expiração.

        Returns:
            UUID do upload como string.

        Raises:
            DBError: em caso de falha de persistência.
        """
        ...

    async def create_draft(
        self,
        *,
        upload_id: str,
        metadata: dict[str, Any] | None = None,
        rows_json: list[dict[str, Any]] | None = None,
    ) -> str:
        """Persiste um rascunho de laudo e retorna o UUID.

        Returns:
            UUID do draft como string.

        Raises:
            DBError: em caso de falha de persistência.
        """
        ...

    async def create_generated(
        self,
        *,
        draft_id: str,
        pdf_storage_path: str,
        pdf_url: str | None = None,
        checksum: str,
        version: int = 1,
        expires_at: "datetime | None" = None,
    ) -> str:
        """Persiste metadados do relatório gerado e retorna o UUID.

        Args:
            draft_id: UUID do draft de origem.
            pdf_storage_path: Caminho no storage.
            pdf_url: URL pública / assinada (opcional).
            checksum: SHA-256 do PDF.
            version: Versão do laudo.
            expires_at: Data/hora de expiração (UTC). ``None`` = sem expiração.

        Returns:
            UUID do relatório gerado como string.

        Raises:
            DBError: em caso de falha de persistência.
        """
        ...

    async def get_draft(self, draft_id: str) -> Optional[dict[str, Any]]:
        """Recupera rascunho pelo ID (ou ``None`` se inexistente).

        Raises:
            DBError: em caso de falha de leitura.
        """
        ...

    async def get_generated(self, report_id: str) -> Optional[dict[str, Any]]:
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
    """Abstração de object-storage (S3, GCS, Supabase Storage, etc.)."""

    async def put_bytes(
        self,
        bucket: str,
        path: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Armazena bytes no storage e retorna o path final.

        Args:
            bucket: nome do bucket.
            path: caminho/chave do objeto dentro do bucket.
            data: conteúdo cru a armazenar.
            content_type: MIME type do conteúdo.
            metadata: metadados personalizados opcionais.

        Returns:
            Path do objeto armazenado.

        Raises:
            StorageError: em caso de falha de upload.
        """
        ...

    async def get_signed_url(
        self,
        bucket: str,
        path: str,
        expires_seconds: int = 3600,
    ) -> str:
        """Gera URL assinada (pré-autenticada) para download.

        Args:
            bucket: nome do bucket.
            path: caminho/chave do objeto dentro do bucket.
            expires_seconds: validade da URL em segundos (padrão 1 h).

        Returns:
            URL assinada como string.

        Raises:
            StorageError: se a geração falhar.
        """
        ...

    async def delete(self, bucket: str, paths: list[str]) -> None:
        """Remove um ou mais objetos do storage.

        Args:
            bucket: nome do bucket.
            paths: lista de caminhos a remover.

        Raises:
            StorageError: em caso de falha de remoção.
        """
        ...


# ---------------------------------------------------------------------------
# LLMPort
# ---------------------------------------------------------------------------

@runtime_checkable
class LLMPort(Protocol):
    """Interface com serviço de LLM (OpenAI, Anthropic, local, etc.)."""

    async def generate_sections(self, context: dict[str, Any]) -> dict[str, Any]:
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
    "LLMCostRepositoryPort",
    "BudgetGuardPort",
]


# ---------------------------------------------------------------------------
# LLMCostRepositoryPort
# ---------------------------------------------------------------------------

@runtime_checkable
class LLMCostRepositoryPort(Protocol):
    """Persistência de registros de custo LLM no banco de dados."""

    async def save_batch(
        self,
        records: list[Any],
        job_id: str,
    ) -> int:
        """Insere registros de uso LLM em batch.

        Returns:
            Número de registros inseridos.
        """
        ...

    async def update_job_cost_summary(
        self,
        job_id: str,
        total_cost_usd: float,
        total_tokens: int,
        call_count: int,
    ) -> None:
        """Atualiza campos pré-agregados de custo no Job."""
        ...


# ---------------------------------------------------------------------------
# BudgetGuardPort
# ---------------------------------------------------------------------------

@runtime_checkable
class BudgetGuardPort(Protocol):
    """Proteção contra gastos LLM descontrolados."""

    def check_job_budget(
        self,
        current_cost: float,
        current_calls: int,
        job_id: str,
    ) -> None:
        """Verifica limites de custo por job."""
        ...
