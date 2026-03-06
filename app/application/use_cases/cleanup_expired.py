"""Caso de uso: limpeza de arquivos expirados no storage.

Este módulo é um **placeholder** — a lógica completa será implementada
quando o fluxo de expiração estiver mais maduro.

Responsabilidades futuras:

1. Consultar ``uploads`` e ``generated_reports`` cujo ``expires_at < now()``.
2. Para cada registro expirado, remover o arquivo correspondente do
   object-storage via ``StoragePort.delete``.
3. Atualizar ou remover os registros no banco de dados.

A expiração **não** é feita automaticamente pelo storage — é controlada
pelo serviço via este use case (rodado por cron / scheduler).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.domain.ports import ReportRepositoryPort, StoragePort


class CleanupExpiredUseCase:
    """Remove arquivos expirados do storage e atualiza o banco.

    Attributes:
        storage: adaptador de object-storage.
        repository: repositório de dados (uploads / relatórios).
        bucket: nome do bucket padrão.
    """

    def __init__(
        self,
        *,
        storage: "StoragePort",
        repository: "ReportRepositoryPort",
        bucket: str,
    ) -> None:
        self._storage = storage
        self._repository = repository
        self._bucket = bucket

    async def execute(self) -> dict[str, Any]:
        """Executa a limpeza de arquivos expirados.

        Returns:
            Dicionário com estatísticas da execução::

                {
                    "checked_at": "2026-03-05T12:00:00Z",
                    "uploads_removed": 0,
                    "reports_removed": 0,
                }

        TODO:
            - Consultar uploads com ``expires_at < now()``.
            - Consultar generated_reports com ``expires_at < now()``.
            - Chamar ``self._storage.delete(...)`` para cada path.
            - Remover / marcar registros no banco.
        """
        now = datetime.now(timezone.utc)

        # Placeholder — nenhuma operação real ainda
        return {
            "checked_at": now.isoformat(),
            "uploads_removed": 0,
            "reports_removed": 0,
        }
