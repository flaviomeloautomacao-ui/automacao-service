"""Cria todas as tabelas no banco de dados (ambiente de desenvolvimento).

Uso::

    python -m app.scripts.init_db

NÃO utilizar em produção — em produção prefira migrations (Alembic).
"""

from __future__ import annotations

import asyncio
import sys

from app.adapters.db.models import Base
from app.infrastructure.config import get_settings
from app.infrastructure.db import get_engine


async def _create_tables() -> None:
    """Cria todas as tabelas definidas em ``Base.metadata``."""
    settings = get_settings()
    print(f"[init_db] ENV={settings.ENV}")
    print(f"[init_db] DATABASE_URL={settings.DATABASE_URL}")

    engine = get_engine()

    async with engine.begin() as conn:
        print("[init_db] Criando tabelas...")
        await conn.run_sync(Base.metadata.create_all)
        print("[init_db] Tabelas criadas com sucesso!")

    await engine.dispose()


def main() -> None:
    """Entry-point síncrono."""
    settings = get_settings()
    if settings.ENV == "production":
        print("[init_db] ERRO: Não execute este script em produção. Use Alembic.")
        sys.exit(1)

    asyncio.run(_create_tables())


if __name__ == "__main__":
    main()
