"""Validação determinística de linhas da planilha de riscos.

Este adaptador implementa ``SpreadsheetValidatorPort`` e aplica regras
puramente determinísticas — nenhuma chamada a LLM é feita aqui.
"""

from __future__ import annotations

from typing import Any

from app.domain.entities import MachineRiskRow
from app.domain.errors import ValidationError


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Campos obrigatórios que não podem ser strings vazias / somente espaços.
REQUIRED_FIELDS: tuple[str, ...] = (
    "equipamento",
    "perigo",
    "causas",
    "consequencias",
    "categoria_severidade",
    "categoria_probabilidade",
    "classificacao_risco",
)


# ---------------------------------------------------------------------------
# Validador
# ---------------------------------------------------------------------------

class BasicSpreadsheetValidator:
    """Implementação concreta de ``SpreadsheetValidatorPort``.

    Aplica validações determinísticas sobre as linhas extraídas da planilha.
    """

    # ------------------------------------------------------------------
    # Validações auxiliares (internas)
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_required_fields(
        row: MachineRiskRow,
        row_index: int,
        errors: list[dict[str, Any]],
    ) -> None:
        """Verifica se os campos obrigatórios não estão vazios."""
        for field_name in REQUIRED_FIELDS:
            value = getattr(row, field_name, None)

            if value is None or (isinstance(value, str) and not value.strip()):
                errors.append({
                    "row": row_index + 1,
                    "column": field_name,
                    "message": f"Campo obrigatório '{field_name}' está vazio.",
                })

    # ------------------------------------------------------------------
    # Método público (contrato do port)
    # ------------------------------------------------------------------

    def validate(self, rows: list[MachineRiskRow]) -> None:
        """Valida a lista de linhas de risco.

        Args:
            rows: linhas já parseadas da planilha.

        Raises:
            ValidationError: se a lista estiver vazia ou alguma linha
                             violar regras de negócio.  A exceção carrega
                             atributo ``errors`` com detalhes estruturados.
        """
        if not rows:
            raise ValidationError(
                "A planilha não contém nenhuma linha de dados.",
                errors=[{
                    "row": 0,
                    "column": "*",
                    "message": "Lista de linhas vazia.",
                }],
            )

        errors: list[dict[str, Any]] = []

        for idx, row in enumerate(rows):
            self._validate_required_fields(row, idx, errors)

        if errors:
            raise ValidationError(
                f"Validação da planilha falhou com {len(errors)} erro(s).",
                errors=errors,
            )
