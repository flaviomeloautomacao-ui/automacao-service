"""Exceções e erros de domínio.

Classes de erro específicas do domínio para comunicação clara
de falhas entre camadas sem acoplar a detalhes de infraestrutura.
"""

from __future__ import annotations


class DomainError(Exception):
    """Classe-base para todas as exceções de domínio."""

    def __init__(self, message: str = "", *, detail: str | None = None) -> None:
        self.detail = detail or message
        super().__init__(message)


class ValidationError(DomainError):
    """Dados de entrada inválidos (planilha, campos obrigatórios, formatos)."""


class DBError(DomainError):
    """Falha em operação de banco de dados (persistência / leitura)."""


class StorageError(DomainError):
    """Falha em operação de object-storage (upload / download / URL)."""


class LLMError(DomainError):
    """Falha ao interagir com o serviço de LLM (timeout, token, etc.)."""


class TemplateError(DomainError):
    """Falha na renderização de template (Jinja2 / HTML / PDF)."""
