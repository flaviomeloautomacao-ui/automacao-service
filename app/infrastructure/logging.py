"""Configuração de logging.

Setup de loggers, formatação e nível de log para toda a aplicação.
Usa `loguru <https://github.com/Delgan/loguru>`_ como backend.

O nível de log é definido pelo ``ENV``:
- **development** → DEBUG
- **staging** → INFO
- **production** → WARNING

Exemplo de uso::

    from app.infrastructure.logging import setup_logging

    logger = setup_logging()       # configura e devolve o logger
    logger.info("Servidor iniciado na porta {}", 8000)
"""

import sys
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from loguru import Logger

# Mapeamento ENV → nível de log
_ENV_LOG_LEVEL: dict[str, str] = {
    "development": "DEBUG",
    "staging": "INFO",
    "production": "WARNING",
}

# Formato padrão: timestamp | level | module:function:line | message
_LOG_FORMAT: str = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{module}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<level>{message}</level>"
)


def setup_logging(env: str = "development") -> "Logger":
    """Configura o loguru com nível e formato adequados ao ambiente.

    Remove handlers padrão e adiciona um handler para ``stderr``
    com o formato padronizado do projeto.

    Args:
        env: Ambiente atual (``development``, ``staging`` ou ``production``).

    Returns:
        Logger: Instância global do ``loguru.logger`` já configurada.

    Example::

        logger = setup_logging("production")
        logger.warning("Algo precisa de atenção")
    """
    level = _ENV_LOG_LEVEL.get(env, "INFO")

    # Remove todos os handlers existentes para evitar duplicatas
    logger.remove()

    # Handler principal → stderr com cores
    logger.add(
        sys.stderr,
        level=level,
        format=_LOG_FORMAT,
        colorize=True,
        backtrace=True,
        diagnose=(env == "development"),
    )

    logger.info("Logging configurado — env={}, level={}", env, level)
    return logger
