"""Pós-processador de equipamentos — aplica normalizadores na ordem correta.

Pipeline (idempotente):
  1. `contamination_filter`     — remove boilerplate RAG
  2. `technical_text_normalizer` — corrige typos/variantes
  3. `normative_reference_formatter` — formata normas
  4. `list_normalizer`           — pontuação consistente
  5. `justification_dedup`       — remove justificativas duplicadas
"""
from __future__ import annotations

from typing import Any

from .contamination_filter import filter_contamination
from .justification_dedup import dedupe_justifications
from .list_normalizer import normalize_list_item
from .normative_reference_formatter import format_normative_reference
from .technical_text_normalizer import normalize_technical_text


def _process_text(value: str, *, apply_contamination_filter: bool = True) -> str:
    if not value:
        return value
    original = value
    out = value
    if apply_contamination_filter:
        out = filter_contamination(out)
    out = normalize_technical_text(out)
    out = format_normative_reference(out)
    # Salvaguarda: se o pipeline esvaziou um texto não-vazio (ex.: contamination
    # filter casou com a frase inteira), preservar o original para evitar
    # bloqueio no preflight por campos vazios.
    if not (out or "").strip() and original.strip():
        return original
    return out


def _process_list_field(
    items: list[Any],
    text_keys: tuple[str, ...],
    *,
    apply_contamination_filter: bool = True,
) -> list[Any]:
    out: list[Any] = []
    for item in items:
        if isinstance(item, dict):
            new_item = dict(item)
            for key in text_keys:
                if key in new_item and isinstance(new_item[key], str):
                    text = _process_text(
                        new_item[key],
                        apply_contamination_filter=apply_contamination_filter,
                    )
                    # Aplica list-normalizer (capitaliza + ponto final) só ao
                    # texto principal de bullet (chave 'texto').
                    if key == "texto":
                        text = normalize_list_item(text, end_with_period=True)
                    new_item[key] = text
            out.append(new_item)
        elif isinstance(item, str):
            processed = _process_text(
                item, apply_contamination_filter=apply_contamination_filter
            )
            out.append(normalize_list_item(processed, end_with_period=True))
    return out


def _renumber_recommendations(eq: dict[str, Any]) -> None:
    """Renumera `recomendacoes_tecnicas` de 1..N de forma contígua e remapeia
    `justificativas_tecnicas` pelo mesmo mapa, preservando o pareamento 1:1.

    O `numero` vem do LLM e pode chegar com lacunas/fora de ordem (ex.: 1, 2, 4),
    o que faz o marcador da lista no PDF "sair diferente". Aqui reordenamos para
    a posição natural, mantendo a correspondência recomendação↔justificativa.

    Idempotente: se já estiver 1..N contíguo, o mapa é identidade e nada muda.
    Mutates ``eq`` in place.
    """
    recs = eq.get("recomendacoes_tecnicas")
    if not isinstance(recs, list) or not recs:
        return

    # Mapa numero_antigo -> numero_novo, a partir da ordem das recomendações.
    old_to_new: dict[int, int] = {}
    for new_numero, rec in enumerate(recs, start=1):
        if isinstance(rec, dict):
            old = rec.get("numero")
            if isinstance(old, int):
                old_to_new[old] = new_numero
            rec["numero"] = new_numero

    justs = eq.get("justificativas_tecnicas")
    if isinstance(justs, list):
        # Justificativas casam pela chave `numero` da recomendação. Após o
        # dedupe algumas podem ter sumido; remapeamos as sobreviventes pelo mapa
        # e, na ausência de correspondência, caímos na posição sequencial.
        for fallback_numero, jst in enumerate(justs, start=1):
            if isinstance(jst, dict):
                old = jst.get("numero")
                jst["numero"] = old_to_new.get(old, fallback_numero)


def post_process_equipment(eq: dict[str, Any]) -> dict[str, Any]:
    """Aplica todos os normalizadores a um equipamento (mutates and returns).

    Campos tratados:
      - recomendacoes_tecnicas[].texto / .norma_referencia
      - justificativas_tecnicas[].texto / .norma_referencia (+ dedupe)
      - observacoes_extras (string)
      - equipment_description (string)
    """
    # Strings simples
    for str_key in ("observacoes_extras", "equipment_description", "funcao_operacional",
                    "local_instalacao"):
        if isinstance(eq.get(str_key), str):
            eq[str_key] = _process_text(eq[str_key])

    # Listas estruturadas
    if isinstance(eq.get("recomendacoes_tecnicas"), list):
        # Recomendações técnicas SÃO citações de norma por natureza —
        # não aplicar contamination_filter (que apagaria a recomendação inteira
        # quando seu texto começa com "Conforme NBR ..., estabelece-se ...").
        eq["recomendacoes_tecnicas"] = _process_list_field(
            eq["recomendacoes_tecnicas"],
            text_keys=("texto", "norma_referencia"),
            apply_contamination_filter=False,
        )

    if isinstance(eq.get("justificativas_tecnicas"), list):
        processed = _process_list_field(
            eq["justificativas_tecnicas"],
            text_keys=("texto", "norma_referencia"),
        )
        eq["justificativas_tecnicas"] = dedupe_justifications(
            processed, text_key="texto"
        )

    # Renumera 1..N contíguo (recomendações + justificativas) após o dedupe,
    # para o marcador da lista no PDF refletir a ordem natural.
    _renumber_recommendations(eq)
    return eq


def post_process_all(equipments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [post_process_equipment(eq) for eq in equipments]
