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


def _build_metadata() -> dict:
    """Retorna metadados fictícios da empresa."""
    return {
        "razao_social": "Indústria Metalmec Ltda.",
        "cnpj": "12.345.678/0001-99",
        "site": "Planta Campinas — Unidade II",
        "endereco": "Rod. Anhanguera, km 112 — Campinas/SP",
        "responsavel": "Eng. Carlos A. Ferreira — CREA-SP 123456",
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
        "introducao": "",  # vazio → usa texto padrão do template
        "metodologia": "",  # vazio → usa texto padrão do template
        "recomendacoes": """
<p>Com base na análise completa dos equipamentos inventariados, recomenda-se:</p>
<ol>
  <li><strong>Prioridade Urgente:</strong> Adequação imediata dos sistemas de proteção do Torno CNC TN-400,
      da Prensa Hidráulica PH-150 e implementação do plano de inspeção da Ponte Rolante PR-10t.
      Esses itens apresentam risco <em>intolerável</em> com potencial de lesões fatais ou amputações.</li>
  <li><strong>Prioridade Alta:</strong> Instalação de proteções na Fresadora Universal FU-3,
      na Guilhotina Hidráulica GH-3000 e adequação da exaustão da Cabine de Pintura CP-02.</li>
  <li><strong>Prioridade Média:</strong> Proteção dos pontos de convergência da Esteira Transportadora ET-01.</li>
  <li><strong>Prioridade Baixa:</strong> Substituição da Parafusadeira Pneumática PP-12 por modelo com isolamento anti-vibração.</li>
</ol>
<p>Recomenda-se cronograma de implementação não superior a <strong>90 dias</strong> para itens urgentes e
   <strong>180 dias</strong> para itens de alta prioridade.</p>
""",
        "justificativas": """
<p>As justificativas técnicas para as recomendações apresentadas baseiam-se nos seguintes fundamentos:</p>
<ul>
  <li>A NR-12 (Portaria MTE nº 916/2019) estabelece que máquinas e equipamentos devem possuir proteções
      que impeçam o acesso a zonas de perigo durante operação normal.</li>
  <li>A ABNT NBR ISO 12100:2013 define a hierarquia de medidas de proteção:
      eliminação do perigo → proteções / dispositivos de segurança → informação ao usuário.</li>
  <li>O critério de classificação de riscos utilizado (probabilidade × severidade) está alinhado
      à metodologia HRN (<em>Hazard Rating Number</em>), amplamente aceita para máquinas industriais.</li>
  <li>Equipamentos com acionamento bimanual devem atender a ABNT NBR 14152 (tipo IIIC) para prensas e similares,
      com monitoração por relé de segurança categoria 4.</li>
</ul>
""",
        "resumo": """
<p>Foram avaliados <strong>8 equipamentos</strong> distribuídos em 5 áreas da planta Campinas — Unidade II.
   A análise identificou:</p>
<ul>
  <li><strong>3 itens com risco intolerável</strong> — exigem ação imediata.</li>
  <li><strong>3 itens com risco substancial</strong> — ação em até 180 dias.</li>
  <li><strong>1 item com risco moderado</strong> — ação programada.</li>
  <li><strong>1 item com risco tolerável</strong> — melhoria contínua.</li>
</ul>
<p>As recomendações priorizam a preservação da integridade física dos trabalhadores,
   o atendimento à legislação vigente (NR-12, NR-11, NR-20) e a redução dos passivos legais da organização.</p>
""",
        "referencias": "",  # vazio → usa lista padrão do template
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

    print("Renderizando HTML…")
    html = renderer.render_html(
        metadata=metadata,
        rows=rows,
        llm_sections=llm_sections,
    )

    print("Gerando PDF…")
    pdf_bytes = renderer.render(html)

    output_path.write_bytes(pdf_bytes)
    print(f"PDF gerado com sucesso: {output_path}  ({len(pdf_bytes):,} bytes)")


if __name__ == "__main__":
    main()
