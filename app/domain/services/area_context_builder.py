"""Builder de contexto para Classificação de Áreas v2."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from app.domain.entities.area_classification import (
    AreaClassificationContext,
    AreaClassificationRow,
    FonteLiberacaoDetail,
)


def build_area_classification_contexts(
    rows: list[AreaClassificationRow],
    *,
    area_complements: list[dict[str, Any]] | None = None,
    substance_complements: list[dict[str, Any]] | None = None,
    reference_documents: list[dict[str, Any]] | None = None,
) -> list[AreaClassificationContext]:
    if not rows:
        raise ValueError("rows não pode estar vazio")

    area_map = {
        (item.get("area_name") or "").strip().lower(): item
        for item in (area_complements or [])
    }
    substance_map = {
        (item.get("substance_name") or "").strip().lower(): item
        for item in (substance_complements or [])
    }

    groups: OrderedDict[str, dict[str, Any]] = OrderedDict()

    for row in rows:
        key = row.area_local.strip().lower()
        if key not in groups:
            groups[key] = {
                "area_local": row.area_local,
                "area_descricao": row.area_descricao,
                "tag_referencias": [],
                "substancias": [],
                "grupo": row.grupo,
                "classe_temperatura": row.classe_temperatura,
                "epl": row.epl,
                "fontes_liberacao": [],
            }

        current = groups[key]

        if not current["area_descricao"] and row.area_descricao:
            current["area_descricao"] = row.area_descricao
        if row.tag_referencia and row.tag_referencia not in current["tag_referencias"]:
            current["tag_referencias"].append(row.tag_referencia)
        if row.substancia and row.substancia not in current["substancias"]:
            current["substancias"].append(row.substancia)
        if not current["grupo"] and row.grupo:
            current["grupo"] = row.grupo
        if not current["classe_temperatura"] and row.classe_temperatura:
            current["classe_temperatura"] = row.classe_temperatura
        if not current["epl"] and row.epl:
            current["epl"] = row.epl

        current["fontes_liberacao"].append(
            FonteLiberacaoDetail(
                tag_referencia=row.tag_referencia,
                substancia=row.substancia,
                descricao=row.fonte_liberacao,
                grau=row.grau_liberacao,
                ventilacao_tipo=row.ventilacao_tipo,
                ventilacao_grau=row.grau_ventilacao,
                ventilacao_disponibilidade=row.disponibilidade_ventilacao,
                zona=row.zona,
                extensao=row.extensao,
                grupo=row.grupo,
                classe_temperatura=row.classe_temperatura,
                epl=row.epl,
                temperatura_processo=row.temperatura_processo,
                pressao_processo=row.pressao_processo,
                volume_processo=row.volume_processo,
                observacoes=row.observacoes,
            ),
        )

    references = [
        {
            "title": item.get("title") or "",
            "document_code": item.get("document_code") or "",
            "document_url": item.get("document_url") or "",
            "notes": item.get("notes") or "",
        }
        for item in (reference_documents or [])
    ]

    contexts: list[AreaClassificationContext] = []
    for index, group in enumerate(groups.values(), start=1):
        normalized_area_key = group["area_local"].strip().lower()
        area_extra = area_map.get(normalized_area_key, {})
        substance_properties = []
        for substance_name in group["substancias"]:
            sub_key = substance_name.strip().lower()
            sub_meta = substance_map.get(sub_key, {}) or {}
            props_json = sub_meta.get("properties_json")
            properties_summary = (
                props_json.get("resumo")
                if isinstance(props_json, dict)
                else None
            )
            substance_properties.append(
                {
                    "substance_name": substance_name,
                    "grupo": sub_meta.get("grupo"),
                    "classe_temperatura": sub_meta.get("classe_temperatura"),
                    "epl": sub_meta.get("epl"),
                    "notes": sub_meta.get("notes"),
                    "properties_summary": properties_summary,
                    # ── Campos físico-químicos detalhados (Tabela 1) ──
                    "tipo": sub_meta.get("tipo"),
                    "ponto_fulgor": sub_meta.get("ponto_fulgor"),
                    "lii": sub_meta.get("lii"),
                    "densidade_relativa": sub_meta.get("densidade_relativa"),
                    "tai": sub_meta.get("tai"),
                    "cme": sub_meta.get("cme"),
                    "mit": sub_meta.get("mit"),
                    "sit_camada": sub_meta.get("sit_camada"),
                    "tmax": sub_meta.get("tmax"),
                    "st": sub_meta.get("st"),
                    "legend_notes": sub_meta.get("legend_notes") or [],
                },
            )

        images = list(area_extra.get("photos") or [])
        complement_description = (area_extra.get("description") or "").strip()
        area_descricao = complement_description or group["area_descricao"]

        contexts.append(
            AreaClassificationContext(
                index=index,
                area_local=group["area_local"],
                area_descricao=area_descricao,
                tag_referencias=group["tag_referencias"],
                substancias=group["substancias"],
                grupo=group["grupo"],
                classe_temperatura=group["classe_temperatura"],
                epl=group["epl"],
                fontes_liberacao=group["fontes_liberacao"],
                row_count=len(group["fontes_liberacao"]),
                operational_notes=area_extra.get("operational_notes") or "",
                ventilation_premises=area_extra.get("ventilation_premises") or "",
                reference_documents=references,
                substance_properties=substance_properties,
                images=images,
            ),
        )

    return contexts
