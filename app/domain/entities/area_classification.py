"""Entidades de domínio — Classificação de Áreas (IEC 60079-10-1/10-2).

Modelos Pydantic que representam os dados da planilha de classificação
de áreas com atmosferas explosivas. Cada linha da planilha-modelo mapeia
para um ``AreaClassificationRow``; múltiplas linhas do mesmo equipamento
(com diferentes fontes de liberação) são agrupadas pelo builder.

──────────────────────────────────────────────────────────────────────
 ESTRUTURA DA PLANILHA DE REFERÊNCIA (21 colunas, A–U)
──────────────────────────────────────────────────────────────────────

 Layout do cabeçalho (multi-row, linhas 1–5):

   Row 1:  A1 = "TABELA ANEXO A"  |  C1 = título
   Row 2:  A2 = "EQUIPAMENTO DE PROCESSO"
           D2 = "Substância Combustível" (merged D:E)
           F2 = "Dados de Processo" (merged F:H)
           I2 = "Grau de Ventilação"
           L2 = "Fonte de Liberação"
           N2 = "Grupo e Classe de Temperatura (Grupo-T)"
           O2 = "Limite da Zona Distância Horizontal/Vertical (m)"
   Row 3:  F3 = "Temp."  |  G3 = "Pressão (kPa)"  |  H3 = "Volume"
   Row 5:  Sub-headers: A=Identificação, B=Descrição, C=Locação,
           F=(°C), H=(m³), I=Tipo, J=Grau, K=Disponibilidade,
           L=Descrição, M=Grau,
           O=Zona 0, P=Zona 1(m), Q=Zona 2(m), R=Zona 2 adicional(m),
           S=Zona 20, T=Zona 21(m), U=Zona 22(m)
   Row 6+: Dados

 Colunas (mapeamento posicional por letra):
   A = Identificação (tag do equipamento)
   B = Descrição do equipamento
   C = Locação (área/setor da planta)
   D = Substância Combustível (merged D:E)
   E = (merged com D — sempre vazio)
   F = Temperatura de processo (°C)
   G = Pressão de processo (kPa)
   H = Volume do equipamento (m³)
   I = Tipo de ventilação
   J = Grau de ventilação
   K = Disponibilidade da ventilação
   L = Fonte de liberação — descrição
   M = Fonte de liberação — grau (Contínua/Primária/Secundária)
   N = Grupo e Classe de Temperatura (ex: "T 2 (II A)", "T200 (III B)")
   O = Zona 0 — extensão ou "NA" / "interno"
   P = Zona 1 — extensão (m) ou "NA"
   Q = Zona 2 — extensão (m) ou "NA"
   R = Zona 2 adicional — extensão (m) ou "NA" (texto livre)
   S = Zona 20 — extensão ou "NA" / "Interno"
   T = Zona 21 — extensão (m) ou "NA"
   U = Zona 22 — extensão (m) ou "NA"

──────────────────────────────────────────────────────────────────────
 VALORES OBSERVADOS (domínio da planilha de referência H. Weber)
──────────────────────────────────────────────────────────────────────

  Substância:           Malte, Álcool etílico
  Ventilação Tipo:      Natural
  Ventilação Grau:      Baixo/Baixa, Medio/Media
  Ventilação Disp.:     Pobre, Satisfatoria, Boa
  Fonte Liberação Desc: Interno, Escotilha, Flanges, Selo, Respiro,
                        PVRV, Operação
  Fonte Liberação Grau: Continua, Primaria, Secundaria/Secundario
  Grupo-Classe Temp:    T 2 (II A), T200 (III B)
  Zona 0:               NA, interno
  Zona 1 (m):           NA, 1.5, 1m
  Zona 2 (m):           NA, 1.5, 3
  Zona 2 adic. (m):     NA, "7,5 raio horizontal e 1m vertical",
                         "3,0 (0,6)"
  Zona 20:              NA, Interno
  Zona 21 (m):          NA, 1.5, com observação multiline
  Zona 22 (m):          NA, 3, com observação multiline
──────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Helpers de normalização
# ---------------------------------------------------------------------------

def _clean(value: str | None) -> str:
    """Strip, colapsa espaços múltiplos, remove newlines internos."""
    if not value:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _parse_numeric(value: str | None) -> Optional[float]:
    """Tenta extrair um valor numérico de uma string.

    Aceita:
      - float/int diretos: 1.5, 25, 110
      - Formato BR com vírgula: "1,5", "7,5"
      - Valores com texto extra: "1,5\\n (no descarregamento…)" → 1.5
      - "NA", "", "interno", "__" → None
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.upper() == "NA" or s.startswith("_"):
        return None
    # Tenta extrair o primeiro número (int ou decimal com , ou .)
    m = re.match(r"^[<>]?\s*(\d+[.,]?\d*)", s)
    if m:
        num_str = m.group(1).replace(",", ".")
        try:
            return float(num_str)
        except ValueError:
            return None
    return None


def _is_na(value: str | None) -> bool:
    """Verifica se o valor é NA/vazio/placeholder."""
    if value is None:
        return True
    s = str(value).strip().upper()
    return s in ("", "NA", "N/A", "-", "—") or s.startswith("_")


def _normalize_grau_ventilacao(value: str) -> str:
    """Normaliza o grau de ventilação para valores padronizados."""
    mapping = {
        "baixo": "Baixo", "baixa": "Baixo",
        "medio": "Médio", "média": "Médio", "media": "Médio",
    }
    return mapping.get(value.lower().strip(), value.strip().title())


def _normalize_disponibilidade(value: str) -> str:
    """Normaliza a disponibilidade da ventilação."""
    mapping = {
        "pobre": "Pobre",
        "satisfatoria": "Satisfatória", "satisfatória": "Satisfatória",
        "boa": "Boa",
    }
    return mapping.get(value.lower().strip(), value.strip().title())


def _normalize_grau_liberacao(value: str) -> str:
    """Normaliza o grau da fonte de liberação."""
    mapping = {
        "continua": "Contínua", "contínua": "Contínua",
        "primaria": "Primária", "primária": "Primária",
        "secundaria": "Secundária", "secundária": "Secundária",
        "secundario": "Secundária",
    }
    return mapping.get(value.lower().strip(), value.strip().title())


# ---------------------------------------------------------------------------
# Parsing do campo composto Grupo-Classe Temperatura
# ---------------------------------------------------------------------------

def parse_grupo_classe_temp(raw: str) -> tuple[str, str]:
    """Extrai classe de temperatura e grupo IEC de uma string combinada.

    Formatos observados:
      "T 2 (II A)"    → classe_temp="T2", grupo="IIA"
      "T200 (III B)"  → classe_temp="T200", grupo="IIIB"

    Returns:
        (classe_temperatura, grupo) normalizado sem espaços internos.
    """
    s = _clean(raw)
    if not s:
        return ("", "")

    # Padrão: "T<num> (<grupo>)"
    m = re.match(r"(T\s*\d+)\s*\(([^)]+)\)", s, re.IGNORECASE)
    if m:
        classe = re.sub(r"\s+", "", m.group(1)).upper()  # "T 2" → "T2"
        grupo = re.sub(r"\s+", "", m.group(2)).upper()    # "II A" → "IIA"
        return (classe, grupo)

    # Fallback: retorna raw limpo
    return (s, "")


# ---------------------------------------------------------------------------
# AreaClassificationRow — 1 linha da planilha
# ---------------------------------------------------------------------------

class AreaClassificationRow(BaseModel):
    """Uma linha normalizada da planilha de classificação de áreas.

    Cada instância mapeia uma combinação equipamento × fonte de liberação.
    Um mesmo equipamento pode ter múltiplas linhas (Interno + Escotilha +
    Flanges = 3 linhas com fontes diferentes).
    """

    # ── Identificação do equipamento ──
    identificacao: str = Field(
        ..., min_length=1,
        description="Tag/código do equipamento (col A)",
    )
    descricao: str = Field(
        default="",
        description="Descrição do equipamento (col B)",
    )
    locacao: str = Field(
        default="",
        description="Área/setor da planta onde está instalado (col C)",
    )

    # ── Substância combustível ──
    substancia: str = Field(
        ..., min_length=1,
        description="Substância combustível presente (col D)",
    )

    # ── Dados de processo ──
    temperatura_celsius: Optional[float] = Field(
        None,
        description="Temperatura de processo em °C (col F)",
    )
    pressao_kpa: Optional[str] = Field(
        None,
        description="Pressão de processo em kPa — texto livre (col G)",
    )
    volume_m3: Optional[str] = Field(
        None,
        description="Volume do equipamento em m³ — texto livre (col H)",
    )

    # ── Ventilação ──
    ventilacao_tipo: str = Field(
        default="Natural",
        description="Tipo de ventilação: Natural, Forçada, Mista (col I)",
    )
    ventilacao_grau: str = Field(
        ...,
        description="Grau de ventilação: Baixo, Médio, Alto (col J)",
    )
    ventilacao_disponibilidade: str = Field(
        ...,
        description="Disponibilidade da ventilação: Pobre, Satisfatória, Boa (col K)",
    )

    # ── Fonte de liberação ──
    fonte_liberacao_descricao: str = Field(
        ...,
        description="Descrição da fonte: Interno, Escotilha, Flanges, Selo, Respiro, PVRV, Operação (col L)",
    )
    fonte_liberacao_grau: str = Field(
        ...,
        description="Grau da fonte: Contínua, Primária, Secundária (col M)",
    )

    # ── Grupo e Classe de Temperatura ──
    classe_temperatura: str = Field(
        default="",
        description="Classe de temperatura: T1..T6, T200, T150 etc. (parsed de col N)",
    )
    grupo: str = Field(
        default="",
        description="Grupo IEC: IIA, IIB, IIC, IIIA, IIIB, IIIC (parsed de col N)",
    )
    grupo_classe_temp_raw: str = Field(
        default="",
        description="Valor original da coluna N (ex: 'T 2 (II A)')",
    )

    # ── Extensões de zona — Gases/Vapores (Zonas 0, 1, 2) ──
    zona_0: Optional[str] = Field(
        None,
        description="Zona 0: 'interno', 'NA', ou extensão (col O)",
    )
    zona_1_m: Optional[float] = Field(
        None,
        description="Zona 1 em metros (col P): valor numérico ou None se NA",
    )
    zona_2_m: Optional[float] = Field(
        None,
        description="Zona 2 em metros (col Q): valor numérico ou None se NA",
    )
    zona_2_adicional: Optional[str] = Field(
        None,
        description="Zona 2 adicional — texto livre com extensão descritiva (col R)",
    )

    # ── Extensões de zona — Poeiras (Zonas 20, 21, 22) ──
    zona_20: Optional[str] = Field(
        None,
        description="Zona 20: 'Interno', 'NA', ou extensão (col S)",
    )
    zona_21_m: Optional[float] = Field(
        None,
        description="Zona 21 em metros (col T): valor numérico ou None se NA",
    )
    zona_22_m: Optional[float] = Field(
        None,
        description="Zona 22 em metros (col U): valor numérico ou None se NA",
    )

    # ── Texto bruto das zonas (para preservar observações multiline) ──
    zona_21_raw: Optional[str] = Field(None, description="Texto bruto col T")
    zona_22_raw: Optional[str] = Field(None, description="Texto bruto col U")

    # ── Metadados ──
    row_number: int = Field(
        default=0, ge=0,
        description="Número da linha na planilha original (para debug)",
    )

    model_config = {"frozen": True}

    @property
    def is_dust(self) -> bool:
        """Retorna True se a substância é poeira (zonas 20/21/22 aplicáveis)."""
        return self.grupo.startswith("III") if self.grupo else False

    @property
    def is_gas_vapor(self) -> bool:
        """Retorna True se a substância é gás/vapor (zonas 0/1/2 aplicáveis)."""
        return self.grupo.startswith("II") if self.grupo else False

    @property
    def has_zone_data(self) -> bool:
        """Retorna True se alguma zona foi classificada (não-NA)."""
        if self.is_dust:
            return (
                (self.zona_20 is not None and not _is_na(self.zona_20))
                or self.zona_21_m is not None
                or self.zona_22_m is not None
            )
        return (
            (self.zona_0 is not None and not _is_na(self.zona_0))
            or self.zona_1_m is not None
            or self.zona_2_m is not None
        )


# ---------------------------------------------------------------------------
# AreaClassificationContext — contexto consolidado POR EQUIPAMENTO
# ---------------------------------------------------------------------------

class AreaClassificationContext(BaseModel):
    """Contexto consolidado de um equipamento para renderização e LLM.

    Agrupa todas as linhas (fontes de liberação) de um mesmo equipamento.
    Um destilador com 3 linhas (Interno + Escotilha + Flanges) gera 1 context.
    """

    index: int = Field(..., ge=1, description="Índice sequencial (1-based)")
    identificacao: str = Field(..., min_length=1, description="Tag do equipamento")
    descricao: str = Field(default="", description="Descrição do equipamento")
    locacao: str = Field(default="", description="Área/setor da planta")
    substancia: str = Field(default="", description="Substância combustível principal")

    # Dados de processo (do equipamento, não da fonte)
    temperatura_celsius: Optional[float] = None
    pressao_kpa: Optional[str] = None
    volume_m3: Optional[str] = None

    # Classificação IEC
    classe_temperatura: str = Field(default="", description="Classe temp (ex: T2)")
    grupo: str = Field(default="", description="Grupo IEC (ex: IIA)")

    # Fontes de liberação (uma por linha original)
    fontes_liberacao: list["FonteLiberacaoDetail"] = Field(
        default_factory=list,
        description="Detalhes de cada fonte de liberação deste equipamento",
    )

    # Contagem
    row_count: int = Field(default=1, ge=1, description="Linhas da planilha agregadas")

    # RAG context (preenchido depois, quando implementado)
    normative_context: list[str] = Field(
        default_factory=list,
        description="Trechos normativos injetados por RAG",
    )

    model_config = {"frozen": True}

    def to_template_dict(self) -> dict:
        """Converte para formato compatível com o template Jinja2."""
        return {
            "index": self.index,
            "identificacao": self.identificacao,
            "descricao": self.descricao,
            "locacao": self.locacao,
            "substancia": self.substancia,
            "temperatura": self.temperatura_celsius,
            "pressao": self.pressao_kpa,
            "volume": self.volume_m3,
            "classe_temperatura": self.classe_temperatura,
            "grupo": self.grupo,
            "fontes": [f.model_dump() for f in self.fontes_liberacao],
            "row_count": self.row_count,
        }


class FonteLiberacaoDetail(BaseModel):
    """Detalhe de uma fonte de liberação individual."""

    descricao: str = Field(..., description="Tipo: Interno, Escotilha, Flanges, Selo...")
    grau: str = Field(..., description="Contínua, Primária, Secundária")

    # Ventilação aplicável a esta fonte
    ventilacao_grau: str = Field(default="", description="Grau de ventilação")
    ventilacao_disponibilidade: str = Field(default="", description="Disponibilidade")

    # Zonas resultantes — Gases/Vapores
    zona_0: Optional[str] = None
    zona_1_m: Optional[float] = None
    zona_2_m: Optional[float] = None
    zona_2_adicional: Optional[str] = None

    # Zonas resultantes — Poeiras
    zona_20: Optional[str] = None
    zona_21_m: Optional[float] = None
    zona_22_m: Optional[float] = None

    # Texto bruto (preservar observações)
    zona_21_raw: Optional[str] = None
    zona_22_raw: Optional[str] = None

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# Re-exports
# ---------------------------------------------------------------------------

__all__ = [
    "AreaClassificationRow",
    "AreaClassificationContext",
    "FonteLiberacaoDetail",
    "parse_grupo_classe_temp",
]
