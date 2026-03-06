"""Configuração da aplicação.

Carregamento de variáveis de ambiente, settings (Pydantic BaseSettings)
e constantes globais do projeto.

Exemplo de uso::

    from app.infrastructure.config import get_settings

    settings = get_settings()
    print(settings.DATABASE_URL)
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações centrais do projeto.

    Valores são lidos automaticamente de variáveis de ambiente
    ou de um arquivo ``.env`` na raiz do projeto.

    Attributes:
        ENV: Ambiente de execução (development, staging, production).
        API_PORT: Porta em que a API FastAPI será servida.
        DATABASE_URL: String de conexão com o banco de dados.
        SUPABASE_URL: URL do projeto Supabase.
        SUPABASE_SERVICE_ROLE_KEY: Chave service-role do Supabase.
        SUPABASE_BUCKET: Nome do bucket de storage no Supabase.
        OPENROUTER_API_KEY: Chave de API do OpenRouter.
        OPENROUTER_BASE_URL: URL base da API do OpenRouter.
        LLM_MODEL: Identificador do modelo LLM a ser utilizado.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Ambiente ────────────────────────────────────────────────
    ENV: Literal["development", "staging", "production"] = "development"
    API_PORT: int = 8000

    # ── Banco de dados ──────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/automacao"

    # ── Supabase ────────────────────────────────────────────────
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_BUCKET: str = "reports"

    # ── LLM / OpenRouter ────────────────────────────────────────
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    LLM_MODEL: str = "openai/gpt-4o"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna a instância singleton de Settings (cacheada via lru_cache).

    Returns:
        Settings: Objeto com todas as configurações carregadas.

    Example::

        settings = get_settings()
        assert settings.ENV in ("development", "staging", "production")
    """
    return Settings()
