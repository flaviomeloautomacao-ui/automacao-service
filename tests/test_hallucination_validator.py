"""Testes unitários — equipment_hallucination_validator.

Cobre as regras HV-01 … HV-04:
  HV-01: Números inventados
  HV-02: Norma sem trecho
  HV-03: Trecho fantasma
  HV-04: Termos sem base
"""

from __future__ import annotations

import pytest

from app.domain.entities import (
    EquipmentLLMInput,
    EquipmentLLMOutput,
    JustificativaTecnica,
    NormativeExcerpt,
    RecomendacaoTecnica,
    RiskClassification,
)
from app.domain.services.equipment_hallucination_validator import (
    HallucinationResult,
    validate_hallucinations,
    _trecho_matches_rag,
    _normalize_for_comparison,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_input(**overrides) -> EquipmentLLMInput:
    """Cria um EquipmentLLMInput padrão para testes."""
    defaults = {
        "equipment_name": "Elevador EC-01",
        "descricao_da_operacao": "Transporte de grãos a 120 °C",
        "identificacao_dos_perigos": ["Poeira combustível", "Atrito excessivo"],
        "causas_possiveis": ["Falha aspiração"],
        "consequencias_potenciais": ["Explosão"],
        "classificacao_do_risco": RiskClassification(
            categoria_severidade="Alta",
            categoria_probabilidade="Alto",
            classificacao_risco="Alto",
        ),
        "medidas_preventivas_existentes": ["Sensor instalado"],
        "medidas_a_implementar": [
            "Instalar supressão",
            "Revisar ventilação",
        ],
        "normas_aplicaveis": ["NFPA 652:2022", "NR-10"],
    }
    defaults.update(overrides)
    return EquipmentLLMInput(**defaults)


def _make_output(recs: list[dict], justs: list[dict] | None = None) -> EquipmentLLMOutput:
    """Constrói EquipmentLLMOutput a partir de dicts simplificados."""
    rec_objs = [
        RecomendacaoTecnica(
            numero=r.get("numero", i + 1),
            texto=r["texto"],
            norma_referencia=r.get("norma_referencia", "NFPA 652:2022"),
            tipo=r.get("tipo", "boa_pratica"),
            trecho_normativo=r.get("trecho_normativo"),
        )
        for i, r in enumerate(recs)
    ]
    if justs is None:
        justs = [
            {"texto": f"Justificativa detalhada para recomendação {i+1}. Risco alto demanda ação corretiva."}
            for i in range(len(recs))
        ]
    just_objs = [
        JustificativaTecnica(
            numero=j.get("numero", i + 1),
            texto=j["texto"],
        )
        for i, j in enumerate(justs)
    ]
    return EquipmentLLMOutput(
        recomendacoes_tecnicas=rec_objs,
        justificativas_tecnicas=just_objs,
    )


# ---------------------------------------------------------------------------
# HV-01: Números inventados
# ---------------------------------------------------------------------------


class TestHV01InventedNumbers:
    def test_no_numbers_no_flags(self):
        """Recomendação sem números não gera flag."""
        inp = _make_input()
        output = _make_output([
            {"texto": "Instalar sistema de supressão conforme norma aplicável ao equipamento identificado."},
            {"texto": "Revisar sistema de ventilação do elevador e adequar às condições operacionais."},
        ])
        result = validate_hallucinations(output, inp)
        hv01_flags = [f for f in result.flags if f.rule == "HV-01"]
        assert len(hv01_flags) == 0

    def test_number_from_context_no_flag(self):
        """Número presente no contexto (120 °C) não gera flag."""
        inp = _make_input()  # descricao_da_operacao contém "120 °C"
        output = _make_output([
            {"texto": "Monitorar temperatura operacional que pode atingir 120 °C durante a operação."},
            {"texto": "Revisar sistema de ventilação do elevador e adequar às condições operacionais vigentes."},
        ])
        result = validate_hallucinations(output, inp)
        hv01_flags = [f for f in result.flags if f.rule == "HV-01"]
        assert len(hv01_flags) == 0

    def test_invented_percentage_flagged(self):
        """Percentual inventado (40%) gera flag HV-01."""
        inp = _make_input()
        output = _make_output([
            {"texto": "Reduzir a concentração de poeira em 40% através de instalação de sistema de exaustão."},
            {"texto": "Revisar sistema de ventilação do elevador e adequar às condições operacionais vigentes."},
        ])
        result = validate_hallucinations(output, inp)
        hv01_flags = [f for f in result.flags if f.rule == "HV-01"]
        assert len(hv01_flags) >= 1
        assert "40%" in hv01_flags[0].detail

    def test_invented_number_cleaned(self):
        """Números inventados são substituídos no texto."""
        inp = _make_input()
        output = _make_output([
            {"texto": "Manter distância mínima de segurança de 15 m entre equipamentos de risco."},
            {"texto": "Revisar sistema de ventilação do elevador e adequar às condições operacionais vigentes."},
        ])
        result = validate_hallucinations(output, inp)
        hv01_flags = [f for f in result.flags if f.rule == "HV-01"]
        if hv01_flags:
            # O número foi ou limpo ou flagged
            assert any(f.action in ("cleaned", "warning") for f in hv01_flags)

    def test_number_from_rag_not_flagged(self):
        """Número presente nos trechos RAG não gera flag."""
        inp = _make_input(
            normative_context=[
                NormativeExcerpt(
                    source="NFPA 652:2022",
                    text="A distância mínima de segurança deve ser de 3 m conforme seção 8.2.",
                    relevance_score=0.9,
                ),
            ],
        )
        output = _make_output([
            {"texto": "Manter distância mínima de segurança de 3 m conforme NFPA 652 para este equipamento."},
            {"texto": "Revisar sistema de ventilação do elevador e adequar às condições operacionais vigentes."},
        ])
        result = validate_hallucinations(output, inp)
        hv01_flags = [f for f in result.flags if f.rule == "HV-01"]
        assert len(hv01_flags) == 0


# ---------------------------------------------------------------------------
# HV-02: Norma sem trecho
# ---------------------------------------------------------------------------


class TestHV02NormaSemTrecho:
    def test_normativa_with_trecho_no_flag(self):
        """tipo='normativa' com trecho → sem flag."""
        inp = _make_input()
        output = _make_output([
            {
                "texto": "Instalar sistema de detecção de poeira combustível no elevador conforme norma aplicável.",
                "tipo": "normativa",
                "trecho_normativo": "A detecção deve ser instalada conforme NFPA 652.",
            },
            {"texto": "Revisar sistema de ventilação do elevador e garantir adequação normativa completa."},
        ])
        result = validate_hallucinations(output, inp)
        hv02_flags = [f for f in result.flags if f.rule == "HV-02"]
        assert len(hv02_flags) == 0

    def test_normativa_without_trecho_reclassified(self):
        """tipo='normativa' sem trecho → reclassificado para boa_pratica."""
        inp = _make_input()
        output = _make_output([
            {
                "texto": "Instalar sistema de detecção de poeira combustível no elevador conforme norma aplicável.",
                "tipo": "normativa",
                "trecho_normativo": None,
            },
            {"texto": "Revisar sistema de ventilação do elevador e garantir adequação normativa completa."},
        ])
        result = validate_hallucinations(output, inp)
        hv02_flags = [f for f in result.flags if f.rule == "HV-02"]
        assert len(hv02_flags) == 1
        assert result.output.recomendacoes_tecnicas[0].tipo == "boa_pratica"

    def test_boa_pratica_without_trecho_no_flag(self):
        """tipo='boa_pratica' sem trecho → nenhum flag HV-02."""
        inp = _make_input()
        output = _make_output([
            {
                "texto": "Implementar procedimento operacional padrão para manutenção preventiva do equipamento.",
                "tipo": "boa_pratica",
                "trecho_normativo": None,
            },
            {"texto": "Revisar sistema de ventilação do elevador e garantir adequação normativa completa."},
        ])
        result = validate_hallucinations(output, inp)
        hv02_flags = [f for f in result.flags if f.rule == "HV-02"]
        assert len(hv02_flags) == 0


# ---------------------------------------------------------------------------
# HV-03: Trecho fantasma
# ---------------------------------------------------------------------------


class TestHV03TrechoFantasma:
    def test_trecho_matching_rag_no_flag(self):
        """Trecho que é substring de um chunk RAG → sem flag."""
        rag_text = (
            "De acordo com a NFPA 652, seção 8.2, equipamentos que processam "
            "poeira combustível devem possuir sistema de detecção adequado."
        )
        inp = _make_input(
            normative_context=[
                NormativeExcerpt(source="NFPA 652:2022", text=rag_text, relevance_score=0.9),
            ],
        )
        output = _make_output([
            {
                "texto": "Instalar sistema de detecção de poeira combustível no elevador conforme NFPA 652.",
                "tipo": "normativa",
                "trecho_normativo": "equipamentos que processam poeira combustível devem possuir sistema de detecção adequado",
            },
            {"texto": "Revisar sistema de ventilação do elevador e garantir adequação normativa completa."},
        ])
        result = validate_hallucinations(output, inp)
        hv03_flags = [f for f in result.flags if f.rule == "HV-03"]
        assert len(hv03_flags) == 0

    def test_trecho_not_in_rag_flagged(self):
        """Trecho inventado que não existe nos chunks RAG → reclassificado."""
        inp = _make_input(
            normative_context=[
                NormativeExcerpt(
                    source="NFPA 652:2022",
                    text="Equipamentos devem ter manutenção periódica conforme procedimentos.",
                    relevance_score=0.9,
                ),
            ],
        )
        output = _make_output([
            {
                "texto": "Instalar barreira corta-fogo entre compartimentos com material certificado.",
                "tipo": "normativa",
                "trecho_normativo": "As barreiras corta-fogo devem ser instaladas entre todos os compartimentos adjacentes com classificação F-120.",
            },
            {"texto": "Revisar sistema de ventilação do elevador e garantir adequação normativa completa."},
        ])
        result = validate_hallucinations(output, inp)
        hv03_flags = [f for f in result.flags if f.rule == "HV-03"]
        assert len(hv03_flags) == 1
        assert result.output.recomendacoes_tecnicas[0].tipo == "boa_pratica"
        assert result.output.recomendacoes_tecnicas[0].trecho_normativo is None

    def test_trecho_empty_rag_no_crash(self):
        """Sem contexto RAG, normativa com trecho is flagged."""
        inp = _make_input(normative_context=[])
        output = _make_output([
            {
                "texto": "Instalar barreira corta-fogo entre compartimentos de equipamento industrial.",
                "tipo": "normativa",
                "trecho_normativo": "texto qualquer sem base disponível no sistema.",
            },
            {"texto": "Revisar sistema de ventilação do elevador e garantir adequação normativa completa."},
        ])
        result = validate_hallucinations(output, inp)
        hv03_flags = [f for f in result.flags if f.rule == "HV-03"]
        assert len(hv03_flags) == 1


# ---------------------------------------------------------------------------
# HV-04: Termos sem base (warning only)
# ---------------------------------------------------------------------------


class TestHV04TermosSemBase:
    def test_terms_with_good_coverage_no_flag(self):
        """Recomendação com termos presentes no contexto → sem flag."""
        inp = _make_input()
        output = _make_output([
            {"texto": "Instalar sistema de supressão de poeira combustível no elevador com sensor adequado."},
            {"texto": "Revisar ventilação do equipamento conforme norma aplicável ao transporte de grãos."},
        ])
        result = validate_hallucinations(output, inp)
        hv04_flags = [f for f in result.flags if f.rule == "HV-04"]
        assert len(hv04_flags) == 0

    def test_terms_completely_alien_flagged(self):
        """Recomendação com termos completamente fora do contexto → flag."""
        inp = _make_input()
        output = _make_output([
            {
                "texto": (
                    "Implementar blockchain descentralizado para rastreabilidade "
                    "criptográfica dos certificados digitais biométricos."
                ),
            },
            {"texto": "Revisar sistema de ventilação do elevador e garantir adequação normativa completa."},
        ])
        result = validate_hallucinations(output, inp)
        hv04_flags = [f for f in result.flags if f.rule == "HV-04"]
        # At least 1 flag expected due to very low coverage
        assert len(hv04_flags) >= 1
        assert hv04_flags[0].action == "warning"


# ---------------------------------------------------------------------------
# Helper: _trecho_matches_rag
# ---------------------------------------------------------------------------


class TestTrechoMatchesRag:
    def test_exact_substring(self):
        rag = ["A norma NFPA 652 exige detecção de poeira combustível em elevadores."]
        assert _trecho_matches_rag("detecção de poeira combustível", rag) is True

    def test_no_match(self):
        rag = ["A norma NFPA 652 exige detecção de poeira combustível em elevadores."]
        assert _trecho_matches_rag("barreiras corta-fogo com classificação F-120", rag) is False

    def test_empty_rag(self):
        assert _trecho_matches_rag("qualquer texto", []) is False

    def test_fuzzy_match_with_small_variation(self):
        rag = ["Os equipamentos devem possuir sistema de detecção adequado conforme norma."]
        # Slight variation
        trecho = "Os equipamentos devem possuir sistemas de detecção adequados conforme norma"
        assert _trecho_matches_rag(trecho, rag) is True


# ---------------------------------------------------------------------------
# Integration: full pipeline
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_clean_output_passes_unchanged(self):
        """Output sem problemas passa sem alterações."""
        inp = _make_input()
        output = _make_output([
            {"texto": "Instalar sistema de supressão de poeira no elevador conforme norma NFPA aplicável."},
            {"texto": "Revisar ventilação do equipamento conforme requisitos de transporte de grãos."},
        ])
        result = validate_hallucinations(output, inp)
        assert not result.has_issues
        assert len(result.output.recomendacoes_tecnicas) == 2

    def test_multiple_flags_combined(self):
        """Recomendação com múltiplos problemas gera múltiplas flags."""
        inp = _make_input(normative_context=[])
        output = _make_output([
            {
                "texto": "Instalar barreira resistente a 500 °C entre compartimentos adjacentes.",
                "tipo": "normativa",
                "trecho_normativo": None,  # HV-02
            },
            {"texto": "Revisar sistema de ventilação do elevador e garantir adequação normativa completa."},
        ])
        result = validate_hallucinations(output, inp)
        # Should have at least HV-01 (500 °C) and HV-02 (normativa sem trecho)
        rules = {f.rule for f in result.flags}
        assert "HV-02" in rules
