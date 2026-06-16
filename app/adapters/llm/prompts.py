"""Prompts para geração de seções do laudo técnico via LLM.

Contém prompts por perfil de risco (DHA/Poeiras, Gases, Vapores)
e funções para construção do contexto.

IMPORTANTE: O LLM **nunca** valida ou modifica dados da planilha.
Ele apenas gera seções narrativas (introdução, metodologia, conclusão,
caracterização de materiais) a partir do contexto estruturado recebido.

────────────────────────────────────────────────────────────────────────
 COMO EDITAR OS PERFIS
────────────────────────────────────────────────────────────────────────
Cada perfil é um dict em ``PROFILE_CONFIG``.  Para adicionar ou
modificar um perfil:

1. Localize ``PROFILE_CONFIG`` abaixo.
2. Copie um bloco existente (ex.: ``"dust"``) e renomeie a chave.
3. Ajuste os campos:
   - ``label``            → nome legível do perfil
   - ``titulo_relatorio`` → título que aparece na capa do PDF
   - ``subtitulo``        → subtítulo na capa
   - ``normas_principais``→ lista de normas citadas nas referências
   - ``materiais_section``→ True se o relatório inclui seção de
                            caracterização de materiais
   - ``foco``             → texto descrevendo o foco da análise
                            (usado para instruir o LLM)
   - ``tipo_atmosfera``   → descrição do tipo de atmosfera perigosa
4. Adicione a mesma chave ao ``<select>`` no frontend em
   ``components/upload/ProfileSelect.tsx`` (array ``PROFILES``).

Para consultar a documentação completa, veja ``docs/PROFILES.md``.
────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from typing import Any

_KONIS_DEFAULTS: dict[str, str] = {
    "responsavel_tecnico": "Francisco Flávio Melo Cavalcante",
    "registro_profissional": "CREA SP – 5060562076",
    "assinatura_nome": "Flávio Cavalcante",
    "assinatura_cargo": "Gerente técnico",
    "assinatura_registro": "CREA SP – 5060562076",
    "assinatura_celular": "+55 (11) 94572 0000",
    "assinatura_telefone": "+55 (11) 3046 3648",
    "assinatura_email": "flavio.cavalcante@konis.com.br",
    "rodape_endereco": (
        "Gomes de Carvalho, 1255, sobreloja, Vila Olímpia, "
        "São Paulo/SP - CEP 04547-005"
    ),
    "rodape_telefone": "+55 (11) 3046-3648",
    "rodape_email": "flavio.cavalcante@konis.com.br",
}

# ---------------------------------------------------------------------------
# Configuração de Perfis
# ---------------------------------------------------------------------------
# Cada perfil define:
#   - label             : nome legível
#   - titulo_relatorio  : título principal do relatório (capa)
#   - subtitulo         : subtítulo do relatório (capa)
#   - normas_principais : normas mais relevantes para esse perfil
#   - materiais_section : se inclui seção de materiais combustíveis
#   - foco              : descrição do foco da análise (system prompt)
#   - tipo_atmosfera    : descrição da atmosfera perigosa
# ---------------------------------------------------------------------------

PROFILE_CONFIG: dict[str, dict[str, Any]] = {
    # ── DHA – Dust Hazard Analysis (Poeiras Combustíveis) ──────────
    "dust": {
        **_KONIS_DEFAULTS,
        "label": "DHA — Dust Hazard Analysis",
        "titulo_relatorio": "RELATÓRIO TÉCNICO\nDHA (Dust Hazard Analysis)",
        "subtitulo": "",
        "normas_principais": [
            "NFPA 652:2022 — Standard on the Fundamentals of Combustible Dust",
            "NFPA 654 — Prevention of Fire and Dust Explosions from Manufacturing, Processing, and Handling of Combustible Particulate Solids",
            "NFPA 68 — Standard on Explosion Protection by Deflagration Venting",
            "NFPA 69 — Standard on Explosion Prevention Systems",
            "ABNT NBR IEC 60079-10-2 — Atmosferas explosivas: classificação de áreas — Poeiras combustíveis",
            "ABNT NBR IEC 60079-14 — Projeto, seleção e montagem de instalações elétricas",
            "ABNT NBR IEC 60079-0 — Requisitos gerais para equipamentos",
            "ABNT NBR IEC 60079-31 — Proteção contra ignição de poeira por invólucro",
            "ABNT NBR IEC 60079-17 — Inspeção e manutenção de instalações elétricas",
            "ABNT NBR 5410 — Instalações elétricas de baixa tensão",
            "NR-10 — Segurança em instalações e serviços em eletricidade",
        ],
        "materiais_section": True,
        "foco": (
            "análise de perigos por poeira combustível (DHA – Dust Hazard Analysis), "
            "incluindo identificação de cenários de risco de incêndio e explosão por "
            "poeiras, fontes de ignição, condições de formação de nuvem de poeira, "
            "potencial de propagação e recomendações de prevenção e mitigação"
        ),
        "tipo_atmosfera": "atmosferas explosivas por poeira combustível",
    },

    # ── Gases Inflamáveis ──────────────────────────────────────────
    "gas": {
        **_KONIS_DEFAULTS,
        "label": "Análise de Riscos — Gases Inflamáveis",
        "titulo_relatorio": "RELATÓRIO TÉCNICO\nAnálise de Riscos de Gases Inflamáveis",
        "subtitulo": "Avaliação de Perigos em Atmosferas com Gases Inflamáveis",
        "normas_principais": [
            "ABNT NBR IEC 60079-10-1 — Atmosferas explosivas: classificação de áreas — Gases inflamáveis",
            "ABNT NBR IEC 60079-14 — Projeto, seleção e montagem de instalações elétricas",
            "ABNT NBR IEC 60079-0 — Requisitos gerais para equipamentos",
            "ABNT NBR IEC 60079-1 — Proteção por invólucro à prova de explosão",
            "ABNT NBR IEC 60079-17 — Inspeção e manutenção",
            "NR-10 — Segurança em instalações e serviços em eletricidade",
            "NR-20 — Segurança e Saúde no Trabalho com Inflamáveis e Combustíveis",
            "ABNT NBR 5410 — Instalações elétricas de baixa tensão",
        ],
        "materiais_section": True,
        "foco": (
            "análise de riscos em atmosferas com gases inflamáveis, incluindo "
            "identificação de fontes de liberação, classificação de zonas, "
            "avaliação de ventilação e recomendações de controle"
        ),
        "tipo_atmosfera": "atmosferas explosivas por gases inflamáveis",
    },

    # ── Vapores Inflamáveis ────────────────────────────────────────
    "vapors": {
        **_KONIS_DEFAULTS,
        "label": "Análise de Riscos — Vapores Inflamáveis",
        "titulo_relatorio": "RELATÓRIO TÉCNICO\nAnálise de Riscos de Vapores Inflamáveis",
        "subtitulo": "Avaliação de Perigos em Atmosferas com Vapores Inflamáveis",
        "normas_principais": [
            "ABNT NBR IEC 60079-10-1 — Atmosferas explosivas: classificação de áreas — Vapores inflamáveis",
            "ABNT NBR IEC 60079-14 — Projeto, seleção e montagem de instalações elétricas",
            "ABNT NBR IEC 60079-0 — Requisitos gerais para equipamentos",
            "NR-10 — Segurança em instalações e serviços em eletricidade",
            "NR-20 — Segurança e Saúde no Trabalho com Inflamáveis e Combustíveis",
            "ABNT NBR 5410 — Instalações elétricas de baixa tensão",
        ],
        "materiais_section": True,
        "foco": (
            "análise de riscos em atmosferas com vapores de líquidos inflamáveis, "
            "incluindo ponto de fulgor, classificação de zonas e medidas de "
            "prevenção e controle"
        ),
        "tipo_atmosfera": "atmosferas explosivas por vapores de líquidos inflamáveis",
    },

    # ── Classificação de Áreas (IEC 60079-10-1/10-2) ───────────────
    "areas": {
        **_KONIS_DEFAULTS,
        "label": "Classificação de Áreas",
        "titulo_relatorio": "RELATÓRIO TÉCNICO\nEstudo de Classificação de Áreas",
        "subtitulo": "Atmosferas Explosivas — Gases, Vapores e Poeiras Combustíveis",
        "normas_principais": [
            "ABNT NBR IEC 60079-10-1 — Atmosferas explosivas: classificação de áreas — Gases e vapores inflamáveis",
            "ABNT NBR IEC 60079-10-2 — Atmosferas explosivas: classificação de áreas — Atmosferas de poeiras combustíveis",
            "ABNT NBR IEC 60079-14 — Projeto, seleção e montagem de instalações elétricas",
            "ABNT NBR IEC 60079-0 — Equipamentos: requisitos gerais",
            "ABNT NBR IEC 60079-17 — Inspeção e manutenção de instalações elétricas",
            "NFPA 652 — Standard on the Fundamentals of Combustible Dust",
            "NR-10 — Segurança em instalações e serviços em eletricidade",
            "NR-20 — Segurança e Saúde no Trabalho com Inflamáveis e Combustíveis",
            "ABNT NBR 5410 — Instalações elétricas de baixa tensão",
        ],
        "materiais_section": False,
        "compound_table": True,
        "sections_semi_static": True,
        "foco": (
            "classificação de áreas com atmosferas explosivas, segundo as normas "
            "ABNT NBR IEC 60079-10-1 (gases e vapores inflamáveis) e "
            "ABNT NBR IEC 60079-10-2 (poeiras combustíveis), incluindo identificação "
            "e graduação de fontes de liberação, avaliação do grau e disponibilidade "
            "de ventilação, definição de zonas (0/1/2 e 20/21/22) e suas extensões, "
            "e seleção de equipamentos elétricos adequados (Grupo, Classe de "
            "Temperatura e EPL)"
        ),
        "tipo_atmosfera": "atmosferas explosivas (gases, vapores e poeiras combustíveis)",
    },
}

#: Perfil padrão quando não especificado.
DEFAULT_PROFILE: str = "dust"


def get_profile_config(profile: str | None) -> dict[str, Any]:
    """Retorna a configuração do perfil selecionado.

    Args:
        profile: Identificador do perfil (``"dust"``, ``"gas"``, ``"vapors"``).
                 Se ``None`` ou inválido, retorna o perfil padrão.

    Returns:
        Dict com configuração completa do perfil.
    """
    if not profile or profile not in PROFILE_CONFIG:
        return PROFILE_CONFIG[DEFAULT_PROFILE]
    return PROFILE_CONFIG[profile]


# ---------------------------------------------------------------------------
# System prompt — base + perfil
# ---------------------------------------------------------------------------

def build_system_prompt(profile: str | None = None) -> str:
    """Constrói o system prompt baseado no perfil selecionado.

    O system prompt instrui o LLM sobre o papel técnico, o perfil de
    análise e as regras de formatação do JSON de resposta.

    Args:
        profile: Identificador do perfil.

    Returns:
        System prompt string completa.
    """
    cfg = get_profile_config(profile)

    normas_text = "\n".join(f"  - {n}" for n in cfg["normas_principais"][:6])

    return (
        f"Você é um engenheiro de segurança do trabalho altamente qualificado, "
        f"especializado em {cfg['foco']}.\n\n"
        f"Normas de referência principal:\n{normas_text}\n\n"
        f"Sua tarefa é gerar seções narrativas para o relatório técnico de "
        f"{cfg['label']}.\n\n"
        "Regras obrigatórias:\n"
        "1. Responda EXCLUSIVAMENTE em JSON válido, sem texto fora do JSON.\n"
        "2. O JSON deve conter exatamente as chaves especificadas no prompt do usuário.\n"
        "3. Cada valor deve ser uma string com texto técnico formal em parágrafos.\n"
        "4. Use linguagem técnica formal, objetiva e concisa.\n"
        "5. Cite normas e referências regulatórias quando aplicável.\n"
        "6. Não invente dados numéricos específicos que não foram fornecidos.\n"
        "   Para propriedades de materiais, use faixas típicas reconhecidas\n"
        "   pela literatura técnica e indique como 'dados de referência'.\n"
        "7. Não inclua markdown, comentários, ou explicações fora do JSON.\n"
        "8. Separe parágrafos com \\n\\n dentro das strings.\n"
        "9. Para listas, use linhas começando com '• ' (bullet point).\n"
        "10. Para listas numeradas, use '1. ', '2. ', etc.\n"
    )


def build_system_prompt_retry(profile: str | None = None) -> str:
    """System prompt para retry quando a primeira resposta não é JSON.

    Args:
        profile: Identificador do perfil.

    Returns:
        System prompt reforçado.
    """
    return (
        build_system_prompt(profile)
        + "\nATENÇÃO: Sua resposta anterior não era JSON válido. "
        "Responda APENAS com JSON puro, sem nenhum texto adicional, "
        "sem blocos de código (```), sem explicações. Apenas o objeto JSON."
    )


# ── Compat: manter constantes legadas para não quebrar imports ────
SYSTEM_PROMPT: str = build_system_prompt(None)
SYSTEM_PROMPT_RETRY: str = build_system_prompt_retry(None)

# ---------------------------------------------------------------------------
# User prompt template
# ---------------------------------------------------------------------------

_USER_PROMPT_TEMPLATE: str = (
    "Com base no contexto abaixo, gere as seções narrativas do relatório técnico.\n\n"
    "### Dados do Projeto ###\n"
    "Cliente / Razão Social: {razao_social}\n"
    "CNPJ: {cnpj}\n"
    "Unidade / Planta: {site}\n"
    "Endereço: {endereco}\n"
    "Local Vistoriado: {local_vistoriado}\n"
    "Responsável Técnico: {responsavel}\n"
    "Registro Profissional: {registro_profissional}\n"
    "Elaboração: {elaboracao}\n"
    "Data da Vistoria: {data_avaliacao}\n"
    "Contrato: {contrato}\n\n"
    "{observacoes_section}"
    "### Tipo de Análise ###\n"
    "Perfil: {perfil_label}\n"
    "Foco: {perfil_foco}\n"
    "Tipo de Atmosfera: {tipo_atmosfera}\n\n"
    "### Equipamentos e Riscos Identificados "
    "({total_equipamentos} equipamentos, {total_riscos} itens de risco) ###\n"
    "{riscos_texto}\n\n"
    "### Normas Aplicáveis ###\n"
    "{normas_texto}\n\n"
    "Gere o JSON com as seguintes chaves (cada valor é uma string de texto):\n"
    "{chaves_solicitadas}\n\n"
    "Formato obrigatório do JSON:\n"
    "{formato_json}\n"
)


def build_user_prompt(context: dict[str, Any]) -> str:
    """Monta o user prompt a partir do contexto estruturado.

    O contexto deve conter:
    - ``company``           : dict com dados da empresa
    - ``rows``              : lista de dicts com riscos (MachineRiskRow)
    - ``profile``           : identificador do perfil
    - ``grouped_equipment`` : lista de equipamentos agrupados (opcional)

    Args:
        context: Dicionário com os dados do pipeline.

    Returns:
        String formatada pronta para envio ao LLM.
    """
    company = context.get("company", {})
    profile = context.get("profile")
    cfg = get_profile_config(profile)

    # ── Formatar riscos como texto legível ──
    rows = context.get("rows", [])
    grouped = context.get("grouped_equipment", [])

    riscos_linhas: list[str] = []
    if grouped:
        for eq in grouped:
            riscos_linhas.append(f"\n--- {eq['nome']} ---")
            if eq.get("descricao"):
                riscos_linhas.append(f"  Descrição: {eq['descricao']}")
            for p in eq.get("perigos", []):
                riscos_linhas.append(f"  • Perigo: {p}")
            for c in eq.get("causas", []):
                riscos_linhas.append(f"  • Causa: {c}")
            for cn in eq.get("consequencias", []):
                riscos_linhas.append(f"  • Consequência: {cn}")
            riscos_linhas.append(
                f"  Severidade: {eq.get('severidade', 'N/I')} | "
                f"Prob: {eq.get('probabilidade', eq.get('risco', 'N/I'))} | "
                f"Class: {eq.get('classificacao', eq.get('risco', 'N/I'))}"
            )
            for m in eq.get("medidas_existentes", []):
                riscos_linhas.append(f"  • Medida existente: {m}")
            for m in eq.get("medidas_implementar", []):
                riscos_linhas.append(f"  • Recomendação: {m}")
    else:
        for i, row in enumerate(rows, start=1):
            riscos_linhas.append(
                f"{i}. Equipamento: {row.get('equipamento', 'N/I')} | "
                f"Perigo: {row.get('perigo', 'N/I')} | "
                f"Causas: {row.get('causas', 'N/I')} | "
                f"Severidade: {row.get('categoria_severidade', 'N/I')} | "
                f"Cat. Risco: {row.get('categoria_risco', 'N/I')}"
            )

    riscos_texto = (
        "\n".join(riscos_linhas) if riscos_linhas else "Nenhum risco informado."
    )

    # ── Normas aplicáveis ──
    normas_texto = "\n".join(f"• {n}" for n in cfg["normas_principais"])

    # ── Chaves solicitadas ao LLM ──
    chaves: list[str] = [
        (
            '"introducao": Texto de introdução do relatório com objetivos e '
            "escopo da análise. Deve citar o cliente, a unidade e a data."
        ),
    ]
    if cfg.get("materiais_section"):
        chaves.append(
            '"materiais": Caracterização dos materiais combustíveis / '
            "inflamáveis presentes na unidade, incluindo propriedades "
            "típicas de explosividade ou inflamabilidade (dados de referência "
            "da literatura quando não disponíveis) e conclusão técnica."
        )
    chaves.extend(
        [
            (
                '"metodologia": Descrição detalhada da metodologia aplicada '
                "à avaliação, etapas realizadas, fontes de dados e critérios "
                "de avaliação de risco."
            ),
            (
                '"conclusao": Conclusão do relatório com resumo dos '
                "achados críticos, urgência das recomendações e visão geral "
                "do nível de risco da unidade. NÃO use o termo 'conclusão geral'."
            ),
        ]
    )

    chaves_texto = "\n".join(f"  - {c}" for c in chaves)

    # ── Formato JSON esperado ──
    keys_json = ['"introducao": "..."']
    if cfg.get("materiais_section"):
        keys_json.append('"materiais": "..."')
    keys_json.extend(['"metodologia": "..."', '"conclusao": "..."'])
    formato = "{\n  " + ",\n  ".join(keys_json) + "\n}"

    total_equipamentos = len(grouped) if grouped else len(
        {r.get("equipamento", "") for r in rows}
    )
    total_riscos = len(rows)

    # ── Seção 7/14: Observações gerais normalizadas (prompt simplificado) ──
    # Usa o prompt normalizado (observacoes_gerais_prompt) se disponível,
    # caso contrário usa o texto original (observacoes_gerais).
    # Se ambos estiverem vazios, omite a seção inteira (Seção 7: NÃO chamar LLM).
    obs_prompt = (
        company.get("observacoes_gerais_prompt")
        or company.get("observacoes_gerais")
        or ""
    ).strip()
    observacoes_section = ""
    if obs_prompt:
        observacoes_section = (
            "### Observações do Cliente ###\n"
            f"{obs_prompt}\n\n"
        )

    return _USER_PROMPT_TEMPLATE.format(
        razao_social=company.get("razao_social", "N/I"),
        cnpj=company.get("cnpj", "N/I"),
        site=company.get("site", "N/I"),
        endereco=company.get("endereco", "N/I"),
        local_vistoriado=company.get("local_vistoriado", "N/I"),
        responsavel=company.get("responsavel", "N/I"),
        registro_profissional=company.get("registro_profissional", "N/I"),
        elaboracao=company.get("elaboracao", "N/I"),
        data_avaliacao=company.get("data_avaliacao", "N/I"),
        contrato=company.get("contrato", "N/I"),
        observacoes_section=observacoes_section,
        perfil_label=cfg["label"],
        perfil_foco=cfg["foco"],
        tipo_atmosfera=cfg["tipo_atmosfera"],
        riscos_texto=riscos_texto,
        normas_texto=normas_texto,
        total_equipamentos=total_equipamentos,
        total_riscos=total_riscos,
        chaves_solicitadas=chaves_texto,
        formato_json=formato,
    )
