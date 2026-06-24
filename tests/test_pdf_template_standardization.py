from __future__ import annotations

from pathlib import Path

from app.adapters.llm.prompts import get_profile_config
from app.adapters.pdf.renderer import WeasyPdfRenderer


def _renderer() -> WeasyPdfRenderer:
    return WeasyPdfRenderer()


def _base_metadata() -> dict:
    return {
        "razao_social": "Cliente Teste",
        "site": "Unidade Teste",
        "codigo_documento": "DOC-001",
        "art_numero": "ART-123",
    }


def test_dha_template_cover_footer_signature_and_images_are_standardized() -> None:
    html = _renderer().render_html(
        metadata=_base_metadata(),
        rows=[],
        llm_sections={
            "introducao": "Introducao.",
            "metodologia": "Metodologia.",
            "conclusao": "Conclusao.",
            "materiais": "",
        },
        equipments=[
            {
                "index": 1,
                "nome": "Filtro",
                "descricao": "Linha inicial.\n\nLinha seguinte.",
                "perigos": ["1. Poeira acumulada"],
                "causas": ["2 - Falha de limpeza"],
                "consequencias": ["Incendio"],
                "severidade": "Alto",
                "probabilidade": "Medio",
                "classificacao": "Alto",
                "classificacao_residual": "Baixo",
                "severidade_residual": "Baixo",
                "probabilidade_residual": "Baixo",
                "medidas_existentes": ["1) Inspecao"],
                "medidas_implementar": [],
                "recomendacoes_tecnicas": [],
                "justificativas_tecnicas": [],
                "images": [{"secure_url": "https://example.com/filtro.png"}],
            },
        ],
        profile_config=get_profile_config("dust"),
    )

    assert "Análise de Perigos por Poeira Combustível" not in html
    assert "Gerado em" not in html
    assert "cover-divider" not in html
    assert "Foto 1" not in html
    assert "<li>Poeira acumulada</li>" in html
    assert "<li>Falha de limpeza</li>" in html
    assert "Responsável Técnico:" in html
    assert "Francisco Flávio Melo Cavalcante" in html
    assert "CREA:" in html
    assert "CREA SP – 5060562076" in html
    assert "Konis Ex do Brasil Ltda." in html
    assert "Gomes de Carvalho, 1255, sobreloja, Vila Olímpia" in html
    assert "São Paulo/SP - CEP 04547-005" in html
    assert "+55 (11) 3046-3648" in html
    assert "flavio.cavalcante@konis.com.br" in html
    assert "ENDERECO OFICIAL DA KONIS PENDENTE DE CONFIRMACAO" not in html


def test_areas_template_uses_dha_visual_contract_and_signature() -> None:
    html = _renderer().render_html(
        metadata=_base_metadata(),
        rows=[],
        llm_sections={
            "introducao": "Introducao.",
            "escopo": "Escopo.",
            "consideracoes_gerais": "Consideracoes.",
            "metodologia": "Metodologia.",
            "recomendacoes": "1. Recomendacao geral.",
            "conclusao": "Conclusao.",
        },
        equipments=[
            {
                "index": 1,
                "area_local": "Area A",
                "area_descricao": "Descricao da area",
                "tag_referencias": ["TAG-1"],
                "substancias": ["Etanol"],
                "grupo": "IIA",
                "classe_temperatura": "T2",
                "epl": "Gb",
                "row_count": 1,
                "operational_notes": "1. Operacao normal.",
                "ventilation_premises": "2 - Ventilacao natural.",
                "images": [
                    {
                        "secure_url": "https://example.com/area.png",
                        "caption": "Foto 1",
                    },
                ],
                "fontes": [
                    {
                        "tag_referencia": "TAG-1",
                        "substancia": "Etanol",
                        "descricao": "Flange",
                        "grau": "Secundaria",
                        "ventilacao_tipo": "Natural",
                        "ventilacao_grau": "Medio",
                        "ventilacao_disponibilidade": "Boa",
                        "zona": "2",
                        "extensao": "1 m",
                        "grupo": "IIA",
                        "classe_temperatura": "T2",
                        "epl": "Gb",
                        "temperatura_processo": "25",
                        "pressao_processo": "101",
                        "volume_processo": "1",
                        "observacoes": "",
                    },
                ],
                "justificativa_zona": "Justificativa.",
                "analise_ventilacao": "Analise.",
                "recomendacoes_especificas": [
                    {"texto": "1. Inspecionar equipamentos.", "norma_referencia": "NBR"}
                ],
            },
        ],
        profile_config=get_profile_config("areas"),
        template_name="report_areas.html",
    )

    assert "Gerado em" not in html
    assert "cover-divider" not in html
    assert "Foto 1" not in html
    assert "Responsável Técnico:" in html
    assert "CREA:" in html
    assert "assinatura.png" in html
    assert "ART nº ART-123" in html
    assert "Konis Ex do Brasil Ltda." in html
    assert "Gomes de Carvalho, 1255, sobreloja, Vila Olímpia" in html
    assert "São Paulo/SP - CEP 04547-005" in html
    assert "+55 (11) 3046-3648" in html
    assert "flavio.cavalcante@konis.com.br" in html


def test_pdf_templates_keep_single_blue_token_and_no_dead_cover_classes() -> None:
    templates_dir = Path(__file__).resolve().parents[1] / "app/adapters/pdf/templates"
    text = "\n".join(
        (templates_dir / name).read_text(encoding="utf-8")
        for name in ("styles.css", "report.html", "report_areas.html")
    )

    for forbidden in ("#1a1a2e", "#2c3e50", "#0066cc", "#e94560"):
        assert forbidden not in text

    assert "cover-divider" not in text
    assert "cover-footer" not in text
    assert "photo-caption" not in text
    assert "figcaption" not in text


def test_dha_titles_follow_abnt_casing_and_no_italic() -> None:
    """Apontamentos 'Afinamento da automação DHA': ABNT em títulos + sem itálico."""
    templates_dir = Path(__file__).resolve().parents[1] / "app/adapters/pdf/templates"
    styles = (templates_dir / "styles.css").read_text(encoding="utf-8")
    report = (templates_dir / "report.html").read_text(encoding="utf-8")

    # Itálico removido dos seletores do CSS e das citações do relatório de equipamentos
    assert "font-style: italic" not in styles
    assert "<em>" not in report

    # Subtítulos de seção secundária (X.1) em CAIXA ALTA via CSS (apontamento 3)
    assert ".section > h3" in styles

    # Subtítulos nível 3 da apresentação em caixa de sentença (apontamento 2)
    assert "3.3 Como interpretar os resultados na prática" in report
    assert "1.4 Prevenção: controle de fontes de ignição" in report
    assert "COMO INTERPRETAR OS RESULTADOS NA PRÁTICA" not in report

    # Bloco de classificação de risco com subtítulos padronizados (apontamento 4)
    assert "risk-block-subtitle" in styles
    assert 'class="risk-block-subtitle"' in report
    assert "risk-block-subtitle residual-risk-title" in report


def test_post_process_renumbers_recommendations_contiguously() -> None:
    """Apontamento 5: numero do LLM com lacunas vira 1..N contíguo, preservando
    o pareamento recomendação↔justificativa, de forma idempotente."""
    from app.application.services.equipment_post_processor import (
        post_process_equipment,
    )

    eq = {
        "recomendacoes_tecnicas": [
            {"numero": 2, "texto": "Instalar sensor de temperatura", "norma_referencia": "NBR"},
            {"numero": 5, "texto": "Aterrar o equipamento", "norma_referencia": "NBR"},
            {"numero": 9, "texto": "Captar poeira no pe do elevador", "norma_referencia": "NBR"},
        ],
        "justificativas_tecnicas": [
            {"numero": 2, "texto": "Reduz ignicao por superficie quente"},
            {"numero": 5, "texto": "Evita eletricidade estatica"},
            {"numero": 9, "texto": "Reduz formacao de nuvem de poeira"},
        ],
    }

    out = post_process_equipment(eq)
    assert [r["numero"] for r in out["recomendacoes_tecnicas"]] == [1, 2, 3]
    # Justificativas remapeadas pelo mesmo mapa (2->1, 5->2, 9->3)
    assert [j["numero"] for j in out["justificativas_tecnicas"]] == [1, 2, 3]

    # Idempotente: rodar de novo não altera a numeração já contígua
    out2 = post_process_equipment(out)
    assert [r["numero"] for r in out2["recomendacoes_tecnicas"]] == [1, 2, 3]
    assert [j["numero"] for j in out2["justificativas_tecnicas"]] == [1, 2, 3]
