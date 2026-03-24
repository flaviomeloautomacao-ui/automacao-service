"""Gera um PDF com dados 100% mockados para teste de layout.

Uso::

    python -m app.scripts.generate_mock_pdf
    python -m app.scripts.generate_mock_pdf --profile gas
    python -m app.scripts.generate_mock_pdf --open

O arquivo é salvo em ``output/mock_report.pdf``.
Com ``--open`` o PDF é aberto automaticamente no visualizador padrão.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.adapters.pdf.renderer import WeasyPdfRenderer  # noqa: E402
from app.adapters.llm.prompts import get_profile_config  # noqa: E402


# ======================================================================
# METADADOS (capa, assinatura, etc.)
# ======================================================================

def _build_metadata() -> dict:
    return {
        "razao_social": "Bunge Alimentos S.A.",
        "cnpj": "84.046.101/0093-40",
        "site": "Unidade São Francisco do Sul — SC",
        "endereco": "Rod. BR-280, km 8 — São Francisco do Sul/SC",
        "responsavel": "Eng. Roberto M. Nascimento",
        "registro_profissional": "CREA-SC 098765/D",
        "elaboracao": "Konis Safety Engenharia",
        "local_vistoriado": "Planta de Processamento de Grãos e Silos",
        "contrato": "CT-2026/042",
        "data_avaliacao": "10/02/2026",
        "data_geracao": datetime.now().strftime("%d/%m/%Y %H:%M"),
        # Novos campos para capa e controle de revisões
        "codigo_documento": "REL-DHA-BUNGE-SFS-2026",
        "revisao": "00",
        "art_numero": "SC20260001234567",
        "data_emissao": "15/02/2026",
        "cover_image_url": None,  # Sem imagem de capa no mock (fallback)
        "revisions": [
            {
                "version": "00",
                "date": "15/02/2026",
                "author": "Konis Safety Engenharia",
                "description": "Emissão inicial",
            },
        ],
    }


# ======================================================================
# LINHAS DE RISCO (rows) — usadas no Anexo / Inventário
# ======================================================================

def _build_rows() -> list[dict]:
    return [
        {
            "equipamento": "Elevador de Canecas EC-01",
            "descricao_equipamento": "Elevador de canecas para transporte vertical de grãos (soja/milho) — capacidade 120 t/h",
            "riscos": "Explosão de poeira",
            "perigo": "Acúmulo de poeira combustível no interior do elevador (pé e cabeça)",
            "causas": "Falha no sistema de aspiração; desgaste das canecas; atrito correia/tambor",
            "consequencias": "Explosão primária com propagação para equipamentos conectados",
            "categoria_severidade": "IV — Catastrófica",
            "categoria_risco": "Intolerável",
            "medidas_existentes": "Sistema de aspiração centralizado operante",
            "medidas_implementar": "Instalar sensores de alinhamento de correia e monitoramento de temperatura nos mancais.",
            "observacoes": "Último alinhamento realizado há 14 meses.",
        },
        {
            "equipamento": "Elevador de Canecas EC-01",
            "descricao_equipamento": "Elevador de canecas para transporte vertical de grãos (soja/milho) — capacidade 120 t/h",
            "riscos": "Incêndio",
            "perigo": "Atrito correia/tambor gerando fonte de ignição",
            "causas": "Desalinhamento de correia sem sensor de detecção",
            "consequencias": "Incêndio interno com danos estruturais e risco de propagação",
            "categoria_severidade": "IV — Catastrófica",
            "categoria_risco": "Intolerável",
            "medidas_existentes": "Sistema de aspiração centralizado operante",
            "medidas_implementar": "Implementar sistema de detecção de desalinhamento com shutdown automático.",
            "observacoes": None,
        },
        {
            "equipamento": "Transportador Redler TR-03",
            "descricao_equipamento": "Transportador tipo redler horizontal para farelo de soja — 80 t/h",
            "riscos": "Explosão de poeira",
            "perigo": "Geração de poeira em suspensão nos pontos de transferência",
            "causas": "Vedação insuficiente nas juntas; acúmulo em superfícies internas",
            "consequencias": "Explosão confinada no interior do transportador",
            "categoria_severidade": "III — Alta",
            "categoria_risco": "Substancial",
            "medidas_existentes": "Vedação com borracha nos pontos de carga",
            "medidas_implementar": "Substituir vedações por modelo pressurizado e instalar bocais de aspiração nos pontos de transferência.",
            "observacoes": None,
        },
        {
            "equipamento": "Silo de Armazenamento SA-12",
            "descricao_equipamento": "Silo metálico vertical para armazenamento de milho — 5.000 t",
            "riscos": "Explosão de poeira",
            "perigo": "Formação de nuvem de poeira durante carga/descarga do silo",
            "causas": "Queda livre de grãos sem defletor; ventilação natural insuficiente",
            "consequencias": "Explosão no topo do silo com colapso estrutural",
            "categoria_severidade": "IV — Catastrófica",
            "categoria_risco": "Intolerável",
            "medidas_existentes": "Bocal de aspiração no topo (subdimensionado)",
            "medidas_implementar": "Redimensionar sistema de aspiração do topo; instalar válvula de alívio de explosão (explosion vent).",
            "observacoes": "Silo sem inspeção interna há 24 meses.",
        },
        {
            "equipamento": "Silo de Armazenamento SA-12",
            "descricao_equipamento": "Silo metálico vertical para armazenamento de milho — 5.000 t",
            "riscos": "Incêndio",
            "perigo": "Auto-aquecimento de grãos armazenados (hot spot)",
            "causas": "Umidade excessiva; falta de termometria no corpo do silo",
            "consequencias": "Incêndio latente com liberação de gases tóxicos e risco de colapso",
            "categoria_severidade": "III — Alta",
            "categoria_risco": "Substancial",
            "medidas_existentes": "Termometria parcial (4 cabos)",
            "medidas_implementar": "Completar sistema de termometria com 12 cabos distribuídos e integrar alarme ao SDAI.",
            "observacoes": None,
        },
        {
            "equipamento": "Filtro de Mangas FM-05",
            "descricao_equipamento": "Filtro de mangas tipo pulse-jet para despoeiramento — 30.000 m³/h",
            "riscos": "Explosão de poeira",
            "perigo": "Acúmulo de poeira combustível dentro do filtro (tremonha e mangas)",
            "causas": "Válvula rotativa travada; falha na limpeza pulse-jet",
            "consequencias": "Explosão secundária no filtro com projeção de fragmentos",
            "categoria_severidade": "III — Alta",
            "categoria_risco": "Substancial",
            "medidas_existentes": "Válvula rotativa na descarga; sistema pulse-jet operante",
            "medidas_implementar": "Instalar sensor de nível na tremonha e válvula de alívio de explosão na carcaça do filtro.",
            "observacoes": None,
        },
        {
            "equipamento": "Moinho de Martelos MM-02",
            "descricao_equipamento": "Moinho de martelos para moagem de farelo — 60 t/h",
            "riscos": "Explosão de poeira",
            "perigo": "Alta concentração de poeira fina no interior do moinho durante operação",
            "causas": "Operação gera particulado fino com granulometria ≤ 75 µm em concentrações acima do MEC",
            "consequencias": "Explosão primária severa com propagação pelo sistema de transporte pneumático",
            "categoria_severidade": "IV — Catastrófica",
            "categoria_risco": "Intolerável",
            "medidas_existentes": "Ímã permanente na entrada; aspiração local",
            "medidas_implementar": "Instalar sistema de supressão de explosão (HRD) e válvula de isolamento rápido na saída.",
            "observacoes": "Equipamento crítico — maior risco da planta.",
        },
        {
            "equipamento": "Rosca Transportadora RT-07",
            "descricao_equipamento": "Rosca transportadora horizontal — transporte de farelo para ensaque",
            "riscos": "Incêndio",
            "perigo": "Atrito entre helicóide e calha por desalinhamento",
            "causas": "Desgaste do mancal intermediário; falta de manutenção preventiva",
            "consequencias": "Ignição de farelo com propagação para silos conectados",
            "categoria_severidade": "II — Média",
            "categoria_risco": "Moderado",
            "medidas_existentes": "Monitoramento visual pela operação",
            "medidas_implementar": "Instalar sensor de rotação (speed switch) e sensor de temperatura nos mancais.",
            "observacoes": None,
        },
    ]


# ======================================================================
# EQUIPAMENTOS AGRUPADOS (com recomendações e justificativas mockadas)
# ======================================================================

def _build_equipments() -> list[dict]:
    """Retorna equipamentos já agrupados com recomendações/justificativas mock."""
    return [
        {
            "index": 1,
            "nome": "Elevador de Canecas EC-01",
            "descricao": "Elevador de canecas para transporte vertical de grãos (soja/milho) — capacidade 120 t/h",
            "local_instalacao": "Torre de recebimento — Setor Grãos",
            "funcao_operacional": "Transporte vertical de grãos do fosso de recebimento ao distribuidor de silos",
            "images": [],
            "perigos": [
                "Acúmulo de poeira combustível no interior do elevador (pé e cabeça)",
                "Atrito correia/tambor gerando fonte de ignição",
            ],
            "causas": [
                "Falha no sistema de aspiração; desgaste das canecas; atrito correia/tambor",
                "Desalinhamento de correia sem sensor de detecção",
            ],
            "consequencias": [
                "Explosão primária com propagação para equipamentos conectados",
                "Incêndio interno com danos estruturais e risco de propagação",
            ],
            "severidade": "IV — Catastrófica",
            "risco": "Intolerável",
            "medidas_existentes": [
                "Sistema de aspiração centralizado operante",
            ],
            "medidas_implementar": [
                "Instalar sensores de alinhamento de correia e monitoramento de temperatura nos mancais",
                "Implementar sistema de detecção de desalinhamento com shutdown automático",
            ],
            "observacoes": ["Último alinhamento realizado há 14 meses."],
            "riscos_desc": ["Explosão de poeira", "Incêndio"],
            "recomendacoes_tecnicas": [
                {
                    "numero": 1,
                    "texto": "Instalar sensores de desalinhamento de correia (tipo chave de desvio) no tambor de retorno e no tambor de acionamento, com intertravamento configurado para parada automática do motor em caso de desvio superior a 15 mm.",
                    "norma_referencia": "NFPA 652, seção 8.3",
                },
                {
                    "numero": 2,
                    "texto": "Implementar sistema de monitoramento contínuo de temperatura nos mancais do pé e da cabeça do elevador, com alarme em 70 °C e shutdown em 85 °C, integrado ao sistema supervisório da planta.",
                    "norma_referencia": "NFPA 61, seção 6.8",
                },
                {
                    "numero": 3,
                    "texto": "Instalar portas de inspeção com trinco à prova de explosão na cabeça e no pé do elevador, possibilitando inspeção visual periódica sem desmontagem completa, conforme periodicidade quinzenal.",
                    "norma_referencia": "NFPA 654, seção 7.1",
                },
                {
                    "numero": 4,
                    "texto": "Implementar válvula de alívio de explosão (explosion vent) dimensionada conforme o volume interno do elevador em sua cabeça, com área de alívio calculada por meio da equação de Bartknecht e direcionada para área segura.",
                    "norma_referencia": "NFPA 68, seção 7.2",
                },
            ],
            "justificativas_tecnicas": [
                {
                    "numero": 1,
                    "texto": "O desalinhamento da correia constitui uma das principais fontes de ignição em elevadores de canecas, conforme reconhecido pela NFPA 652. O atrito entre a correia desalinhada e o tambor gera calor superficial suficiente para ignitar poeira combustível depositada, especialmente em equipamentos com operação contínua.\n\nConsiderando que o equipamento está classificado com severidade IV (Catastrófica) e risco Intolerável, a ausência de monitoramento automatizado de desalinhamento representa uma vulnerabilidade crítica que requer intervenção imediata.",
                },
                {
                    "numero": 2,
                    "texto": "O aquecimento de mancais em elevadores de canecas é um precursor reconhecido de eventos de incêndio e explosão. A NFPA 61 estabelece requisitos específicos para monitoramento de temperatura em equipamentos de transporte de grãos.\n\nDada a classificação de risco Intolerável e a consequência potencial de explosão primária com propagação, o monitoramento contínuo com shutdown automático é uma barreira preventiva essencial para interromper a cadeia de eventos antes da ignição.",
                },
                {
                    "numero": 3,
                    "texto": "A inspeção periódica do interior do elevador permite identificar acúmulos anormais de poeira, desgaste de canecas e condições precursoras de incêndio. A NFPA 654 recomenda inspeção visual regular em equipamentos com potencial de acúmulo de poeiras combustíveis.\n\nA implementação de portas de inspeção adequadas viabiliza esta prática sem necessidade de parada prolongada, reduzindo o tempo de exposição dos trabalhadores e aumentando a frequência de verificação.",
                },
                {
                    "numero": 4,
                    "texto": "A cabeça do elevador constitui o ponto de maior concentração de poeira em suspensão e, portanto, o volume com maior probabilidade de atingir condições explosivas. A NFPA 68 fornece metodologia consagrada para dimensionamento de dispositivos de alívio de explosão.\n\nConsiderando as consequências catastróficas (propagação para equipamentos conectados), a válvula de alívio atua como última barreira de proteção, limitando a sobrepressão interna e direcionando a energia da explosão para área segura.",
                },
            ],
        },
        {
            "index": 2,
            "nome": "Transportador Redler TR-03",
            "descricao": "Transportador tipo redler horizontal para farelo de soja — 80 t/h",
            "local_instalacao": "Interligação Extração — Armazém de Farelo",
            "funcao_operacional": "Transporte horizontal de farelo de soja entre o setor de extração e o armazém",
            "images": [],
            "perigos": [
                "Geração de poeira em suspensão nos pontos de transferência",
            ],
            "causas": [
                "Vedação insuficiente nas juntas; acúmulo em superfícies internas",
            ],
            "consequencias": [
                "Explosão confinada no interior do transportador",
            ],
            "severidade": "III — Alta",
            "risco": "Substancial",
            "medidas_existentes": [
                "Vedação com borracha nos pontos de carga",
            ],
            "medidas_implementar": [
                "Substituir vedações por modelo pressurizado e instalar bocais de aspiração nos pontos de transferência",
            ],
            "observacoes": [],
            "riscos_desc": ["Explosão de poeira"],
            "recomendacoes_tecnicas": [
                {
                    "numero": 1,
                    "texto": "Substituir as vedações atuais (borracha convencional) por vedação tipo labirinto pressurizado nos pontos de carga e descarga, garantindo estanqueidade contra emissão fugitiva de poeira para o ambiente externo.",
                    "norma_referencia": "NFPA 654, seção 7.4",
                },
                {
                    "numero": 2,
                    "texto": "Instalar bocais de aspiração localizada nos dois pontos de transferência (entrada e saída), conectados ao sistema de despoeiramento central, com velocidade de captura mínima de 1,0 m/s na face do bocal.",
                    "norma_referencia": "NFPA 652, seção 8.1",
                },
                {
                    "numero": 3,
                    "texto": "Implementar procedimento de inspeção e limpeza interna semestral do transportador, com registro fotográfico das condições de acúmulo e desgaste das correntes e raspadores.",
                    "norma_referencia": "NFPA 654, seção 8.2",
                },
            ],
            "justificativas_tecnicas": [
                {
                    "numero": 1,
                    "texto": "A vedação atual com borracha convencional não impede totalmente a emissão de poeira fugitiva nos pontos de transferência, conforme constatado em campo. A NFPA 654 recomenda sistemas de vedação que limitem a dispersão de particulado combustível para o ambiente.\n\nConsiderando que a poeira de farelo de soja é classificada como combustível (St-1) e que o risco do equipamento é Substancial, a substituição por vedação pressurizada é necessária para reduzir a concentração de poeira no entorno e minimizar o risco de explosão secundária externa.",
                },
                {
                    "numero": 2,
                    "texto": "Os pontos de transferência são reconhecidos como as principais fontes de geração de poeira em transportadores de material a granel. A NFPA 652 estabelece que sistemas de controle de poeira devem ser aplicados em todos os pontos de geração significativa.\n\nA aspiração localizada com velocidade de captura adequada reduz a concentração de poeira tanto no interior do transportador quanto no ambiente circundante, mitigando o risco de formação de nuvens em concentração explosiva.",
                },
                {
                    "numero": 3,
                    "texto": "O acúmulo progressivo de material residual no interior do transportador pode criar condições propícias a uma explosão confinada. A NFPA 654 recomenda programas de limpeza e inspeção documentados para equipamentos que processam materiais combustíveis.\n\nO registro fotográfico permite rastrear a evolução das condições ao longo do tempo e fundamentar decisões de manutenção preventiva.",
                },
            ],
        },
        {
            "index": 3,
            "nome": "Silo de Armazenamento SA-12",
            "descricao": "Silo metálico vertical para armazenamento de milho — 5.000 t",
            "local_instalacao": "Pátio de Silos — Ala Norte",
            "funcao_operacional": "Armazenamento intermediário de milho antes do processamento",
            "images": [],
            "perigos": [
                "Formação de nuvem de poeira durante carga/descarga do silo",
                "Auto-aquecimento de grãos armazenados (hot spot)",
            ],
            "causas": [
                "Queda livre de grãos sem defletor; ventilação natural insuficiente",
                "Umidade excessiva; falta de termometria no corpo do silo",
            ],
            "consequencias": [
                "Explosão no topo do silo com colapso estrutural",
                "Incêndio latente com liberação de gases tóxicos e risco de colapso",
            ],
            "severidade": "IV — Catastrófica",
            "risco": "Intolerável",
            "medidas_existentes": [
                "Bocal de aspiração no topo (subdimensionado)",
                "Termometria parcial (4 cabos)",
            ],
            "medidas_implementar": [
                "Redimensionar sistema de aspiração do topo; instalar válvula de alívio de explosão",
                "Completar sistema de termometria com 12 cabos e integrar alarme ao SDAI",
            ],
            "observacoes": ["Silo sem inspeção interna há 24 meses."],
            "riscos_desc": ["Explosão de poeira", "Incêndio"],
            "recomendacoes_tecnicas": [
                {
                    "numero": 1,
                    "texto": "Redimensionar o sistema de aspiração do topo do silo para vazão mínima de 15.000 m³/h, garantindo velocidade de captura suficiente para conter a nuvem de poeira gerada durante o carregamento a plena capacidade (120 t/h).",
                    "norma_referencia": "NFPA 652, seção 8.1",
                },
                {
                    "numero": 2,
                    "texto": "Instalar válvula de alívio de explosão (explosion vent) no topo do silo, dimensionada conforme NFPA 68 para o volume de 6.250 m³, com área de alívio direcionada para zona de exclusão demarcada.",
                    "norma_referencia": "NFPA 68, seção 7.3",
                },
                {
                    "numero": 3,
                    "texto": "Completar o sistema de termometria com instalação de 8 cabos adicionais (total 12), distribuídos radialmente em 3 níveis verticais, com integração ao SDAI para alarme em 45 °C e alerta crítico em 55 °C.",
                    "norma_referencia": "NFPA 61, seção 6.7",
                },
                {
                    "numero": 4,
                    "texto": "Instalar defletores de carga no ponto de alimentação do silo para reduzir a velocidade de queda dos grãos e minimizar a geração de poeira em suspensão durante o carregamento.",
                    "norma_referencia": "NFPA 61, seção 8.2",
                },
                {
                    "numero": 5,
                    "texto": "Realizar inspeção interna anual do silo com equipe especializada, incluindo verificação de integridade estrutural, condições de acúmulo de poeira em superfícies e funcionamento dos dispositivos de proteção.",
                    "norma_referencia": "NFPA 654, seção 8.3",
                },
            ],
            "justificativas_tecnicas": [
                {
                    "numero": 1,
                    "texto": "O sistema de aspiração atual é subdimensionado conforme constatado em campo, permitindo que poeira em concentração potencialmente explosiva permaneça em suspensão no topo do silo durante operações de carga. A NFPA 652 exige controle de poeira em todos os pontos de geração significativa.\n\nCom classificação de risco Intolerável e consequência potencial de explosão com colapso estrutural, o redimensionamento do sistema de aspiração é uma medida primária de prevenção.",
                },
                {
                    "numero": 2,
                    "texto": "Silos de grande volume representam cenários de alta energia de explosão. A NFPA 68 estabelece requisitos para dimensionamento de dispositivos de alívio de explosão em vasos e equipamentos confinados.\n\nA instalação de válvula de alívio no topo é a principal barreira de proteção contra sobrepressão catastrófica, direcionando a energia liberada para zona segura e preservando a integridade estrutural do silo.",
                },
                {
                    "numero": 3,
                    "texto": "A termometria parcial (4 cabos) não fornece cobertura adequada para um silo de 5.000 t, criando zonas sem monitoramento onde hot spots podem se desenvolver sem detecção. A NFPA 61 recomenda monitoramento térmico abrangente em silos de grãos.\n\nA integração com o SDAI garante resposta automatizada em caso de elevação de temperatura, permitindo ações preventivas antes da evolução para incêndio declarado.",
                },
                {
                    "numero": 4,
                    "texto": "A queda livre de grãos é a principal fonte de geração de poeira em suspensão durante o carregamento de silos. A instalação de defletores reduz significativamente a velocidade de impacto e, consequentemente, a quantidade de poeira dispersa.\n\nEsta medida atua na origem do perigo identificado, sendo complementar ao sistema de aspiração e reduzindo a demanda sobre o mesmo.",
                },
                {
                    "numero": 5,
                    "texto": "O silo encontra-se sem inspeção interna há 24 meses, período que excede as boas práticas recomendadas pela NFPA 654. Acúmulos não identificados de poeira em superfícies internas representam combustível disponível para uma explosão secundária de maior intensidade.\n\nA inspeção anual documentada permite manter o controle sobre as condições internas e garantir a operacionalidade dos dispositivos de proteção instalados.",
                },
            ],
        },
        {
            "index": 4,
            "nome": "Filtro de Mangas FM-05",
            "descricao": "Filtro de mangas tipo pulse-jet para despoeiramento — 30.000 m³/h",
            "local_instalacao": "Área externa — adjacente ao moinho MM-02",
            "funcao_operacional": "Despoeiramento do sistema de moagem e transporte pneumático",
            "images": [],
            "perigos": [
                "Acúmulo de poeira combustível dentro do filtro (tremonha e mangas)",
            ],
            "causas": [
                "Válvula rotativa travada; falha na limpeza pulse-jet",
            ],
            "consequencias": [
                "Explosão secundária no filtro com projeção de fragmentos",
            ],
            "severidade": "III — Alta",
            "risco": "Substancial",
            "medidas_existentes": [
                "Válvula rotativa na descarga; sistema pulse-jet operante",
            ],
            "medidas_implementar": [
                "Instalar sensor de nível na tremonha e válvula de alívio de explosão na carcaça",
            ],
            "observacoes": [],
            "riscos_desc": ["Explosão de poeira"],
            "recomendacoes_tecnicas": [
                {
                    "numero": 1,
                    "texto": "Instalar sensor de nível tipo capacitivo na tremonha do filtro, com alarme para a sala de controle quando o nível atingir 70% da capacidade, indicando falha na descarga.",
                    "norma_referencia": "NFPA 654, seção 7.2",
                },
                {
                    "numero": 2,
                    "texto": "Instalar válvula de alívio de explosão (explosion vent) dimensionada conforme NFPA 68 na lateral da carcaça do filtro, direcionada para área de exclusão sinalizada e livre de trânsito.",
                    "norma_referencia": "NFPA 68, seção 7.2",
                },
                {
                    "numero": 3,
                    "texto": "Implementar monitoramento diferencial de pressão entre entrada e saída do filtro, com alarme em queda de pressão inferior a 500 Pa (indicando ruptura de manga) e shutdown em sobrepressão.",
                    "norma_referencia": "NFPA 652, seção 9.2",
                },
            ],
            "justificativas_tecnicas": [
                {
                    "numero": 1,
                    "texto": "O travamento da válvula rotativa causa acúmulo de poeira na tremonha, aumentando a massa de combustível disponível para uma eventual explosão. A NFPA 654 recomenda monitoramento de nível em equipamentos de coleta de poeira.\n\nO sensor de nível com alarme permite intervenção antes que o acúmulo atinja níveis críticos, funcionando como barreira preventiva contra a condição precursora identificada.",
                },
                {
                    "numero": 2,
                    "texto": "Filtros de mangas são reconhecidos como pontos críticos de explosão secundária em plantas de processamento de grãos. A NFPA 68 fornece metodologia validada para dimensionamento de dispositivos de alívio em filtros industriais.\n\nA válvula de alívio limita a sobrepressão interna e previne a ruptura não controlada da carcaça, que poderia causar projeção de fragmentos em área com trânsito de pessoas.",
                },
                {
                    "numero": 3,
                    "texto": "A ruptura de mangas permite passagem de poeira fina para o lado limpo do filtro, reduzindo a eficiência e potencialmente liberando particulado para a atmosfera ou para dutos a jusante. A NFPA 652 recomenda monitoramento de integridade em sistemas de filtragem.\n\nO monitoramento diferencial de pressão é o método mais confiável e econômico para detecção precoce de falhas nas mangas.",
                },
            ],
        },
        {
            "index": 5,
            "nome": "Moinho de Martelos MM-02",
            "descricao": "Moinho de martelos para moagem de farelo — 60 t/h",
            "local_instalacao": "Setor de Moagem — Prédio Industrial 3",
            "funcao_operacional": "Moagem de farelo de soja para granulometria de ensaque",
            "images": [],
            "perigos": [
                "Alta concentração de poeira fina no interior do moinho durante operação",
            ],
            "causas": [
                "Operação gera particulado fino com granulometria ≤ 75 µm em concentrações acima do MEC",
            ],
            "consequencias": [
                "Explosão primária severa com propagação pelo sistema de transporte pneumático",
            ],
            "severidade": "IV — Catastrófica",
            "risco": "Intolerável",
            "medidas_existentes": [
                "Ímã permanente na entrada; aspiração local",
            ],
            "medidas_implementar": [
                "Instalar sistema de supressão de explosão (HRD) e válvula de isolamento rápido na saída",
            ],
            "observacoes": ["Equipamento crítico — maior risco da planta."],
            "riscos_desc": ["Explosão de poeira"],
            "recomendacoes_tecnicas": [
                {
                    "numero": 1,
                    "texto": "Instalar sistema de supressão de explosão (HRD — High Rate Discharge) no corpo do moinho, com detectores de pressão de resposta ≤ 5 ms e agente supressor tipo bicarbonato de sódio, dimensionado para Pred ≤ 0,5 bar.",
                    "norma_referencia": "NFPA 69, seção 8.2",
                },
                {
                    "numero": 2,
                    "texto": "Instalar válvula de isolamento rápido (tipo guilhotina pneumática com tempo de fechamento ≤ 50 ms) na saída do moinho para o sistema de transporte pneumático, impedindo propagação de chama e pressão.",
                    "norma_referencia": "NFPA 69, seção 10.3",
                },
                {
                    "numero": 3,
                    "texto": "Substituir o ímã permanente na entrada por detector de metais tipo indutivo com rejeição automática, capaz de identificar materiais ferrosos e não-ferrosos com diâmetro ≥ 3 mm.",
                    "norma_referencia": "NFPA 652, seção 8.8",
                },
                {
                    "numero": 4,
                    "texto": "Implementar monitoramento contínuo de vibração nos mancais do rotor, com alarme em 7 mm/s RMS e shutdown automático em 11 mm/s RMS, integrado ao CLP de segurança.",
                    "norma_referencia": "NFPA 652, seção 8.6",
                },
            ],
            "justificativas_tecnicas": [
                {
                    "numero": 1,
                    "texto": "O moinho de martelos opera intrinsecamente em condições explosivas, com concentrações de poeira acima do MEC (Minimum Explosible Concentration) no interior da câmara de moagem. A NFPA 69 estabelece requisitos para sistemas de supressão em equipamentos onde a prevenção total da formação de atmosferas explosivas não é viável.\n\nConsiderando a classificação de risco Intolerável e o potencial de início de cadeia de propagação, o sistema HRD é a barreira de proteção mais eficaz para este cenário, capaz de suprimir a explosão nos primeiros milissegundos.",
                },
                {
                    "numero": 2,
                    "texto": "A conexão do moinho ao sistema de transporte pneumático cria um caminho de propagação para explosões primárias. A NFPA 69 recomenda isolamento mecânico automatizado em pontos de interconexão entre equipamentos classificados.\n\nA válvula de isolamento rápido interrompe a propagação de chama e onda de pressão, limitando os efeitos da explosão ao volume do moinho e protegendo o filtro de mangas e demais equipamentos a jusante.",
                },
                {
                    "numero": 3,
                    "texto": "Objetos metálicos no fluxo de material representam fontes de ignição por impacto e faísca mecânica. O ímã permanente atual não detecta materiais não-ferrosos (alumínio, inox) que podem gerar faíscas ao impactar os martelos.\n\nA substituição por detector de metais com rejeição automática elimina esta fonte de ignição na origem, conforme boas práticas da NFPA 652.",
                },
                {
                    "numero": 4,
                    "texto": "Vibração excessiva no rotor indica desgaste ou desbalanceamento dos martelos, condição que aumenta o risco de atrito metal-metal e geração de calor localizado. A NFPA 652 recomenda monitoramento de condição em equipamentos críticos de processamento.\n\nO shutdown automático em nível crítico previne a evolução da condição para ignição, sendo compatível com a classificação de risco Intolerável do equipamento.",
                },
            ],
        },
        {
            "index": 6,
            "nome": "Rosca Transportadora RT-07",
            "descricao": "Rosca transportadora horizontal — transporte de farelo para ensaque",
            "local_instalacao": "Setor de Ensaque — Galpão 2",
            "funcao_operacional": "Transporte de farelo moído do silo pulmão para a ensacadeira",
            "images": [],
            "perigos": [
                "Atrito entre helicóide e calha por desalinhamento",
            ],
            "causas": [
                "Desgaste do mancal intermediário; falta de manutenção preventiva",
            ],
            "consequencias": [
                "Ignição de farelo com propagação para silos conectados",
            ],
            "severidade": "II — Média",
            "risco": "Moderado",
            "medidas_existentes": [
                "Monitoramento visual pela operação",
            ],
            "medidas_implementar": [
                "Instalar sensor de rotação (speed switch) e sensor de temperatura nos mancais",
            ],
            "observacoes": [],
            "riscos_desc": ["Incêndio"],
            "recomendacoes_tecnicas": [
                {
                    "numero": 1,
                    "texto": "Instalar sensor de rotação (speed switch) no eixo da rosca, configurado para parada automática em caso de sub-velocidade (≤ 80% da rotação nominal), indicando travamento ou sobrecarga.",
                    "norma_referencia": "NFPA 61, seção 6.5",
                },
                {
                    "numero": 2,
                    "texto": "Instalar sensores de temperatura tipo PT100 nos mancais intermediário e de ponta, com alarme em 60 °C e integração ao sistema supervisório para registro histórico.",
                    "norma_referencia": "NFPA 61, seção 6.8",
                },
            ],
            "justificativas_tecnicas": [
                {
                    "numero": 1,
                    "texto": "O travamento da rosca transportadora gera atrito intenso entre o helicóide e a calha, constituindo fonte de ignição potencial para o farelo transportado. A NFPA 61 recomenda monitoramento de rotação em transportadores de materiais combustíveis.\n\nA detecção automática de sub-velocidade permite intervenção antes que o atrito prolongado eleve a temperatura a ponto de ignição do farelo de soja (aproximadamente 340 °C — valor de referência da literatura técnica).",
                },
                {
                    "numero": 2,
                    "texto": "O monitoramento visual atualmente empregado é insuficiente para detectar elevação de temperatura nos mancais, uma vez que o aquecimento pode ocorrer gradualmente sem sinais visíveis até o estágio avançado. A NFPA 61 recomenda sensoriamento contínuo em pontos de atrito de equipamentos de transporte.\n\nO registro histórico viabiliza análise de tendência e planejamento de manutenção preditiva, reduzindo intervenções corretivas emergenciais.",
                },
            ],
        },
    ]


# ======================================================================
# SEÇÕES LLM (texto estático mockado)
# ======================================================================

def _build_llm_sections() -> dict[str, str]:
    return {
        "introducao": (
            "Este relatório técnico apresenta os resultados da Análise de Perigos "
            "por Poeira Combustível (DHA — Dust Hazard Analysis) realizada nas "
            "dependências da empresa Bunge Alimentos S.A., unidade São Francisco "
            "do Sul — SC, conforme vistoria técnica realizada em 10/02/2026.\n\n"
            "O objetivo principal é identificar cenários de risco associados à "
            "presença de poeiras combustíveis de origem agrícola (soja e milho) "
            "nos processos de recebimento, armazenamento, transporte e moagem "
            "de grãos, avaliar a severidade e a probabilidade de ocorrência de "
            "eventos adversos (incêndio e explosão) e propor medidas de controle "
            "fundamentadas nas normas NFPA 652, NFPA 61, NFPA 68, NFPA 69 e "
            "na série ABNT NBR IEC 60079.\n\n"
            "A análise abrange a Planta de Processamento de Grãos e Silos, "
            "compreendendo 6 equipamentos inventariados no levantamento de campo, "
            "desde o recebimento até o ensaque do produto final."
        ),
        "materiais": {
            "materiais_presentes": (
                "Durante a vistoria técnica realizada na unidade da Bunge — São Francisco "
                "do Sul, foi identificado o manuseio e armazenamento dos seguintes produtos "
                "com potencial de gerar poeiras combustíveis:\n\n"
                "• Soja em grão\n"
                "• Milho em grão\n"
                "• Farelo de soja\n\n"
                "Estes materiais, quando transformados em partículas finas em suspensão, "
                "possuem características combustíveis reconhecidas pelas normas internacionais "
                "e literatura científica especializada. A presença dessas poeiras em ambientes "
                "fechados, combinada com fontes de ignição, pode resultar em incêndios ou explosões."
            ),
            "propriedades_intro": (
                "Abaixo, apresentam-se os parâmetros típicos de explosividade dos materiais, "
                "extraídos de bases técnicas reconhecidas (Eckhoff, 2003; NFPA 652; relatórios "
                "de ensaios laboratoriais de indústrias similares)."
            ),
            "propriedades_colunas": ["Soja (poeira)", "Milho (poeira)", "Farelo de soja"],
            "propriedades_tabela": [
                {"propriedade": "Kst (bar·m/s)", "Soja (poeira)": "125 – 160", "Milho (poeira)": "110 – 150", "Farelo de soja": "150 – 200"},
                {"propriedade": "Pmax (bar)", "Soja (poeira)": "7,5 – 9,0", "Milho (poeira)": "6,5 – 8,5", "Farelo de soja": "7,5 – 9,0"},
                {"propriedade": "Classe de explosividade (St)", "Soja (poeira)": "St1", "Milho (poeira)": "St1", "Farelo de soja": "St1"},
                {"propriedade": "MIT (nuvem) (°C)", "Soja (poeira)": "400 – 460", "Milho (poeira)": "470 – 500", "Farelo de soja": "420 – 450"},
                {"propriedade": "MIT (camada) (°C)", "Soja (poeira)": "260 – 290", "Milho (poeira)": "270 – 300", "Farelo de soja": "250 – 280"},
                {"propriedade": "MIE (mínima energia de ignição)", "Soja (poeira)": "30 – 70 mJ", "Milho (poeira)": "50 – 100 mJ", "Farelo de soja": "40 – 80 mJ"},
                {"propriedade": "Tamanho de partícula crítico", "Soja (poeira)": "< 500 μm", "Milho (poeira)": "< 420 μm", "Farelo de soja": "< 420 μm"},
            ],
            "consideracoes": [
                "Os valores de Kst e Pmax confirmam que os materiais analisados pertencem à Classe St1, caracterizada por poeiras com potencial moderado de explosão, mas que ainda assim requerem controle rigoroso.",
                "A energia mínima de ignição (MIE) desses materiais está dentro da faixa crítica que permite ignição por fontes eletrostáticas, faíscas mecânicas ou elétricas, superfícies quentes e atrito.",
                "As temperaturas mínimas de ignição (MIT) da camada são significativamente menores que da nuvem, o que exige cuidados com acúmulo de poeira em superfícies aquecidas.",
            ],
            "conclusao_tecnica": (
                "Com base nas propriedades listadas, confirma-se que as poeiras de soja, milho "
                "e farelo de soja devem ser classificadas como materiais combustíveis, com potencial "
                "de formar atmosferas explosivas em condições de operação normal ou anormal da planta.\n\n"
                "A recomendação normativa, conforme NFPA 652:2022, é que todas as áreas onde tais "
                "materiais são manuseados, transportados ou armazenados estejam sujeitas à análise "
                "de riscos (DHA), com base técnica e documentação formal."
            ),
        },
        "metodologia": (
            "A avaliação foi conduzida com base na metodologia de Análise de "
            "Perigos por Poeira Combustível (DHA) estabelecida pela NFPA 652:2024, "
            "conforme as seguintes etapas:\n\n"
            "1. Levantamento dos materiais e substâncias processados na unidade, "
            "com identificação das propriedades de explosividade\n"
            "2. Identificação das áreas e equipamentos com potencial de formação "
            "de atmosferas explosivas por poeira combustível\n"
            "3. Inspeção técnica em campo, avaliando condições de housekeeping, "
            "fontes de ignição, sistemas de contenção e práticas operacionais\n"
            "4. Avaliação dos sistemas de proteção, detecção e supressão "
            "existentes\n"
            "5. Classificação do risco por equipamento, utilizando matriz de "
            "severidade (I–IV) × probabilidade, resultando em 5 faixas de risco: "
            "Trivial, Tolerável, Moderado, Substancial e Intolerável\n"
            "6. Geração de recomendações técnicas priorizadas por nível de risco, "
            "fundamentadas nas normas NFPA e ABNT aplicáveis\n\n"
            "A visita técnica foi realizada em 10/02/2026 com duração de 8 horas, "
            "percorrendo todas as áreas do processo produtivo. A classificação de "
            "risco seguiu os critérios da NFPA 652 adaptados para a metodologia "
            "da Konis Safety Engenharia."
        ),
        "conclusao": (
            "Com base na análise realizada em 6 equipamentos da unidade São "
            "Francisco do Sul, conclui-se que:\n\n"
            "• 3 equipamentos apresentam risco INTOLERÁVEL e requerem intervenção "
            "imediata: Elevador de Canecas EC-01, Silo de Armazenamento SA-12 e "
            "Moinho de Martelos MM-02\n"
            "• 2 equipamentos apresentam risco SUBSTANCIAL e devem ser tratados "
            "em até 90 dias: Transportador Redler TR-03 e Filtro de Mangas FM-05\n"
            "• 1 equipamento apresenta risco MODERADO com ação programada em até "
            "180 dias: Rosca Transportadora RT-07\n\n"
            "O Moinho de Martelos MM-02 é o equipamento de maior criticidade da "
            "planta, requerendo instalação prioritária de sistema de supressão "
            "de explosão (HRD) e válvula de isolamento rápido.\n\n"
            "Recomenda-se a implementação imediata das medidas indicadas para os "
            "itens de risco Intolerável, com cronograma máximo de 30 dias para "
            "início de implantação e 90 dias para conclusão. Riscos Substanciais "
            "devem ser tratados em paralelo, com prazo de 90 dias.\n\n"
            "A empresa deve manter programa de inspeção contínua, com revisão "
            "periódica desta análise conforme NFPA 652 (mínimo a cada 3 anos "
            "ou quando houver mudanças significativas nas operações ou "
            "configuração dos equipamentos)."
        ),
    }


# ======================================================================
# MAIN
# ======================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="Gera PDF mock para teste de layout")
    parser.add_argument(
        "--profile",
        default="dust",
        choices=["dust", "gas", "vapors"],
        help="Perfil do relatório (default: dust)",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Abrir o PDF automaticamente após geração",
    )
    args = parser.parse_args()

    output_dir = _PROJECT_ROOT / "output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "mock_report.pdf"

    renderer = WeasyPdfRenderer()
    profile_config = get_profile_config(args.profile)

    metadata = _build_metadata()
    rows = _build_rows()
    llm_sections = _build_llm_sections()
    equipments = _build_equipments()

    print(f"Perfil: {profile_config['label']}")
    print(f"Equipamentos: {len(equipments)}")
    print(f"Linhas de risco (anexo): {len(rows)}")

    print("Renderizando HTML...")
    html = renderer.render_html(
        metadata=metadata,
        rows=rows,
        llm_sections=llm_sections,
        equipments=equipments,
        profile_config=profile_config,
    )

    # Salvar HTML intermediário para debug de layout
    html_path = output_dir / "mock_report.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"HTML salvo: {html_path}")

    print("Gerando PDF via WeasyPrint...")
    pdf_bytes = renderer.render(html)

    output_path.write_bytes(pdf_bytes)
    print(f"PDF gerado: {output_path}  ({len(pdf_bytes):,} bytes)")

    if args.open:
        print("Abrindo PDF...")
        if sys.platform == "win32":
            os.startfile(str(output_path))
        elif sys.platform == "darwin":
            subprocess.run(["open", str(output_path)])
        else:
            subprocess.run(["xdg-open", str(output_path)])


if __name__ == "__main__":
    main()
