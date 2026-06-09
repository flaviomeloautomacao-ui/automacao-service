"""Serviço de domínio — monta o user prompt per-equipment para o LLM.

Transforma um ``EquipmentLLMInput`` (já validado e bounded) na string
de user prompt enviada ao LLM junto com o system prompt.

Contrato de referência: ``docs/equipment_llm_contract.md``, §8.

──────────────────────────────────────────────────────────────────────
 RESPONSABILIDADES
──────────────────────────────────────────────────────────────────────

 1. Formatar cada campo do ``EquipmentLLMInput`` em blocos legíveis.
 2. Produzir uma string **determinística** — mesma entrada, mesma saída.
 3. Solicitar explicitamente recomendações e justificativas numeradas.
 4. Exigir resposta em JSON e reforçar o formato.
 5. Incluir blocos opcionais de contexto externo (trechos normativos,
    literatura técnica) automaticamente quando presentes no model.

 **NÃO** faz: chamadas de rede, acesso a banco, geração de texto,
 validação de input (isso é responsabilidade de ``equipment_prompt_context``).
──────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from app.domain.entities import EquipmentLLMInput


# ---------------------------------------------------------------------------
# Helpers de formatação
# ---------------------------------------------------------------------------

def _format_bullet_list(items: list[str], empty_msg: str = "Nenhum item informado.") -> str:
    """Formata lista como bullets ``• item``, ou mensagem padrão se vazia."""
    if not items:
        return empty_msg
    return "\n".join(f"• {item}" for item in items)


# ---------------------------------------------------------------------------
# Função pública
# ---------------------------------------------------------------------------

def build_equipment_user_prompt(
    llm_input: EquipmentLLMInput,
    *,
    normative_excerpts: list[str] | None = None,
    literature_excerpts: list[str] | None = None,
) -> str:
    """Monta o user prompt para geração per-equipment.

    O prompt apresenta o contexto completo de **um único** equipamento
    e solicita ao LLM recomendações técnicas numeradas e justificativas
    técnicas numeradas, em formato JSON.

    Contexto externo (trechos normativos e de literatura) é incluído
    automaticamente quando presente no model (``llm_input.normative_context``
    / ``llm_input.literature_context``). Os parâmetros keyword
    ``normative_excerpts`` e ``literature_excerpts`` também são
    aceitos para retrocompatibilidade e são **mesclados** aos dados
    do model.

    A saída é uma string determinística: mesma entrada produz sempre
    a mesma string, sem dependência de estado externo.

    Args:
        llm_input: Payload validado e bounded (de ``build_equipment_prompt_context``).
        normative_excerpts: Trechos normativos como strings simples.
            Mesclados (após) ``llm_input.normative_context``.
        literature_excerpts: Trechos de literatura como strings simples.
            Mesclados (após) ``llm_input.literature_context``.

    Returns:
        String formatada pronta para envio como user message ao LLM.

    Example::

        from app.domain.services.equipment_prompt_context import (
            build_equipment_prompt_context,
        )
        from app.adapters.llm.prompts import get_profile_config

        cfg = get_profile_config("dust")
        llm_input = build_equipment_prompt_context(ctx, cfg["normas_principais"])
        if llm_input:
            user_prompt = build_equipment_user_prompt(llm_input)
    """
    risco = llm_input.classificacao_do_risco
    residual = getattr(llm_input, 'classificacao_risco_residual', None)

    # ── Blocos de contexto do equipamento ─────────────────────────
    sections: list[str] = [
        "Com base no contexto do equipamento abaixo, gere as recomendações técnicas e justificativas técnicas.",
        "",
        "### Equipamento ###",
        f"Nome: {llm_input.equipment_name}",
        f"Descrição da operação: {llm_input.descricao_da_operacao}",
        "",
        "### Perigos Identificados ###",
        _format_bullet_list(llm_input.identificacao_dos_perigos, "Nenhum perigo informado."),
        "",
        "### Causas Possíveis ###",
        _format_bullet_list(llm_input.causas_possiveis, "Nenhuma causa informada."),
        "",
        "### Consequências Potenciais ###",
        _format_bullet_list(llm_input.consequencias_potenciais, "Nenhuma consequência informada."),
        "",
        "### Classificação do Risco — Situação Atual ###",
        f"Categoria de Severidade: {risco.categoria_severidade}",
        f"Categoria da Probabilidade: {risco.categoria_probabilidade}",
        f"Classificação do Risco: {risco.classificacao_risco}",
    ]

    # Bloco residual (condicional)
    if residual is not None and any([
        residual.categoria_severidade,
        residual.categoria_probabilidade,
        residual.classificacao_risco,
    ]):
        sections.append("")
        sections.append("### Classificação do Risco — Pós Implementação das Medidas Preventivas ###")
        sections.append(f"Categoria de Severidade Residual: {residual.categoria_severidade or 'N/I'}")
        sections.append(f"Categoria da Probabilidade Residual: {residual.categoria_probabilidade or 'N/I'}")
        sections.append(f"Classificação do Risco Residual: {residual.classificacao_risco or 'N/I'}")

    sections.extend([
        "",
        "### Medidas Preventivas Existentes ###",
        _format_bullet_list(llm_input.medidas_preventivas_existentes, "Nenhuma medida existente informada."),
        "",
        "### Medidas a Implementar (orientação do analista) ###",
        _format_bullet_list(llm_input.medidas_a_implementar, "Nenhuma medida sugerida."),
        "",
        "### Normas Aplicáveis ###",
        _format_bullet_list(llm_input.normas_aplicaveis),
    ])

    # ── Blocos opcionais de contexto externo ────────────────────
    # Mescla dados do model + parâmetros keyword (retrocompatível)
    all_normative: list[str] = []
    for exc in llm_input.normative_context:
        # Usar apenas o nome da norma como label.
        # exc.section contém apenas posição no arquivo ("linhas X–Y"),
        # NÃO seções reais da norma — incluí-lo induziria o LLM a
        # inventar referências de seção inexistentes.
        label = f"{exc.source}"
        all_normative.append(f"{label}: {exc.text}")
    if normative_excerpts:
        all_normative.extend(normative_excerpts)

    all_literature: list[str] = []
    for exc in llm_input.literature_context:
        all_literature.append(f"{exc.source}: {exc.text}")
    if literature_excerpts:
        all_literature.extend(literature_excerpts)

    if all_normative:
        sections.append("")
        sections.append("### Trechos Normativos Relevantes ###")
        for i, excerpt in enumerate(all_normative, 1):
            sections.append(f"[{i}] {excerpt}")

    if all_literature:
        sections.append("")
        sections.append("### Trechos de Literatura Técnica ###")
        for i, excerpt in enumerate(all_literature, 1):
            sections.append(f"[{i}] {excerpt}")

    # ── Instrução final ───────────────────────────────────────────
    sections.append("")

    if all_normative:
        # Instrução reforçada quando há contexto normativo recuperado
        sections.append(
            "Analise SOMENTE este equipamento. "
            "Gere recomendações técnicas numeradas e justificativas técnicas numeradas, "
            "fundamentadas nos perigos, consequências e classificação de risco apresentados. "
            "As recomendações devem ir além das medidas existentes e usar as medidas a implementar como orientação."
        )
        sections.append("")
        sections.append(
            "REGRAS DE REFERÊNCIA NORMATIVA:\n"
            "• Use PRIORITARIAMENTE os trechos normativos recuperados acima como base para as recomendações e justificativas.\n"
            "• Em \"norma_referencia\", cite SOMENTE o nome da norma exatamente como aparece no campo fonte dos trechos acima (ex.: o título do documento). NÃO adicione seções, capítulos ou cláusulas que não estejam explicitamente escritas nos trechos.\n"
            "• NÃO invente norma, seção, capítulo ou obrigação técnica que não esteja explicitamente presente nos trechos normativos fornecidos ou na lista de normas aplicáveis.\n"
            "• Quando o contexto normativo recuperado não for suficiente para uma recomendação, use uma das normas da lista de Normas Aplicáveis (apenas o nome, sem seção).\n"
            "• Cada justificativa deve referenciar ao menos um dos trechos normativos fornecidos, quando disponível.\n"
            "• NÃO invente valores numéricos (percentuais, distâncias, temperaturas, etc.) que não estejam nos trechos normativos ou no contexto do equipamento."
        )
        sections.append("")
        sections.append(
            "REGRAS DE CLASSIFICAÇÃO E EVIDÊNCIA:\n"
            "• Para cada recomendação, classifique obrigatoriamente o campo \"tipo\":\n"
            "  - \"normativa\": quando a recomendação é fundamentada em um trecho normativo fornecido acima. Copie o trecho literal em \"trecho_normativo\".\n"
            "  - \"boa_pratica\": quando a recomendação é baseada em conhecimento técnico sem trecho normativo explícito. Defina \"trecho_normativo\" como null.\n"
            "• Se não houver trecho normativo aplicável para fundamentar a recomendação, NÃO classifique como \"normativa\". Use \"boa_pratica\".\n"
            "• O campo \"trecho_normativo\" deve conter APENAS texto copiado literalmente de um dos trechos normativos relevantes listados acima. NÃO parafraseie."
        )
    else:
        sections.append(
            "Analise SOMENTE este equipamento. "
            "Gere recomendações técnicas numeradas e justificativas técnicas numeradas, "
            "fundamentadas nos perigos, consequências e classificação de risco apresentados. "
            "As recomendações devem ir além das medidas existentes e usar as medidas a implementar como orientação."
        )
    sections.append("")
    sections.append(
        "REGRAS ANTI-DUPLICAÇÃO DE JUSTIFICATIVAS:\n"
        "• NÃO emita justificativas com texto idêntico ou com mesmo conteúdo reformulado.\n"
        "• Cada justificativa deve ser Única, vinculada à recomendação de mesmo número,\n"
        "  trazendo elementos específicos (perigo distinto, trecho normativo distinto\n"
        "  ou consequência específica) que a diferenciem das demais.\n"
        "• Prefira uma única justificativa abrangente a várias justificativas repetidas."
    )
    sections.append("")
    sections.append("Responda EXCLUSIVAMENTE com o JSON no formato abaixo:")
    sections.append(
        "{\n"
        '  "recomendacoes_tecnicas": [\n'
        '    {"numero": 1, "texto": "...", "norma_referencia": "...", "tipo": "normativa", "trecho_normativo": "texto literal do trecho"},\n'
        '    {"numero": 2, "texto": "...", "norma_referencia": "...", "tipo": "boa_pratica", "trecho_normativo": null},\n'
        "    ...\n"
        "  ],\n"
        '  "justificativas_tecnicas": [\n'
        '    {"numero": 1, "texto": "..."},\n'
        "    ...\n"
        "  ]\n"
        "}"
    )

    return "\n".join(sections)
