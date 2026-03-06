"""Script de debug para testar o parser com uma planilha real.

Uso::

    python -m app.scripts.debug_parse caminho/para/planilha.xlsx

Imprime:
  - Linha do cabeçalho detectada
  - Colunas detectadas
  - Número de linhas válidas
  - Primeiras duas linhas parseadas (fields + valores)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Garante que o diretório raiz do projeto esteja no sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.adapters.spreadsheet.parser import PandasSpreadsheetParser  # noqa: E402
from app.domain.errors import ValidationError  # noqa: E402


def main() -> None:
    """Executa o parser sobre o arquivo informado e imprime informações de debug."""
    if len(sys.argv) < 2:
        print("Uso: python -m app.scripts.debug_parse <caminho_planilha>")
        sys.exit(1)

    filepath = Path(sys.argv[1])
    if not filepath.exists():
        print(f"Arquivo não encontrado: {filepath}")
        sys.exit(1)

    file_bytes = filepath.read_bytes()
    filename = filepath.name

    print(f"\n{'=' * 60}")
    print(f"  Arquivo: {filepath}")
    print(f"  Tamanho: {len(file_bytes):,} bytes")
    print(f"{'=' * 60}\n")

    parser = PandasSpreadsheetParser()

    try:
        rows = parser.parse(file_bytes, filename)
    except ValidationError as exc:
        print(f"[ERRO DE VALIDAÇÃO] {exc}")
        if hasattr(exc, "errors") and exc.errors:
            for err in exc.errors:
                print(f"  - {err}")
        sys.exit(1)
    except Exception as exc:
        print(f"[ERRO INESPERADO] {type(exc).__name__}: {exc}")
        sys.exit(1)

    print(f"Número de linhas válidas: {len(rows)}")
    print()

    # Mostrar primeiras 2 linhas
    for i, row in enumerate(rows[:2]):
        print(f"--- Linha {i + 1} ---")
        for field_name, field_info in row.model_fields.items():
            value = getattr(row, field_name)
            display = repr(value) if value is not None else "None"
            # Truncar valores longos para leitura no terminal
            if isinstance(value, str) and len(value) > 100:
                display = repr(value[:100] + "…")
            print(f"  {field_name:25s} = {display}")
        print()

    if len(rows) > 2:
        print(f"... e mais {len(rows) - 2} linha(s).")


if __name__ == "__main__":
    main()
