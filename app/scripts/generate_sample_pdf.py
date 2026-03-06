"""Gera um PDF de exemplo com dados fictícios para teste local.

Uso::

    python -m app.scripts.generate_sample_pdf

O arquivo será salvo em ``output/sample_report.pdf`` na raiz do projeto.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# Garante que o diretório raiz do projeto esteja no sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.adapters.pdf.renderer import WeasyPdfRenderer  # noqa: E402
from app.adapters.llm.prompts import get_profile_config  # noqa: E402
from app.application.use_cases.process_upload import group_rows_by_equipment  # noqa: E402

# Perfil usado no exemplo (altere para "gas" ou "vapors" para testar outros)
_SAMPLE_PROFILE = "dust"


def _build_metadata() -> dict:
    """Retorna metadados fictícios da empresa."""
    return {
        "razao_social": "Indústria Metalmec Ltda.",
        "cnpj": "12.345.678/0001-99",
        "site": "Planta Campinas — Unidade II",
        "endereco": "Rod. Anhanguera, km 112 — Campinas/SP",
        "responsavel": "Eng. Carlos A. Ferreira",
        "registro_profissional": "CREA-SP 123456",
        "elaboracao": "Konis Safety Engenharia",
        "local_vistoriado": "Galpão de Usinagem e Linha de Montagem",
        "contrato": "CT-2026/001",
        "data_avaliacao": "15/01/2026",
        "data_geracao": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }


def _build_rows() -> list[dict]:
    """Retorna linhas de risco fictícias (simulando MachineRiskRow)."""
    return [
        {
            "equipamento": "Torno CNC TN-400",
            "descricao_equipamento": "Torno de bancada com acionamento CNC",
            "riscos": "Mecânico",
            "perigo": "Contato com partes móveis (placa, castanhas)",
            "causas": "Ausência de proteção fixa na zona de trabalho",
            "consequencias": "Amputação de dedos ou mãos",
            "categoria_severidade": "IV — Catastrófica",
            "categoria_risco": "Intolerável",
            "medidas_existentes": "Nenhuma",
            "medidas_implementar": "Instalar proteção fixa com intertravamento e monitorar abertura via CLP de segurança.",
            "observacoes": None,
        },
        {
            "equipamento": "Fresadora Universal FU-3",
            "descricao_equipamento": "Fresadora universal de 3 eixos",
            "riscos": "Mecânico",
            "perigo": "Projeção de cavacos e fragmentos",
            "causas": "Falta de anteparo protetor na zona de corte",
            "consequencias": "Lesão ocular grave",
            "categoria_severidade": "III — Alta",
            "categoria_risco": "Substancial",
            "medidas_existentes": "Óculos de proteção fornecidos",
            "medidas_implementar": "Instalar proteção transparente em policarbonato na região de corte.",
            "observacoes": None,
        },
        {
            "equipamento": "Prensa Hidráulica PH-150",
            "descricao_equipamento": "Prensa hidráulica 150 toneladas",
            "riscos": "Mecânico",
            "perigo": "Esmagamento entre matrizes",
            "causas": "Acionamento bimanual sem sincronia monitorada",
            "consequencias": "Esmagamento de mãos / amputação",
            "categoria_severidade": "IV — Catastrófica",
            "categoria_risco": "Intolerável",
            "medidas_existentes": "Comando bimanual simples",
            "medidas_implementar": "Substituir comando bimanual por modelo tipo IIIC com monitoração por relé de segurança.",
            "observacoes": "Equipamento possui mais de 20 anos sem retrofit.",
        },
        {
            "equipamento": "Guilhotina Hidráulica GH-3000",
            "descricao_equipamento": "Guilhotina hidráulica para chapas",
            "riscos": "Mecânico",
            "perigo": "Acesso à zona de corte pela lateral",
            "causas": "Proteção lateral ausente / removida",
            "consequencias": "Corte / amputação de membros superiores",
            "categoria_severidade": "III — Alta",
            "categoria_risco": "Substancial",
            "medidas_existentes": "Nenhuma",
            "medidas_implementar": "Reinstalar proteção lateral fixa e adicionar sensor de presença AOPD.",
            "observacoes": None,
        },
        {
            "equipamento": "Esteira Transportadora ET-01",
            "descricao_equipamento": "Esteira de transporte de peças — linha montagem",
            "riscos": "Mecânico",
            "perigo": "Arraste / ponto de convergência nos roletes",
            "causas": "Rolete de retorno exposto e sem proteção",
            "consequencias": "Arraste de roupas soltas, escoriações graves",
            "categoria_severidade": "II — Média",
            "categoria_risco": "Moderado",
            "medidas_existentes": "Sinalização de alerta",
            "medidas_implementar": "Instalar proteção fixa nos pontos de convergência dos roletes de retorno.",
            "observacoes": None,
        },
        {
            "equipamento": "Parafusadeira Pneumática PP-12",
            "descricao_equipamento": "Parafusadeira pneumática portátil",
            "riscos": "Físico / Ergonômico",
            "perigo": "Vibração excessiva em mãos e braços",
            "causas": "Ferramenta sem sistema anti-vibração; uso prolongado",
            "consequencias": "Doença ocupacional (síndrome vibratória)",
            "categoria_severidade": "I — Baixa",
            "categoria_risco": "Tolerável",
            "medidas_existentes": "Rodízio de postos",
            "medidas_implementar": "Substituir ferramenta por modelo com isolamento anti-vibração e limitar jornada de uso.",
            "observacoes": None,
        },
        {
            "equipamento": "Ponte Rolante PR-10t",
            "descricao_equipamento": "Ponte rolante 10 toneladas — galpão manutenção",
            "riscos": "Mecânico / Queda",
            "perigo": "Queda de carga suspensa",
            "causas": "Ausência de inspeção periódica de cabos e gancho",
            "consequencias": "Esmagamento, óbito",
            "categoria_severidade": "IV — Catastrófica",
            "categoria_risco": "Intolerável",
            "medidas_existentes": "Inspeção visual eventual",
            "medidas_implementar": "Implementar plano de inspeção trimestral com ensaio de carga e substituição preventiva de cabos.",
            "observacoes": "Último ensaio de carga realizado há mais de 2 anos.",
        },
        {
            "equipamento": "Cabine de Pintura CP-02",
            "descricao_equipamento": "Cabine de pintura industrial com exaustão",
            "riscos": "Químico / Incêndio",
            "perigo": "Incêndio / explosão por acúmulo de vapores orgânicos",
            "causas": "Sistema de exaustão com vazão insuficiente",
            "consequencias": "Queimaduras, destruição patrimonial",
            "categoria_severidade": "III — Alta",
            "categoria_risco": "Substancial",
            "medidas_existentes": "Exaustão parcial operante",
            "medidas_implementar": "Adequar sistema de exaustão conforme projeto e instalar detector de gases inflamáveis.",
            "observacoes": None,
        },
    ]


def _build_llm_sections() -> dict[str, str]:
    """Retorna seções simuladas como se tivessem sido geradas por LLM."""
    return {
        "introducao": (
            "Este relatório técnico tem como finalidade apresentar os resultados "
            "da Análise de Perigos por Poeira Combustível (DHA — Dust Hazard Analysis) "
            "realizada nas dependências da empresa Indústria Metalmec Ltda., "
            "unidade Planta Campinas — Unidade II, conforme vistoria realizada em 15/01/2026.\n\n"
            "O objetivo principal é identificar os cenários de risco associados à "
            "presença de poeiras combustíveis, avaliar a severidade e a probabilidade "
            "de ocorrência de eventos adversos (incêndio e explosão) e propor medidas "
            "de prevenção e mitigação baseadas nas normas NFPA 652, NFPA 654, "
            "NFPA 68, NFPA 69 e na série ABNT NBR IEC 60079.\n\n"
            "A análise abrange o Galpão de Usinagem e a Linha de Montagem, com foco "
            "em 8 equipamentos inventariados no levantamento de campo."
        ),
        "materiais": (
            "A unidade avaliada processa materiais metálicos (aço carbono, alumínio "
            "e ligas) que geram poeiras durante operações de usinagem, corte e "
            "acabamento superficial.\n\n"
            "De acordo com a literatura técnica (dados de referência NFPA 652), "
            "poeiras metálicas apresentam as seguintes propriedades típicas de "
            "explosividade:\n\n"
            "• Alumínio: Kst = 300–700 bar·m/s; Pmax = 11–13 bar; MIE < 10 mJ\n"
            "• Ferro / Aço: Kst = 50–100 bar·m/s; Pmax = 5–7 bar; MIE > 100 mJ\n"
            "• Ligas de magnésio: Kst = 400–800 bar·m/s; Pmax = 15–17 bar; MIE < 5 mJ\n\n"
            "Nota: os valores acima são dados de referência da literatura e devem "
            "ser confirmados por ensaios laboratoriais específicos para os materiais "
            "presentes na planta.\n\n"
            "As poeiras de alumínio e ligas leves representam o maior risco de "
            "explosão (Classe ST-2 a ST-3), enquanto poeiras ferrosas possuem "
            "menor sensibilidade mas ainda requerem controle adequado de fontes "
            "de ignição e acúmulo."
        ),
        "metodologia": (
            "A avaliação foi conduzida com base na metodologia de identificação de "
            "perigos e avaliação de riscos estabelecida pela NFPA 652:2022, conforme "
            "as seguintes etapas:\n\n"
            "1. Levantamento dos materiais e substâncias processados na unidade\n"
            "2. Identificação das áreas críticas com potencial de formação de "
            "atmosferas explosivas por poeira combustível\n"
            "3. Inspeção técnica em campo, avaliando condições de housekeeping, "
            "fontes de ignição e sistemas de contenção\n"
            "4. Avaliação dos sistemas de proteção e detecção existentes\n"
            "5. Classificação do risco por equipamento (severidade × probabilidade)\n"
            "6. Geração de recomendações técnicas priorizadas por nível de risco\n\n"
            "Para cada equipamento, a severidade foi classificada em 4 categorias "
            "(I — Baixa a IV — Catastrófica) e o risco combinado em 5 faixas "
            "(Trivial, Tolerável, Moderado, Substancial, Intolerável), conforme "
            "matriz de risco adaptada da NFPA 652 e ABNT NBR IEC 60079-10-2."
        ),
        "conclusao": (
            "Com base na análise realizada em 8 equipamentos da Planta Campinas — "
            "Unidade II, conclui-se que:\n\n"
            "• 2 equipamentos apresentam risco INTOLERÁVEL e requerem intervenção "
            "imediata (Torno CNC TN-400 e Prensa Hidráulica PH-150)\n"
            "• 3 equipamentos apresentam risco SUBSTANCIAL e devem ser tratados "
            "em até 180 dias\n"
            "• 1 equipamento apresenta risco MODERADO com ação programada\n"
            "• 2 equipamentos apresentam risco TOLERÁVEL requerendo melhoria contínua\n\n"
            "Recomenda-se a implementação imediata das medidas indicadas para os "
            "itens de risco intolerável, seguida de um cronograma de adequação "
            "para os demais itens, com prazo máximo de 90 dias para riscos "
            "substanciais e 180 dias para moderados.\n\n"
            "A empresa deve manter programa de inspeção contínua e revisão "
            "periódica desta análise, conforme NFPA 652 (mínimo a cada 3 anos "
            "ou quando houver mudanças significativas nas operações)."
        ),
    }


def main() -> None:
    """Gera o PDF de exemplo e salva em ``output/sample_report.pdf``."""
    output_dir = _PROJECT_ROOT / "output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "sample_report.pdf"

    renderer = WeasyPdfRenderer()

    metadata = _build_metadata()
    rows = _build_rows()
    llm_sections = _build_llm_sections()

    # Agrupar equipamentos para análise individual
    equipments = group_rows_by_equipment(rows)
    profile_config = get_profile_config(_SAMPLE_PROFILE)

    print(f"Perfil: {profile_config['label']}")
    print(f"Equipamentos agrupados: {len(equipments)}")

    print("Renderizando HTML…")
    html = renderer.render_html(
        metadata=metadata,
        rows=rows,
        llm_sections=llm_sections,
        equipments=equipments,
        profile_config=profile_config,
    )

    print("Gerando PDF…")
    pdf_bytes = renderer.render(html)

    output_path.write_bytes(pdf_bytes)
    print(f"PDF gerado com sucesso: {output_path}  ({len(pdf_bytes):,} bytes)")


if __name__ == "__main__":
    main()
