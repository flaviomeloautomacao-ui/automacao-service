"""Validação determinística de linhas da planilha de riscos.

Este adaptador implementa ``SpreadsheetValidatorPort`` e aplica regras
puramente determinísticas — nenhuma chamada a LLM é feita aqui.
"""

from __future__ import annotations

import re
from typing import Any

from app.domain.entities import MachineRiskRow, RiskLevel
from app.domain.errors import ValidationError


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Campos obrigatórios que não podem ser strings vazias / somente espaços.
REQUIRED_FIELDS: tuple[str, ...] = (
    "equipamento",
    "perigo",
    "causa",
    "consequencia",
    "risco",
)

#: Conjunto de valores válidos para ``risco`` (case-insensitive).
ALLOWED_RISK_VALUES: set[str] = {level.value for level in RiskLevel}

#: Padrão mínimo para referências normativas.
#  Aceita siglas comuns (ABNT, NBR, NR, ISO, IEC, EN) seguidas opcionalmente
#  de separador e números.  O objetivo é barrar textos claramente não-normativos
#  sem ser excessivamente restritivo.
_NORMA_REF_PATTERN: re.Pattern[str] = re.compile(
    r"(?i)\b(ABNT|NBR|NR|ISO|IEC|EN)\b",
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

            # Para RiskLevel (enum), o valor textual é ``value.value``
            if isinstance(value, RiskLevel):
                raw = value.value
            else:
                raw = value

            if raw is None or (isinstance(raw, str) and not raw.strip()):
                errors.append({
                    "row_index": row_index,
                    "field": field_name,
                    "message": f"Campo obrigatório '{field_name}' está vazio.",
                })

    @staticmethod
    def _validate_risk_value(
        row: MachineRiskRow,
        row_index: int,
        errors: list[dict[str, Any]],
    ) -> None:
        """Verifica se o nível de risco pertence ao conjunto permitido."""
        risk_raw: str = row.risco.value if isinstance(row.risco, RiskLevel) else str(row.risco)
        if risk_raw.strip().lower() not in ALLOWED_RISK_VALUES:
            errors.append({
                "row_index": row_index,
                "field": "risco",
                "message": (
                    f"Valor de risco '{risk_raw}' não é permitido. "
                    f"Valores aceitos: {sorted(ALLOWED_RISK_VALUES)}."
                ),
            })

    @staticmethod
    def _validate_norma_ref(
        row: MachineRiskRow,
        row_index: int,
        errors: list[dict[str, Any]],
    ) -> None:
        """Se ``norma_ref`` estiver preenchido, verifica padrão mínimo."""
        if row.norma_ref is None:
            return

        norma = row.norma_ref.strip()
        if not norma:
            # Vazio após strip — tudo bem, considere como ausente.
            return

        if not _NORMA_REF_PATTERN.search(norma):
            errors.append({
                "row_index": row_index,
                "field": "norma_ref",
                "message": (
                    f"Referência normativa '{norma}' não contém sigla reconhecida "
                    "(ABNT, NBR, NR, ISO, IEC, EN)."
                ),
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
                    "row_index": -1,
                    "field": "__all__",
                    "message": "Lista de linhas vazia.",
                }],
            )

        errors: list[dict[str, Any]] = []

        for idx, row in enumerate(rows):
            self._validate_required_fields(row, idx, errors)
            self._validate_risk_value(row, idx, errors)
            self._validate_norma_ref(row, idx, errors)

        if errors:
            raise ValidationError(
                f"Validação da planilha falhou com {len(errors)} erro(s).",
                errors=errors,
            )
