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
        LLM_MODEL: Identificador do modelo LLM padrão (fallback geral).
        LLM_MODEL_GLOBAL: Modelo para seções globais (CP-01).
        LLM_MODEL_PER_EQUIPMENT: Modelo para equipamentos risco médio/baixo (CP-02).
        LLM_MODEL_PER_EQUIPMENT_HIGH: Modelo para equipamentos risco alto (CP-02).
        LLM_MODEL_FALLBACK: Modelo de fallback se o primário falhar.
        LLM_HIGH_RISK_KEYWORDS: Palavras-chave (vírgula-separadas) que indicam risco alto.
        LLM_TIERED_ROUTING_ENABLED: Habilita roteamento por risco (False = modelo único).
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
    LLM_MODEL: str = "openai/gpt-4.1-mini"

    # ── Roteamento multi-modelo (tiered) ────────────────────────
    LLM_MODEL_GLOBAL: str = "openai/gpt-4.1-mini"
    LLM_MODEL_PER_EQUIPMENT: str = "openai/gpt-4.1-mini"
    LLM_MODEL_PER_EQUIPMENT_HIGH: str = "openai/gpt-4.1"
    LLM_MODEL_FALLBACK: str = "openai/gpt-4.1-mini"
    LLM_HIGH_RISK_KEYWORDS: str = "muito alto,intolerável,substancial"
    LLM_TIERED_ROUTING_ENABLED: bool = True

    # ── Parâmetros de geração LLM ───────────────────────────────
    LLM_TEMPERATURE: float = 0.15
    LLM_TOP_P: float = 0.85

    # ── RAG / Embedding (normas ABNT) ───────────────────────────
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_BASE_URL: str = "https://api.openai.com/v1"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    RAG_ENABLED: bool = True
    RAG_TOP_K: int = 8
    RAG_MAX_CHUNKS: int = 5
    RAG_MIN_SCORE: float = 0.35
    RAG_NORM_TABLE: str = "konis_db"
    RAG_NORM_TABLE_DHA: str = "konis_db_DHA"
    RAG_NORM_TABLE_AREAS: str = "konis_db_ClassificacaoDeAreas"

    # ── Dev / Teste ─────────────────────────────────────────────
    DEVLLM: bool = False
    LLM_MOCK_ENABLED: bool = False
    DEV_MAX_EQUIPMENTS: int = 0   # 0 = sem limite
    DEV_SKIP_PDF: bool = False

    # ── Segurança ───────────────────────────────────────────────
    INTERNAL_API_KEY: str = ""

    # ── Budget / Limites LLM ────────────────────────────────────
    LLM_MAX_COST_PER_JOB_USD: float = 2.00
    LLM_MAX_COST_PER_DAY_USD: float = 50.00
    LLM_MAX_CALLS_PER_JOB: int = 100


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
