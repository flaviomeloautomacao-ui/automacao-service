"""Serviço de domínio — valida e sanitiza a saída do LLM per-equipment.

Implementa as regras OV-01 … OV-14 definidas em
``docs/equipment_llm_contract.md``, §4, e os limites de tamanho §5.2.

──────────────────────────────────────────────────────────────────────
 RESPONSABILIDADES
──────────────────────────────────────────────────────────────────────

 1. Parsear JSON cru da resposta do LLM.
 2. Validar estrutura (OV-01 … OV-09).
 3. Validar conteúdo (OV-10 … OV-14).
 4. Aplicar limites de tamanho §5.2.
 5. Construir fallback determinístico (§4.3).

 **NÃO** faz: chamadas de rede, acesso a banco, chamadas ao LLM.
──────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger

from app.domain.entities import (
    EquipmentLLMInput,
    EquipmentLLMOutput,
    JustificativaTecnica,
    RecomendacaoTecnica,
)


# ---------------------------------------------------------------------------
# Constantes §5.2
# ---------------------------------------------------------------------------

_MIN_RECS = 2
_MAX_RECS = 10
_REC_TEXT_MIN = 50
_REC_TEXT_MAX = 500
_REC_NORMA_MIN = 5
_REC_NORMA_MAX = 150
_JUST_TEXT_MIN = 80
_JUST_TEXT_MAX = 1_000
_TOTAL_OUTPUT_MAX = 15_000

# Regex para extrair o código base de uma norma (ex: "NFPA 652", "NR-10",
# "ABNT NBR IEC 60079-10-2"). Captura o identificador numérico completo,
# parando antes de sufixos inventados como ", Seção 8.3.2".
_NORM_BASE_RE = re.compile(
    r"(NFPA\s*\d+|NR[\-\s]*\d+|(?:ABNT\s+)?NBR(?:\s+IEC)?\s*\d[\d\-\.]*)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Resultado de validação
# ---------------------------------------------------------------------------


class ValidationResult:
    """Resultado da validação de output — sucesso ou falha com motivo."""

    __slots__ = ("success", "output", "reason", "needs_retry")

    def __init__(
        self,
        *,
        success: bool,
        output: EquipmentLLMOutput | None = None,
        reason: str = "",
        needs_retry: bool = False,
    ) -> None:
        self.success = success
        self.output = output
        self.reason = reason
        self.needs_retry = needs_retry


# ---------------------------------------------------------------------------
# Funções públicas
# ---------------------------------------------------------------------------


def validate_llm_output(
    raw_json: str,
    llm_input: EquipmentLLMInput,
) -> ValidationResult:
    """Valida e sanitiza a resposta crua do LLM.

    Aplica as regras OV-01 … OV-14 e limites §5.2 sequencialmente.

    Args:
        raw_json: String JSON retornada pelo LLM.
        llm_input: Input original (usado para fallback de norma e dados).

    Returns:
        ``ValidationResult`` com ``success=True`` e ``output`` preenchido
        se aprovado, ou ``success=False`` com ``reason`` e ``needs_retry``
        indicando se vale fazer retry LLM.
    """
    equip = llm_input.equipment_name

    # ── OV-01: parsear JSON ───────────────────────────────────────
    data = _parse_json(raw_json)
    if data is None:
        logger.warning("OV-01 falhou | equip={} | JSON inválido", equip)
        return ValidationResult(
            success=False,
            reason="OV-01: resposta não é JSON válido",
            needs_retry=True,
        )

    # ── OV-02: chaves obrigatórias ────────────────────────────────
    recs_raw = data.get("recomendacoes_tecnicas")
    justs_raw = data.get("justificativas_tecnicas")

    if recs_raw is None or justs_raw is None:
        missing = []
        if recs_raw is None:
            missing.append("recomendacoes_tecnicas")
        if justs_raw is None:
            missing.append("justificativas_tecnicas")
        logger.warning("OV-02 falhou | equip={} | faltam: {}", equip, missing)
        return ValidationResult(
            success=False,
            reason=f"OV-02: chaves faltantes: {missing}",
            needs_retry=True,
        )

    # ── OV-03 / OV-04: arrays de objetos ─────────────────────────
    if not isinstance(recs_raw, list) or not all(isinstance(r, dict) for r in recs_raw):
        logger.warning("OV-03 falhou | equip={}", equip)
        return ValidationResult(
            success=False,
            reason="OV-03: recomendacoes_tecnicas não é array de objetos",
            needs_retry=True,
        )
    if not isinstance(justs_raw, list) or not all(isinstance(j, dict) for j in justs_raw):
        logger.warning("OV-04 falhou | equip={}", equip)
        return ValidationResult(
            success=False,
            reason="OV-04: justificativas_tecnicas não é array de objetos",
            needs_retry=True,
        )

    # ── OV-05: igualar tamanhos ───────────────────────────────────
    min_len = min(len(recs_raw), len(justs_raw))
    if len(recs_raw) != len(justs_raw):
        logger.info(
            "OV-05 | equip={} | recs={}, justs={} → trim para {}",
            equip, len(recs_raw), len(justs_raw), min_len,
        )
    recs_raw = recs_raw[:min_len]
    justs_raw = justs_raw[:min_len]

    # ── OV-10 / OV-11: remover itens com texto vazio ─────────────
    cleaned_pairs: list[tuple[dict, dict]] = []
    for rec, jst in zip(recs_raw, justs_raw):
        rec_text = (rec.get("texto") or "").strip()
        jst_text = (jst.get("texto") or "").strip()
        if not rec_text:
            logger.info("OV-10 | equip={} | recomendação com texto vazio removida", equip)
            continue
        if not jst_text:
            logger.info("OV-11 | equip={} | justificativa com texto vazio removida", equip)
            continue
        cleaned_pairs.append((rec, jst))

    # ── OV-13: remover recomendações duplicadas ───────────────────
    seen_texts: set[str] = set()
    deduped_pairs: list[tuple[dict, dict]] = []
    for rec, jst in cleaned_pairs:
        text_key = (rec.get("texto") or "").strip().lower()
        if text_key in seen_texts:
            logger.info("OV-13 | equip={} | duplicata removida", equip)
            continue
        seen_texts.add(text_key)
        deduped_pairs.append((rec, jst))

    # ── OV-07: truncar em 10 ─────────────────────────────────────
    if len(deduped_pairs) > _MAX_RECS:
        logger.info("OV-07 | equip={} | truncando de {} para {}", equip, len(deduped_pairs), _MAX_RECS)
        deduped_pairs = deduped_pairs[:_MAX_RECS]

    # ── OV-06 / OV-14: mínimo 2 ──────────────────────────────────
    if len(deduped_pairs) < _MIN_RECS:
        logger.warning(
            "OV-06/OV-14 | equip={} | apenas {} itens após limpeza",
            equip, len(deduped_pairs),
        )
        return ValidationResult(
            success=False,
            reason=f"OV-06/OV-14: apenas {len(deduped_pairs)} recomendações após limpeza (mín {_MIN_RECS})",
            needs_retry=True,
        )

    # ── OV-08 / OV-09: renumerar sequencialmente ─────────────────
    # ── OV-12: fallback de norma_referencia (fortalecido com RAG) ─
    # ── §5.2: limites de tamanho ──────────────────────────────────
    default_norma = llm_input.normas_aplicaveis[0] if llm_input.normas_aplicaveis else ""

    # Conjunto de normas válidas: normas do profile + sources do RAG
    valid_norm_sources: set[str] = set()
    for na in llm_input.normas_aplicaveis:
        valid_norm_sources.add(na.strip().lower())
        # Adicionar variantes parciais (ex.: "ABNT NBR 16385")
        for part in na.split("—"):
            cleaned = part.strip().lower()
            if len(cleaned) >= 5:
                valid_norm_sources.add(cleaned)
    for exc in llm_input.normative_context:
        src_lower = exc.source.strip().lower()
        valid_norm_sources.add(src_lower)
        # Também aceitar sem extensão .pdf
        if src_lower.endswith(".pdf"):
            valid_norm_sources.add(src_lower[:-4].strip())

    # Pré-computar códigos base das normas válidas para match robusto
    valid_norm_bases = _build_valid_norm_bases(valid_norm_sources)

    has_normative_context = bool(llm_input.normative_context)

    final_recs: list[RecomendacaoTecnica] = []
    final_justs: list[JustificativaTecnica] = []

    for idx, (rec, jst) in enumerate(deduped_pairs, 1):
        # Texto da recomendação
        rec_text = _truncate(
            (rec.get("texto") or "").strip(),
            _REC_TEXT_MAX,
        )

        # Tipo de recomendação (novo — normativa | boa_pratica)
        raw_tipo = (rec.get("tipo") or "").strip().lower()
        raw_trecho = (rec.get("trecho_normativo") or "").strip() or None

        # Norma referência (OV-12 — endurecido com match por código base)
        norma = (rec.get("norma_referencia") or "").strip()
        if len(norma) < _REC_NORMA_MIN:
            norma = default_norma
        else:
            # Extrair código base da norma citada pelo LLM
            norma_base = _extract_norm_base(norma)
            norma_lower = norma.strip().lower()

            # Verificar se a norma é válida: match exato OU match por código base
            norm_is_valid = (
                norma_lower in valid_norm_sources
                or (norma_base is not None and norma_base in valid_norm_bases)
            )

            if norm_is_valid and norma_base is not None:
                # Norma válida — mas strippear seções/cláusulas inventadas.
                # Encontrar a fonte válida mais completa que contém o código base.
                matched_source = _find_matching_source(
                    norma_base, valid_norm_sources, llm_input.normas_aplicaveis,
                    [e.source for e in llm_input.normative_context],
                )
                if matched_source:
                    norma = matched_source
            elif not norm_is_valid and has_normative_context:
                # Fallback: usar a norma mais relevante do contexto RAG
                best_source = llm_input.normative_context[0].source
                logger.info(
                    "OV-12 | equip={} | norma inventada '{}' (base={}) → fallback para '{}' (RAG)",
                    equip,
                    norma,
                    norma_base,
                    best_source,
                )
                norma = best_source
            elif not norm_is_valid:
                # Sem RAG: manter fallback para norma do perfil
                logger.info(
                    "OV-12 | equip={} | norma '{}' não reconhecida (base={}) → fallback default",
                    equip,
                    norma,
                    norma_base,
                )
                norma = default_norma

        norma = _truncate(norma, _REC_NORMA_MAX)

        # ── Classificar tipo (inferir se não fornecido) ────────────
        if raw_tipo == "normativa" and raw_trecho:
            tipo = "normativa"
            trecho = _truncate(raw_trecho, 2000)
        elif raw_tipo == "normativa" and not raw_trecho:
            # LLM disse normativa mas não forneceu trecho → reclassificar
            tipo = "boa_pratica"
            trecho = None
            logger.info(
                "OV-12 | equip={} | rec {} marcada normativa sem trecho → reclassificada boa_pratica",
                equip, idx,
            )
        elif raw_trecho:
            # Trecho fornecido mas tipo não é normativa → inferir normativa
            tipo = "normativa"
            trecho = _truncate(raw_trecho, 2000)
        else:
            tipo = "boa_pratica"
            trecho = None

        # Texto da justificativa
        jst_text = _truncate(
            (jst.get("texto") or "").strip(),
            _JUST_TEXT_MAX,
        )

        final_recs.append(
            RecomendacaoTecnica(
                numero=idx,
                texto=rec_text,
                norma_referencia=norma,
                tipo=tipo,
                trecho_normativo=trecho,
            )
        )
        final_justs.append(
            JustificativaTecnica(numero=idx, texto=jst_text)
        )

    # ── §5.2: total output ≤ 15.000 chars ────────────────────────
    output_data = {
        "recomendacoes_tecnicas": [r.model_dump() for r in final_recs],
        "justificativas_tecnicas": [j.model_dump() for j in final_justs],
    }
    serialized = json.dumps(output_data, ensure_ascii=False)
    if len(serialized) > _TOTAL_OUTPUT_MAX:
        logger.info(
            "§5.2 | equip={} | output {} chars > {} — truncando justificativas",
            equip, len(serialized), _TOTAL_OUTPUT_MAX,
        )
        final_justs = _shrink_justificativas(final_justs, final_recs, _TOTAL_OUTPUT_MAX)

    try:
        output = EquipmentLLMOutput(
            recomendacoes_tecnicas=final_recs,
            justificativas_tecnicas=final_justs,
        )
    except Exception as exc:
        logger.error("Falha ao construir EquipmentLLMOutput | equip={} | {}", equip, exc)
        return ValidationResult(
            success=False,
            reason=f"Falha ao construir modelo: {exc}",
            needs_retry=False,
        )

    return ValidationResult(success=True, output=output)


def build_fallback(llm_input: EquipmentLLMInput) -> EquipmentLLMOutput:
    """Constrói output determinístico de fallback (§4.3).

    Usa ``medidas_a_implementar`` do input como recomendações.
    Se vazio, usa uma recomendação genérica.

    Melhorias sobre a versão original:
    - Distribui normas entre recomendações por keyword heurístico.
    - Usa fonte RAG como norma quando contexto normativo está disponível.
    - Justificativas referenciam perigos e consequências do equipamento.

    Args:
        llm_input: Input original do equipamento.

    Returns:
        ``EquipmentLLMOutput`` determinístico.
    """
    items = list(llm_input.medidas_a_implementar) or [
        "Realizar avaliação detalhada conforme normas aplicáveis"
    ]

    # Garantir mínimo de 2 itens
    if len(items) == 1:
        items.append(
            "Implementar plano de ação corretiva com cronograma de adequação"
        )

    default_norma = (
        llm_input.normas_aplicaveis[0] if llm_input.normas_aplicaveis else "Norma aplicável"
    )

    sev = llm_input.classificacao_do_risco.categoria_severidade
    risco = llm_input.classificacao_do_risco.categoria_risco
    equip_name = llm_input.equipment_name

    # Perigos e consequências para enriquecer justificativas
    perigos_resumo = ", ".join(llm_input.identificacao_dos_perigos[:3]) or "perigos identificados"
    consequencias_resumo = ", ".join(llm_input.consequencias_potenciais[:2]) or "consequências potenciais"

    recs: list[RecomendacaoTecnica] = []
    justs: list[JustificativaTecnica] = []

    for i, medida in enumerate(items[:_MAX_RECS], start=1):
        # Distribuir norma por keyword heurístico
        norma = _match_norma_for_fallback(
            medida, llm_input.normas_aplicaveis, llm_input.normative_context,
        ) or default_norma

        recs.append(
            RecomendacaoTecnica(
                numero=i,
                texto=medida,
                norma_referencia=norma,
                tipo="boa_pratica",
                trecho_normativo=None,
            )
        )
        justs.append(
            JustificativaTecnica(
                numero=i,
                texto=(
                    f"A recomendação técnica nº {i} é necessária para o equipamento "
                    f"{equip_name}, pois os perigos identificados ({perigos_resumo}) "
                    f"podem resultar em {consequencias_resumo}. Considerando a "
                    f"severidade {sev} e o risco {risco}, a medida deve ser "
                    f"implementada e acompanhada conforme {norma}."
                ),
            )
        )

    logger.info(
        "Fallback determinístico gerado | equip={} | recs={}",
        equip_name, len(recs),
    )

    return EquipmentLLMOutput(
        recomendacoes_tecnicas=recs,
        justificativas_tecnicas=justs,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_norm_base(norma: str) -> str | None:
    """Extrai o código base normalizado de uma referência normativa.

    Exemplos::

        _extract_norm_base("NFPA 652:2022 — Standard on...")  → "nfpa 652"
        _extract_norm_base("ABNT NBR IEC 60079-10-2")         → "nbr iec 60079-10-2"
        _extract_norm_base("NR-10, Seção 10.8.4")             → "nr-10"
        _extract_norm_base("texto qualquer sem norma")         → None

    Returns:
        Código base normalizado (lowercase, sem ano/título) ou ``None``.
    """
    m = _NORM_BASE_RE.search(norma)
    if not m:
        return None
    base = m.group(1).strip().lower()
    # Normalizar espaços múltiplos
    base = re.sub(r"\s+", " ", base)
    # Remover sufixo de ano (":2022", ":2019", etc.)
    base = re.sub(r":\d{4}$", "", base)
    return base


def _build_valid_norm_bases(valid_norm_sources: set[str]) -> set[str]:
    """Pré-computa o conjunto de códigos base a partir das fontes válidas.

    Args:
        valid_norm_sources: Conjunto de normas válidas em lowercase.

    Returns:
        Conjunto de códigos base normalizados.
    """
    bases: set[str] = set()
    for src in valid_norm_sources:
        base = _extract_norm_base(src)
        if base:
            bases.add(base)
    return bases


def _find_matching_source(
    norma_base: str,
    valid_norm_sources: set[str],
    normas_aplicaveis: list[str],
    rag_sources: list[str],
) -> str | None:
    """Encontra a fonte válida mais completa que corresponde ao código base.

    Prioriza normas_aplicaveis (nome oficial) sobre RAG sources (podem
    ter extensão .pdf).

    Args:
        norma_base: Código base extraído da norma citada pelo LLM.
        valid_norm_sources: Conjunto de normas válidas em lowercase.
        normas_aplicaveis: Lista de normas do perfil (formato oficial).
        rag_sources: Lista de fontes do contexto RAG.

    Returns:
        Nome oficial da norma correspondente, ou ``None`` se não encontrado.
    """
    # Prioridade 1: normas_aplicaveis (nome mais completo/oficial)
    for na in normas_aplicaveis:
        na_base = _extract_norm_base(na)
        if na_base == norma_base:
            return na
    # Prioridade 2: RAG sources
    for src in rag_sources:
        src_base = _extract_norm_base(src)
        if src_base == norma_base:
            return src
    return None


# Tabela de keywords → padrão de norma para heurística do fallback.
# Cada tupla: (lista de keywords no texto da medida, regex de norma a priorizar).
_FALLBACK_NORM_KEYWORDS: list[tuple[list[str], str]] = [
    (["aterr", "elétric", "instalação elétrica", "nbr 5410", "5410"], r"nbr\s*5410"),
    (["nr-10", "nr 10", "segurança em instalações"], r"nr[\-\s]*10\b"),
    (["nr-20", "nr 20", "inflamáve", "combustíve"], r"nr[\-\s]*20\b"),
    (["inspeção", "inspecao", "manutenção", "manutencao"], r"60079[\-\s]*17"),
    (["classificação de área", "classificacao de area", "zona classificada"], r"60079[\-\s]*10"),
    (["equipamento ex", "invólucro", "involucro", "à prova de explosão"], r"60079[\-\s]*(0|1|31)"),
    (["ventila", "exaust"], r"nfpa\s*(68|69|654)"),
    (["poeira", "dust", "pó combustível"], r"nfpa\s*652"),
    (["detecção", "deteccao", "alarme", "sensor"], r"60079"),
    (["proteção contra incêndio", "proteção contra incendio", "spda"], r"nfpa"),
]


def _match_norma_for_fallback(
    medida_texto: str,
    normas_aplicaveis: list[str],
    normative_context: list | None = None,
) -> str | None:
    """Atribui a norma mais adequada a uma medida pelo texto, via heurística.

    Verifica keywords no texto da medida e retorna a norma correspondente
    da lista ``normas_aplicaveis`` ou do contexto RAG. Mantém a natureza
    determinística do fallback (sem chamadas externas).

    Args:
        medida_texto: Texto da medida/recomendação.
        normas_aplicaveis: Normas do perfil.
        normative_context: Trechos normativos RAG (opcional).

    Returns:
        Nome da norma correspondente ou ``None`` (usa default_norma).
    """
    texto_lower = medida_texto.lower()

    # Montar pool de normas candidatas (profile + RAG sources)
    pool: list[str] = list(normas_aplicaveis)
    if normative_context:
        for exc in normative_context:
            src = exc.source if hasattr(exc, "source") else str(exc)
            if src not in pool:
                pool.append(src)

    for keywords, norm_pattern in _FALLBACK_NORM_KEYWORDS:
        if any(kw in texto_lower for kw in keywords):
            # Procurar no pool a norma que faz match com o padrão
            for norma in pool:
                if re.search(norm_pattern, norma, re.IGNORECASE):
                    return norma

    # Se há contexto RAG, usar a fonte de maior relevância
    if normative_context:
        src = normative_context[0].source if hasattr(normative_context[0], "source") else None
        if src:
            return src

    return None


def _parse_json(raw: str) -> dict[str, Any] | None:
    """Parseia string JSON, lidando com blocos markdown ````` ```.

    Returns:
        Dicionário ou ``None`` se inválido.
    """
    from app.domain.services.json_utils import parse_llm_json
    return parse_llm_json(raw)


def _truncate(text: str, max_len: int) -> str:
    """Trunca texto adicionando ``…`` se exceder o limite."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _shrink_justificativas(
    justs: list[JustificativaTecnica],
    recs: list[RecomendacaoTecnica],
    max_total: int,
) -> list[JustificativaTecnica]:
    """Encurta textos das justificativas proporcionalmente até caber no limite.

    Estratégia: reduz o max de cada justificativa iterativamente.
    """
    # Calcular tamanho base (recs + overhead JSON)
    recs_data = [r.model_dump() for r in recs]
    base_size = len(json.dumps({"recomendacoes_tecnicas": recs_data}, ensure_ascii=False))
    overhead = 80  # chaves, colchetes, vírgulas extras
    available = max_total - base_size - overhead

    # Distribuir igualmente entre justificativas
    per_just = max(100, available // max(len(justs), 1))

    new_justs: list[JustificativaTecnica] = []
    for j in justs:
        texto = _truncate(j.texto, per_just)
        new_justs.append(JustificativaTecnica(numero=j.numero, texto=texto))

    return new_justs
