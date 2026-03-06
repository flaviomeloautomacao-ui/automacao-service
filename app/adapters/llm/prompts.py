"""Prompts para geração de seções do laudo técnico via LLM.

Contém o system prompt fixo e o template de user prompt utilizado
pelo ``OpenRouterClient`` para solicitar seções narrativas ao modelo.

IMPORTANTE: O LLM **nunca** valida ou modifica dados da planilha.
Ele apenas gera texto enriquecido (sumário, recomendações, justificativas)
a partir do contexto estruturado recebido.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# System prompt — enviado em todas as chamadas
# ---------------------------------------------------------------------------

SYSTEM_PROMPT: str = (
    "Você é um engenheiro de segurança do trabalho altamente qualificado, "
    "especializado em análise de riscos de máquinas e equipamentos conforme "
    "as normas brasileiras (NR-12, NR-10, ISO 12100, ABNT NBR 14153, entre outras).\n\n"
    "Sua tarefa é gerar seções narrativas para laudos técnicos de segurança.\n\n"
    "Regras obrigatórias:\n"
    "1. Responda EXCLUSIVAMENTE em JSON válido, sem texto fora do JSON.\n"
    "2. O JSON deve conter exatamente as chaves: \"sumario\", \"recomendacoes\", \"justificativas\".\n"
    "   - \"sumario\": string com o resumo executivo do laudo.\n"
    "   - \"recomendacoes\": lista de strings, cada uma com uma recomendação técnica.\n"
    "   - \"justificativas\": lista de strings, cada uma com a justificativa normativa correspondente.\n"
    "3. Use linguagem técnica formal, objetiva e concisa.\n"
    "4. Cite normas e referências regulatórias quando aplicável.\n"
    "5. Não invente dados. Baseie-se apenas no contexto fornecido.\n"
    "6. Não inclua markdown, comentários, ou explicações fora do JSON.\n"
)

# ---------------------------------------------------------------------------
# System prompt para retry — usado quando a primeira resposta não é JSON
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_RETRY: str = (
    SYSTEM_PROMPT
    + "\nATENÇÃO: Sua resposta anterior não era JSON válido. "
    "Responda APENAS com JSON puro, sem nenhum texto adicional, "
    "sem blocos de código (```), sem explicações. Apenas o objeto JSON."
)

# ---------------------------------------------------------------------------
# User prompt template
# ---------------------------------------------------------------------------

USER_PROMPT_TEMPLATE: str = (
    "Com base no contexto abaixo, gere as seções narrativas do laudo técnico.\n\n"
    "### Dados da Empresa ###\n"
    "Razão Social: {razao_social}\n"
    "CNPJ: {cnpj}\n"
    "Unidade/Planta: {site}\n"
    "Endereço: {endereco}\n"
    "Responsável Técnico: {responsavel}\n"
    "Data da Avaliação: {data_avaliacao}\n\n"
    "### Riscos Identificados ###\n"
    "{riscos_texto}\n\n"
    "### Normas Aplicáveis ###\n"
    "{normas_texto}\n\n"
    "Responda APENAS com JSON válido no formato:\n"
    '{{\n'
    '  "sumario": "...",\n'
    '  "recomendacoes": ["...", "..."],\n'
    '  "justificativas": ["...", "..."]\n'
    '}}'
)


def build_user_prompt(context: dict) -> str:
    """Monta o user prompt a partir do contexto estruturado.

    Args:
        context: Dicionário com dados do draft. Espera-se chaves como
                 ``company`` (dict com dados da empresa), ``rows`` (lista de
                 dicts com riscos) e opcionalmente ``normas`` (texto ou lista).

    Returns:
        String formatada pronta para envio ao LLM.
    """
    company = context.get("company", {})

    # Formatar riscos como texto legível
    rows = context.get("rows", [])
    riscos_linhas: list[str] = []
    for i, row in enumerate(rows, start=1):
        linha = (
            f"{i}. Área: {row.get('area', 'N/I')} | "
            f"Equipamento: {row.get('equipamento', 'N/I')} | "
            f"Perigo: {row.get('perigo', 'N/I')} | "
            f"Causa: {row.get('causa', 'N/I')} | "
            f"Consequência: {row.get('consequencia', 'N/I')} | "
            f"Risco: {row.get('risco', 'N/I')} | "
            f"Norma: {row.get('norma_ref', 'N/I')}"
        )
        riscos_linhas.append(linha)

    riscos_texto = "\n".join(riscos_linhas) if riscos_linhas else "Nenhum risco informado."

    # Normas aplicáveis
    normas = context.get("normas", "")
    if isinstance(normas, list):
        normas_texto = "\n".join(str(n) for n in normas)
    else:
        normas_texto = str(normas) if normas else "Não informadas."

    return USER_PROMPT_TEMPLATE.format(
        razao_social=company.get("razao_social", "N/I"),
        cnpj=company.get("cnpj", "N/I"),
        site=company.get("site", "N/I"),
        endereco=company.get("endereco", "N/I"),
        responsavel=company.get("responsavel", "N/I"),
        data_avaliacao=company.get("data_avaliacao", "N/I"),
        riscos_texto=riscos_texto,
        normas_texto=normas_texto,
    )
