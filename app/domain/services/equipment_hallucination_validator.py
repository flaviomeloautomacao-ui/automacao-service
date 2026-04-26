"""Serviço de domínio — pós-validação de alucinações do LLM.

Detecta e corrige problemas de fidelidade na saída do LLM que passaram
pela validação estrutural (OV-01…OV-14):

  HV-01: Números inventados — valores numéricos sem evidência no contexto
  HV-02: Norma sem trecho — tipo "normativa" mas trecho_normativo vazio
  HV-03: Trecho fantasma — trecho_normativo que não corresponde a nenhum
         chunk RAG fornecido
  HV-04: Termos técnicos sem base — recomendação com conteúdo não rastreável

──────────────────────────────────────────────────────────────────────
 RESPONSABILIDADES
──────────────────────────────────────────────────────────────────────

 1. Receber um ``EquipmentLLMOutput`` já validado estruturalmente.
 2. Aplicar regras HV-01…HV-04 contra o ``EquipmentLLMInput`` original.
 3. Retornar output corrigido + lista de flags para logging/auditoria.

 **NÃO** faz: chamadas de rede, acesso a banco, chamadas ao LLM.
──────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

from loguru import logger

from app.domain.entities import (
    EquipmentLLMInput,
    EquipmentLLMOutput,
    JustificativaTecnica,
    RecomendacaoTecnica,
)


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Regex para detectar valores numéricos com unidades ou percentuais
_NUMERIC_PATTERN = re.compile(
    r"(?<!\[)"           # não depois de [  (evitar referências "[1]")
    r"(?<!\w)"           # não precedido por letra (evitar "NR-10")
    r"("
    r"\d+(?:[.,]\d+)?%"  # percentuais: 40%, 3,5%
    r"|"
    r"\d+(?:[.,]\d+)?\s*(?:m\b|mm\b|cm\b|km\b|m²|m³)"  # distâncias/áreas
    r"|"
    r"\d+(?:[.,]\d+)?\s*(?:°C|°F|K\b)"                   # temperaturas
    r"|"
    r"\d+(?:[.,]\d+)?\s*(?:bar\b|Pa\b|kPa\b|MPa\b|atm\b|psi\b)"  # pressões
    r"|"
    r"\d+(?:[.,]\d+)?\s*(?:g/m³|mg/m³|kg/m³|ppm\b)"     # concentrações
    r"|"
    r"\d+(?:[.,]\d+)?\s*(?:L/min|m³/h|m³/s|L/s)"         # vazões
    r"|"
    r"\d+(?:[.,]\d+)?\s*(?:kW\b|MW\b|W\b|HP\b|CV\b|kVA\b)"  # potência
    r"|"
    r"\d+(?:[.,]\d+)?\s*(?:V\b|kV\b|A\b|mA\b)"             # elétrica
    r")",
    re.IGNORECASE,
)

# Threshold para fuzzy match de trecho normativo
_FUZZY_THRESHOLD = 0.75

# Palavras a ignorar ao extrair termos-chave (stopwords pt-BR técnicas)
_STOPWORDS = frozenset({
    "a", "à", "ao", "aos", "as", "até", "com", "como", "da", "das", "de",
    "del", "do", "dos", "e", "é", "em", "entre", "era", "essa", "esse",
    "esta", "este", "eu", "foi", "for", "há", "isso", "isto", "já", "lhe",
    "mais", "mas", "me", "meu", "na", "nas", "não", "nem", "no", "nos",
    "num", "numa", "nuns", "numas", "o", "os", "ou", "para", "pela",
    "pelas", "pelo", "pelos", "por", "qual", "quando", "que", "quem",
    "são", "se", "sem", "ser", "seu", "sua", "suas", "seus", "só",
    "também", "te", "ter", "tu", "tua", "tuas", "teu", "teus", "um",
    "uma", "umas", "uns", "você", "vos",
    # Termos técnicos genéricos que não são indicativos de alucinação
    "deve", "devem", "deverá", "conforme", "acordo", "aplicável",
    "equipamento", "sistema", "recomendação", "implementar", "realizar",
    "instalar", "adequar", "revisar", "verificar", "garantir",
})


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------


@dataclass
class HallucinationFlag:
    """Flag individual de possível alucinação."""

    rule: str                   # "HV-01", "HV-02", etc.
    rec_numero: int             # número da recomendação afetada
    detail: str                 # descrição do problema
    action: str                 # "cleaned" | "reclassified" | "warning"


@dataclass
class HallucinationResult:
    """Resultado da validação de alucinações."""

    output: EquipmentLLMOutput
    flags: list[HallucinationFlag] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return len(self.flags) > 0


# ---------------------------------------------------------------------------
# Funções públicas
# ---------------------------------------------------------------------------


def validate_hallucinations(
    output: EquipmentLLMOutput,
    llm_input: EquipmentLLMInput,
) -> HallucinationResult:
    """Aplica regras HV-01…HV-04 ao output validado do LLM.

    Corrige problemas quando possível, logga flags para auditoria.

    Args:
        output: Output já validado por OV-01…OV-14.
        llm_input: Input original do equipamento.

    Returns:
        ``HallucinationResult`` com output (possivelmente corrigido) e flags.
    """
    equip = llm_input.equipment_name
    flags: list[HallucinationFlag] = []

    # Montar corpus de referência (todo o texto disponível como contexto)
    reference_corpus = _build_reference_corpus(llm_input)

    # Montar textos dos trechos normativos RAG
    rag_texts = [exc.text for exc in llm_input.normative_context]

    new_recs: list[RecomendacaoTecnica] = []

    for rec in output.recomendacoes_tecnicas:
        corrected_rec = rec
        rec_flags: list[HallucinationFlag] = []

        # ── HV-01: Números inventados ─────────────────────────────
        hv01_flags = _check_invented_numbers(rec, reference_corpus, rag_texts, equip)
        rec_flags.extend(hv01_flags)

        # Se números inventados detectados, limpar do texto
        if hv01_flags:
            cleaned_text = _clean_invented_numbers(rec.texto, reference_corpus, rag_texts)
            if cleaned_text != rec.texto:
                corrected_rec = RecomendacaoTecnica(
                    numero=rec.numero,
                    texto=cleaned_text,
                    norma_referencia=rec.norma_referencia,
                    tipo=rec.tipo,
                    trecho_normativo=rec.trecho_normativo,
                )
                for f in hv01_flags:
                    f.action = "cleaned"

        # ── HV-02: Norma sem trecho ──────────────────────────────
        if corrected_rec.tipo == "normativa" and not corrected_rec.trecho_normativo:
            rec_flags.append(HallucinationFlag(
                rule="HV-02",
                rec_numero=rec.numero,
                detail="Tipo 'normativa' sem trecho_normativo",
                action="reclassified",
            ))
            corrected_rec = RecomendacaoTecnica(
                numero=corrected_rec.numero,
                texto=corrected_rec.texto,
                norma_referencia=corrected_rec.norma_referencia,
                tipo="boa_pratica",
                trecho_normativo=None,
            )

        # ── HV-03: Trecho fantasma ───────────────────────────────
        if corrected_rec.tipo == "normativa" and corrected_rec.trecho_normativo:
            if not _trecho_matches_rag(corrected_rec.trecho_normativo, rag_texts):
                rec_flags.append(HallucinationFlag(
                    rule="HV-03",
                    rec_numero=rec.numero,
                    detail=f"Trecho não encontrado nos chunks RAG: '{corrected_rec.trecho_normativo[:80]}...'",
                    action="reclassified",
                ))
                corrected_rec = RecomendacaoTecnica(
                    numero=corrected_rec.numero,
                    texto=corrected_rec.texto,
                    norma_referencia=corrected_rec.norma_referencia,
                    tipo="boa_pratica",
                    trecho_normativo=None,
                )

        # ── HV-04: Termos sem base (warning only) ────────────────
        hv04_flag = _check_terms_without_basis(
            corrected_rec, reference_corpus, rag_texts, equip,
        )
        if hv04_flag:
            rec_flags.extend(hv04_flag)

        new_recs.append(corrected_rec)
        flags.extend(rec_flags)

    # Log resumo
    if flags:
        for f in flags:
            logger.warning(
                "Hallucination {} | equip={} | rec={} | {} | action={}",
                f.rule, equip, f.rec_numero, f.detail, f.action,
            )
        logger.info(
            "Hallucination validation | equip={} | flags={}",
            equip, len(flags),
        )

    new_output = EquipmentLLMOutput(
        recomendacoes_tecnicas=new_recs,
        justificativas_tecnicas=list(output.justificativas_tecnicas),
    )

    return HallucinationResult(output=new_output, flags=flags)


# ---------------------------------------------------------------------------
# HV-01: Números inventados
# ---------------------------------------------------------------------------


def _build_reference_corpus(llm_input: EquipmentLLMInput) -> str:
    """Constrói um corpus concatenado de todo o contexto disponível."""
    parts: list[str] = []

    # Contexto do equipamento
    parts.append(llm_input.equipment_name)
    parts.append(llm_input.descricao_da_operacao)
    parts.extend(llm_input.identificacao_dos_perigos)
    parts.extend(llm_input.causas_possiveis)
    parts.extend(llm_input.consequencias_potenciais)
    parts.extend(llm_input.medidas_preventivas_existentes)
    parts.extend(llm_input.medidas_a_implementar)

    # Classificação de risco
    r = llm_input.classificacao_do_risco
    parts.extend([r.categoria_severidade, r.categoria_probabilidade, r.classificacao_risco])

    # Trechos normativos RAG
    for exc in llm_input.normative_context:
        parts.append(exc.text)

    # Trechos de literatura
    for exc in llm_input.literature_context:
        parts.append(exc.text)

    return " ".join(p for p in parts if p)


def _check_invented_numbers(
    rec: RecomendacaoTecnica,
    reference_corpus: str,
    rag_texts: list[str],
    equip: str,
) -> list[HallucinationFlag]:
    """Detecta valores numéricos no texto da recomendação que não existem no contexto."""
    flags: list[HallucinationFlag] = []
    matches = _NUMERIC_PATTERN.findall(rec.texto)

    for match in matches:
        # Extrair apenas os dígitos + unidade para busca
        match_clean = match.strip()

        # Verificar se o valor aparece no corpus de referência
        if match_clean in reference_corpus:
            continue

        # Verificar sem espaço entre número e unidade
        match_no_space = re.sub(r"\s+", "", match_clean)
        if any(match_no_space in re.sub(r"\s+", "", txt) for txt in [reference_corpus] + rag_texts):
            continue

        # Extrair apenas o número para verificar
        num_match = re.search(r"(\d+(?:[.,]\d+)?)", match_clean)
        if num_match:
            num_str = num_match.group(1)
            # Valores muito genéricos (1, 2, 3, 100) — ignorar
            try:
                val = float(num_str.replace(",", "."))
                if val in (1, 2, 3, 0):
                    continue
            except ValueError:
                pass
            # Verificar se o número (sem unidade) aparece no contexto
            if num_str in reference_corpus:
                continue

        flags.append(HallucinationFlag(
            rule="HV-01",
            rec_numero=rec.numero,
            detail=f"Valor numérico '{match_clean}' não encontrado no contexto",
            action="warning",
        ))

    return flags


def _clean_invented_numbers(
    texto: str,
    reference_corpus: str,
    rag_texts: list[str],
) -> str:
    """Remove/substitui números inventados no texto da recomendação."""

    def _replace_match(m: re.Match) -> str:
        match_text = m.group(0).strip()
        # Se o valor existe no contexto, manter
        if match_text in reference_corpus:
            return m.group(0)
        match_no_space = re.sub(r"\s+", "", match_text)
        if any(match_no_space in re.sub(r"\s+", "", txt) for txt in [reference_corpus] + rag_texts):
            return m.group(0)
        # Substituir por expressão genérica
        return "conforme parâmetros da norma aplicável"

    return _NUMERIC_PATTERN.sub(_replace_match, texto)


# ---------------------------------------------------------------------------
# HV-03: Trecho fantasma
# ---------------------------------------------------------------------------


def _trecho_matches_rag(trecho: str, rag_texts: list[str]) -> bool:
    """Verifica se o trecho normativo corresponde a algum chunk RAG.

    Usa fuzzy matching (SequenceMatcher) com threshold configurável.
    """
    if not rag_texts:
        return False

    trecho_clean = _normalize_for_comparison(trecho)
    if len(trecho_clean) < 20:
        # Trecho muito curto — aceitar se for substring
        return any(trecho_clean in _normalize_for_comparison(t) for t in rag_texts)

    for rag_text in rag_texts:
        rag_clean = _normalize_for_comparison(rag_text)

        # Substring exata (caso ideal)
        if trecho_clean in rag_clean:
            return True

        # Fuzzy match em sliding windows do tamanho do trecho
        trecho_len = len(trecho_clean)
        if trecho_len <= len(rag_clean):
            # Verificar em janelas do texto RAG
            best_ratio = 0.0
            step = max(1, trecho_len // 4)
            for start in range(0, len(rag_clean) - trecho_len + 1, step):
                window = rag_clean[start:start + trecho_len]
                ratio = SequenceMatcher(None, trecho_clean, window).ratio()
                best_ratio = max(best_ratio, ratio)
                if best_ratio >= _FUZZY_THRESHOLD:
                    return True
        else:
            # Trecho maior que o chunk RAG — comparar o chunk inteiro
            ratio = SequenceMatcher(None, trecho_clean, rag_clean).ratio()
            if ratio >= _FUZZY_THRESHOLD:
                return True

    return False


def _normalize_for_comparison(text: str) -> str:
    """Normaliza texto para comparação fuzzy."""
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[""''\"']", "", text)
    return text


# ---------------------------------------------------------------------------
# HV-04: Termos sem base
# ---------------------------------------------------------------------------


def _check_terms_without_basis(
    rec: RecomendacaoTecnica,
    reference_corpus: str,
    rag_texts: list[str],
    equip: str,
) -> list[HallucinationFlag]:
    """Verifica se os termos-chave da recomendação aparecem no contexto.

    Warning-only — não bloqueia, pois termos técnicos legítimos podem
    não aparecer literalmente no contexto.
    """
    # Extrair termos-chave (palavras com ≥ 4 chars, excluindo stopwords)
    words = re.findall(r"[a-záàâãéêíóôõúüç]{4,}", rec.texto.lower())
    key_terms = [w for w in words if w not in _STOPWORDS and len(w) >= 5]

    if not key_terms:
        return []

    full_corpus = (reference_corpus + " " + " ".join(rag_texts)).lower()

    found = sum(1 for term in key_terms if term in full_corpus)
    total = len(key_terms)

    if total == 0:
        return []

    coverage = found / total

    if coverage < 0.4:
        return [HallucinationFlag(
            rule="HV-04",
            rec_numero=rec.numero,
            detail=f"Cobertura de termos no contexto: {coverage:.0%} ({found}/{total})",
            action="warning",
        )]

    return []
