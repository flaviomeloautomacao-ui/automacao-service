"""Serviço de domínio — constrói contextos de classificação de áreas.

Agrupa linhas da planilha de classificação de áreas por equipamento
(tag/identificação) e produz ``AreaClassificationContext`` para cada um.

──────────────────────────────────────────────────────────────────────
 REGRAS DE AGRUPAMENTO
──────────────────────────────────────────────────────────────────────

 1. Chave de agrupamento = ``identificacao`` (tag do equipamento),
    case-insensitive, trimmed.
 2. Ordem de saída = ordem de primeira aparição na planilha.
 3. Cada fonte de liberação distinta do mesmo equipamento gera
    um ``FonteLiberacaoDetail`` separado.
 4. Dados do equipamento (descrição, locação, substância, temp,
    pressão, volume) usam o valor da primeira aparição; campos
    vazios podem ser preenchidos por linhas subsequentes.
 5. Grupo/Classe de temperatura são consolidados da primeira linha
    que tiver valor não-vazio.
──────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from loguru import logger

from app.domain.entities.area_classification import (
    AreaClassificationContext,
    AreaClassificationRow,
    FonteLiberacaoDetail,
    parse_grupo_classe_temp,
    _clean,
    _normalize_disponibilidade,
    _normalize_grau_liberacao,
    _normalize_grau_ventilacao,
    _parse_numeric,
)


# ---------------------------------------------------------------------------
# Mapeamento coluna-letra → campo do AreaClassificationRow
# ---------------------------------------------------------------------------

#: Mapeamento da posição da coluna (0-based) para o campo do modelo.
#: Usado pelo reader de openpyxl para converter a row de células em dict.
COLUMN_INDEX_MAP: dict[int, str] = {
    0: "identificacao",        # A
    1: "descricao",            # B
    2: "locacao",              # C
    3: "substancia",           # D (merged D:E)
    # 4: E — merged com D, ignorar
    5: "temperatura_celsius",  # F
    6: "pressao_kpa",          # G
    7: "volume_m3",            # H
    8: "ventilacao_tipo",      # I
    9: "ventilacao_grau",      # J
    10: "ventilacao_disponibilidade",  # K
    11: "fonte_liberacao_descricao",   # L
    12: "fonte_liberacao_grau",        # M
    13: "grupo_classe_temp_raw",       # N
    14: "zona_0",              # O
    15: "zona_1_m",            # P
    16: "zona_2_m",            # Q
    17: "zona_2_adicional",    # R
    18: "zona_20",             # S
    19: "zona_21_m",           # T
    20: "zona_22_m",           # U
}

#: Linha de início dos dados (1-based) — pula o cabeçalho multi-row (linhas 1-5).
DATA_START_ROW = 6


# ---------------------------------------------------------------------------
# Reader: openpyxl → list[AreaClassificationRow]
# ---------------------------------------------------------------------------

def read_area_classification_rows(
    filepath: str,
    *,
    sheet_name: str | None = None,
    data_start_row: int = DATA_START_ROW,
) -> list[AreaClassificationRow]:
    """Lê uma planilha Excel de classificação de áreas e retorna linhas parseadas.

    Args:
        filepath: Caminho para o arquivo .xlsx.
        sheet_name: Nome da aba. Se ``None``, usa a primeira aba.
        data_start_row: Linha (1-based) onde começam os dados.

    Returns:
        Lista de ``AreaClassificationRow`` validadas.
    """
    import openpyxl

    wb = openpyxl.load_workbook(filepath, data_only=True, read_only=True)
    ws = wb[sheet_name] if sheet_name else wb.active

    rows: list[AreaClassificationRow] = []
    skipped = 0

    for row_idx, row_cells in enumerate(ws.iter_rows(min_row=data_start_row), start=data_start_row):
        raw = _row_to_dict(row_cells, row_idx)
        if raw is None:
            skipped += 1
            continue
        try:
            parsed = _normalize_and_validate(raw, row_idx)
            rows.append(parsed)
        except Exception as exc:
            logger.warning(
                "Linha {} ignorada — erro de validação: {}",
                row_idx, exc,
            )
            skipped += 1

    wb.close()

    logger.info(
        "Planilha de classificação lida | rows_válidas={} | skipped={} | total={}",
        len(rows), skipped, len(rows) + skipped,
    )

    return rows


def _row_to_dict(cells: tuple, row_idx: int) -> dict[str, Any] | None:
    """Converte uma tupla de células openpyxl para um dict.

    Retorna ``None`` se a linha não tem identificação (tag).
    """
    values = [c.value for c in cells]

    # Coluna A (id 0) = identificação — se vazio, pula a linha
    tag = values[0] if len(values) > 0 else None
    if tag is None or str(tag).strip() == "":
        return None

    result: dict[str, Any] = {}
    for col_idx, field_name in COLUMN_INDEX_MAP.items():
        if col_idx < len(values):
            result[field_name] = values[col_idx]
        else:
            result[field_name] = None

    result["row_number"] = row_idx
    return result


def _normalize_and_validate(raw: dict[str, Any], row_idx: int) -> AreaClassificationRow:
    """Normaliza e valida um dict de uma linha da planilha.

    Aplica:
    - Limpeza de strings (trim, colapso de espaços)
    - Parsing do campo Grupo-Classe Temperatura
    - Normalização de enumerados (grau ventilação, disponibilidade, grau liberação)
    - Conversão numérica de zonas
    """
    # Campos de texto simples
    identificacao = _clean(raw.get("identificacao"))
    descricao = _clean(raw.get("descricao"))
    locacao = _clean(raw.get("locacao"))
    substancia = _clean(raw.get("substancia"))

    # Dados de processo
    temp_raw = raw.get("temperatura_celsius")
    temperatura = _parse_numeric(str(temp_raw)) if temp_raw is not None else None

    pressao = _clean(str(raw.get("pressao_kpa") or "")) or None
    volume = _clean(str(raw.get("volume_m3") or "")) or None

    # Ventilação
    ventilacao_tipo = _clean(raw.get("ventilacao_tipo")) or "Natural"
    ventilacao_grau = _normalize_grau_ventilacao(
        _clean(raw.get("ventilacao_grau")) or "Baixo"
    )
    ventilacao_disponibilidade = _normalize_disponibilidade(
        _clean(raw.get("ventilacao_disponibilidade")) or "Satisfatória"
    )

    # Fonte de liberação
    fonte_desc = _clean(raw.get("fonte_liberacao_descricao")) or "Não especificado"
    fonte_grau = _normalize_grau_liberacao(
        _clean(raw.get("fonte_liberacao_grau")) or "Secundária"
    )

    # Grupo e Classe de Temperatura
    grupo_classe_raw = _clean(raw.get("grupo_classe_temp_raw"))
    classe_temp, grupo = parse_grupo_classe_temp(grupo_classe_raw)

    # Zonas — texto bruto preservado, numéricas parseadas
    zona_0_raw = _clean(str(raw.get("zona_0") or ""))
    zona_1_raw = raw.get("zona_1_m")
    zona_2_raw = raw.get("zona_2_m")
    zona_2_adic_raw = raw.get("zona_2_adicional")
    zona_20_raw = _clean(str(raw.get("zona_20") or ""))
    zona_21_raw_val = raw.get("zona_21_m")
    zona_22_raw_val = raw.get("zona_22_m")

    return AreaClassificationRow(
        identificacao=identificacao,
        descricao=descricao,
        locacao=locacao,
        substancia=substancia,
        temperatura_celsius=temperatura,
        pressao_kpa=pressao,
        volume_m3=volume,
        ventilacao_tipo=ventilacao_tipo,
        ventilacao_grau=ventilacao_grau,
        ventilacao_disponibilidade=ventilacao_disponibilidade,
        fonte_liberacao_descricao=fonte_desc,
        fonte_liberacao_grau=fonte_grau,
        classe_temperatura=classe_temp,
        grupo=grupo,
        grupo_classe_temp_raw=grupo_classe_raw,
        zona_0=zona_0_raw or None,
        zona_1_m=_parse_numeric(str(zona_1_raw)) if zona_1_raw is not None else None,
        zona_2_m=_parse_numeric(str(zona_2_raw)) if zona_2_raw is not None else None,
        zona_2_adicional=_clean(str(zona_2_adic_raw)) if zona_2_adic_raw else None,
        zona_20=zona_20_raw or None,
        zona_21_m=_parse_numeric(str(zona_21_raw_val)) if zona_21_raw_val is not None else None,
        zona_22_m=_parse_numeric(str(zona_22_raw_val)) if zona_22_raw_val is not None else None,
        zona_21_raw=_clean(str(zona_21_raw_val)) if zona_21_raw_val else None,
        zona_22_raw=_clean(str(zona_22_raw_val)) if zona_22_raw_val else None,
        row_number=raw.get("row_number", 0),
    )


# ---------------------------------------------------------------------------
# Builder: list[AreaClassificationRow] → list[AreaClassificationContext]
# ---------------------------------------------------------------------------

def build_area_classification_contexts(
    rows: list[AreaClassificationRow],
) -> list[AreaClassificationContext]:
    """Agrupa linhas por equipamento e produz contextos consolidados.

    Args:
        rows: Linhas parseadas da planilha.

    Returns:
        Lista de ``AreaClassificationContext``, um por equipamento,
        na ordem de primeira aparição. Campo ``index`` sequencial 1-based.

    Raises:
        ValueError: Se ``rows`` estiver vazia.
    """
    if not rows:
        raise ValueError("rows não pode estar vazio")

    groups: OrderedDict[str, _AreaAccumulator] = OrderedDict()

    for row in rows:
        key = row.identificacao.strip().lower()

        if key not in groups:
            groups[key] = _AreaAccumulator(row)
        else:
            groups[key].absorb(row)

    contexts: list[AreaClassificationContext] = []
    for idx, (_, acc) in enumerate(groups.items(), start=1):
        contexts.append(acc.to_context(index=idx))

    logger.info(
        "AreaClassificationContexts construídos | total_rows={} | equipamentos={}",
        len(rows), len(contexts),
    )

    return contexts


# ---------------------------------------------------------------------------
# Acumulador interno
# ---------------------------------------------------------------------------

class _AreaAccumulator:
    """Acumula dados de várias fontes de liberação de um mesmo equipamento."""

    __slots__ = (
        "identificacao",
        "descricao",
        "locacao",
        "substancia",
        "temperatura_celsius",
        "pressao_kpa",
        "volume_m3",
        "classe_temperatura",
        "grupo",
        "fontes",
        "row_count",
    )

    def __init__(self, first_row: AreaClassificationRow) -> None:
        self.identificacao = first_row.identificacao
        self.descricao = first_row.descricao
        self.locacao = first_row.locacao
        self.substancia = first_row.substancia
        self.temperatura_celsius = first_row.temperatura_celsius
        self.pressao_kpa = first_row.pressao_kpa
        self.volume_m3 = first_row.volume_m3
        self.classe_temperatura = first_row.classe_temperatura
        self.grupo = first_row.grupo
        self.fontes: list[FonteLiberacaoDetail] = [_to_fonte_detail(first_row)]
        self.row_count = 1

    def absorb(self, row: AreaClassificationRow) -> None:
        """Absorve mais uma linha (fonte de liberação) do mesmo equipamento."""
        self.row_count += 1

        # Preenche campos vazios do equipamento (fill-forward)
        if not self.descricao and row.descricao:
            self.descricao = row.descricao
        if not self.locacao and row.locacao:
            self.locacao = row.locacao
        if not self.substancia and row.substancia:
            self.substancia = row.substancia
        if self.temperatura_celsius is None and row.temperatura_celsius is not None:
            self.temperatura_celsius = row.temperatura_celsius
        if not self.pressao_kpa and row.pressao_kpa:
            self.pressao_kpa = row.pressao_kpa
        if not self.volume_m3 and row.volume_m3:
            self.volume_m3 = row.volume_m3
        if not self.classe_temperatura and row.classe_temperatura:
            self.classe_temperatura = row.classe_temperatura
        if not self.grupo and row.grupo:
            self.grupo = row.grupo

        self.fontes.append(_to_fonte_detail(row))

    def to_context(self, *, index: int) -> AreaClassificationContext:
        """Converte o acumulador em ``AreaClassificationContext`` imutável."""
        return AreaClassificationContext(
            index=index,
            identificacao=self.identificacao,
            descricao=self.descricao,
            locacao=self.locacao,
            substancia=self.substancia,
            temperatura_celsius=self.temperatura_celsius,
            pressao_kpa=self.pressao_kpa,
            volume_m3=self.volume_m3,
            classe_temperatura=self.classe_temperatura,
            grupo=self.grupo,
            fontes_liberacao=list(self.fontes),
            row_count=self.row_count,
        )


def _to_fonte_detail(row: AreaClassificationRow) -> FonteLiberacaoDetail:
    """Cria um ``FonteLiberacaoDetail`` a partir de uma row."""
    return FonteLiberacaoDetail(
        descricao=row.fonte_liberacao_descricao,
        grau=row.fonte_liberacao_grau,
        ventilacao_grau=row.ventilacao_grau,
        ventilacao_disponibilidade=row.ventilacao_disponibilidade,
        zona_0=row.zona_0,
        zona_1_m=row.zona_1_m,
        zona_2_m=row.zona_2_m,
        zona_2_adicional=row.zona_2_adicional,
        zona_20=row.zona_20,
        zona_21_m=row.zona_21_m,
        zona_22_m=row.zona_22_m,
        zona_21_raw=row.zona_21_raw,
        zona_22_raw=row.zona_22_raw,
    )


# ---------------------------------------------------------------------------
# Atalho: filepath → contexts (pipeline-ready)
# ---------------------------------------------------------------------------

def read_and_build_area_contexts(
    filepath: str,
    *,
    sheet_name: str | None = None,
) -> list[AreaClassificationContext]:
    """Lê planilha e retorna contextos prontos para o pipeline.

    Combina ``read_area_classification_rows`` + ``build_area_classification_contexts``.
    """
    rows = read_area_classification_rows(filepath, sheet_name=sheet_name)
    return build_area_classification_contexts(rows)
