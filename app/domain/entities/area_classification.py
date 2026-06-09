"""Entidades de domínio — Classificação de Áreas v2.

Modelo canônico:
  - 1 linha da planilha = 1 fonte de liberação
  - agrupamento posterior = por área/local
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


def _clean(value: str | None) -> str:
    return (value or "").strip()


class AreaClassificationRow(BaseModel):
    area_local: str = Field(..., min_length=1)
    area_descricao: str = Field(default="")
    tag_referencia: str = Field(default="")
    substancia: str = Field(..., min_length=1)
    fonte_liberacao: str = Field(..., min_length=1)
    grau_liberacao: str = Field(..., min_length=1)
    ventilacao_tipo: str = Field(..., min_length=1)
    grau_ventilacao: str = Field(..., min_length=1)
    disponibilidade_ventilacao: str = Field(..., min_length=1)
    zona: str = Field(..., min_length=1)
    extensao: str = Field(..., min_length=1)
    grupo: str = Field(default="")
    classe_temperatura: str = Field(default="")
    epl: str = Field(default="")
    temperatura_processo: str = Field(default="")
    pressao_processo: str = Field(default="")
    volume_processo: str = Field(default="")
    observacoes: str = Field(default="")
    row_number: int = Field(default=0, ge=0)

    model_config = {"frozen": True}

    @field_validator("*", mode="before")
    @classmethod
    def _normalize_strings(cls, value: object) -> object:
        if isinstance(value, str):
            return _clean(value)
        return value


class FonteLiberacaoDetail(BaseModel):
    tag_referencia: str = ""
    substancia: str = ""
    descricao: str = ""
    grau: str = ""
    ventilacao_tipo: str = ""
    ventilacao_grau: str = ""
    ventilacao_disponibilidade: str = ""
    zona: str = ""
    extensao: str = ""
    grupo: str = ""
    classe_temperatura: str = ""
    epl: str = ""
    temperatura_processo: str = ""
    pressao_processo: str = ""
    volume_processo: str = ""
    observacoes: str = ""

    model_config = {"frozen": True}


class AreaClassificationContext(BaseModel):
    index: int = Field(..., ge=1)
    area_local: str = Field(..., min_length=1)
    area_descricao: str = Field(default="")
    tag_referencias: list[str] = Field(default_factory=list)
    substancias: list[str] = Field(default_factory=list)
    grupo: str = ""
    classe_temperatura: str = ""
    epl: str = ""
    fontes_liberacao: list[FonteLiberacaoDetail] = Field(default_factory=list)
    row_count: int = Field(default=1, ge=1)
    operational_notes: str = ""
    ventilation_premises: str = ""
    normative_context: list[str] = Field(default_factory=list)
    reference_documents: list[dict[str, str]] = Field(default_factory=list)
    substance_properties: list[dict[str, Any]] = Field(default_factory=list)
    images: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"frozen": True}

    @property
    def identificacao(self) -> str:
        return self.area_local

    @property
    def descricao(self) -> str:
        return self.area_descricao

    @property
    def locacao(self) -> str:
        return self.area_local

    @property
    def substancia(self) -> str:
        return ", ".join(self.substancias)

    def to_template_dict(self) -> dict:
        return {
            "index": self.index,
            "area_local": self.area_local,
            "area_descricao": self.area_descricao,
            "identificacao": self.area_local,
            "descricao": self.area_descricao,
            "locacao": self.area_local,
            "tag_referencias": self.tag_referencias,
            "substancias": self.substancias,
            "substancia": self.substancia,
            "grupo": self.grupo,
            "classe_temperatura": self.classe_temperatura,
            "epl": self.epl,
            "row_count": self.row_count,
            "fontes": [fonte.model_dump() for fonte in self.fontes_liberacao],
            "operational_notes": self.operational_notes,
            "ventilation_premises": self.ventilation_premises,
            "reference_documents": self.reference_documents,
            "substance_properties": self.substance_properties,
            "images": self.images,
        }


__all__ = [
    "AreaClassificationRow",
    "AreaClassificationContext",
    "FonteLiberacaoDetail",
]
