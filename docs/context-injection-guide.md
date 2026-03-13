# Guia de Integração — Context Injection (RAG / Retrieval)

> **Status:** Arquitetura preparada. Retrieval **não implementado** ainda.

Este documento descreve como futuros adaptadores de RAG/retrieval devem
popular os campos `normative_context` e `literature_context` do pipeline
per-equipment de geração LLM.

---

## 1. Visão geral da arquitetura

```
┌─────────────────────┐
│ Spreadsheet Parser   │
└────────┬────────────┘
         │ rows
         ▼
┌─────────────────────┐
│ EquipmentContext     │  ← build_equipment_contexts()
│ Builder              │
└────────┬────────────┘
         │ EquipmentContext[]
         ▼
┌─────────────────────┐     ┌──────────────────────────┐
│ Prompt Context       │◄────│ 🔮 RAG / Retrieval       │
│ Builder              │     │    (FUTURO)              │
│                      │     │  normative_contexts={}   │
│                      │     │  literature_contexts={}  │
└────────┬────────────┘     └──────────────────────────┘
         │ EquipmentLLMInput[]
         ▼
┌─────────────────────┐
│ User Prompt Builder  │  ← blocos opcionais auto-incluídos
└────────┬────────────┘
         ▼
┌─────────────────────┐
│ Narrative Generator  │  ← LLM call + validate + retry
└─────────────────────┘
```

O **ponto de injeção** é na chamada a `build_all_equipment_prompt_contexts()`
(ou `build_equipment_prompt_context()` para chamada unitária).

---

## 2. Modelos de dados

### `NormativeExcerpt`

```python
from app.domain.entities import NormativeExcerpt

excerpt = NormativeExcerpt(
    source="NFPA 652:2022",           # obrigatório, max 200 chars
    section="8.2.1",                   # opcional, max 50 chars
    text="Sistemas de captação...",    # obrigatório, max 2000 chars
    relevance_score=0.92,              # opcional, 0.0–1.0
)
```

### `LiteratureExcerpt`

```python
from app.domain.entities import LiteratureExcerpt

excerpt = LiteratureExcerpt(
    source="Eckhoff, R.K. (2003). Dust Explosions...",  # max 300 chars
    text="A MEC típica para grãos...",                   # max 2000 chars
    relevance_score=0.85,                                # opcional
)
```

Ambos são Pydantic models **frozen** (imutáveis).

---

## 3. Como injetar trechos

### 3.1 Per-equipment (unitário)

```python
from app.domain.services.equipment_prompt_context import (
    build_equipment_prompt_context,
)

llm_input = build_equipment_prompt_context(
    equipment_context=ctx,
    normas_aplicaveis=normas,
    normative_context=[excerpt1, excerpt2],   # ← novo
    literature_context=[lit_excerpt1],         # ← novo
)
```

### 3.2 Batch (todos os equipamentos)

Os parâmetros batch aceitam **dicionários** `equipment_name → list[Excerpt]`:

```python
from app.domain.services.equipment_prompt_context import (
    build_all_equipment_prompt_contexts,
)

norm_map: dict[str, list[NormativeExcerpt]] = {
    "Elevador de Canecas EC-01": [excerpt_nfpa],
    "Peneira Vibratória PV-03": [excerpt_abnt],
}

lit_map: dict[str, list[LiteratureExcerpt]] = {
    "Elevador de Canecas EC-01": [excerpt_eckhoff],
}

llm_inputs = build_all_equipment_prompt_contexts(
    equipment_contexts=contexts,
    normas_aplicaveis=normas,
    normative_contexts=norm_map,      # ← novo
    literature_contexts=lit_map,      # ← novo
)
```

Equipamentos sem chave no mapa recebem listas vazias (sem bloco no prompt).

---

## 4. Como os trechos aparecem no prompt

Quando `normative_context` ou `literature_context` não estão vazios, o
`build_equipment_user_prompt()` inclui automaticamente blocos extras:

```
### Trechos Normativos Relevantes ###
[1] NFPA 652:2022, seção 8.2.1: Sistemas de captação devem operar...
[2] ABNT NBR 16577: Requisitos gerais de segurança...

### Trechos de Literatura Técnica ###
[1] Eckhoff (2003): A MEC típica para grãos de soja...
```

Os blocos só aparecem quando há pelo menos um trecho. Sem trechos = sem bloco.

---

## 5. Limites

| Campo                | Limite            |
|----------------------|-------------------|
| `normative_context`  | máx. 10 trechos   |
| `literature_context` | máx. 10 trechos   |
| `source` (normative) | máx. 200 chars    |
| `source` (literature)| máx. 300 chars    |
| `section`            | máx.  50 chars    |
| `text`               | máx. 2 000 chars  |
| `relevance_score`    | 0.0–1.0 (opcional)|

---

## 6. Padrão de adaptador futuro (exemplo)

```python
# app/adapters/norms/abnt_retriever.py  (NÃO IMPLEMENTADO)

from app.domain.entities import NormativeExcerpt


class ABNTRetriever:
    """Retriever de trechos normativos via vector store."""

    async def retrieve_for_equipment(
        self,
        equipment_name: str,
        perigos: list[str],
        *,
        top_k: int = 5,
    ) -> list[NormativeExcerpt]:
        # 1. Montar query semântica a partir de equipment_name + perigos
        # 2. Consultar vector store (e.g. Supabase pgvector, Pinecone)
        # 3. Mapear resultados para NormativeExcerpt
        # 4. Filtrar por relevance_score mínimo
        # 5. Retornar top_k trechos
        ...
```

### Integração no `process_job.py`

```python
# Futuro — antes de build_all_equipment_prompt_contexts()
retriever = ABNTRetriever(vector_store=...)

norm_map = {}
for ctx in equipment_contexts:
    excerpts = await retriever.retrieve_for_equipment(
        ctx.equipment_name,
        list(ctx.identificacao_dos_perigos),
    )
    if excerpts:
        norm_map[ctx.equipment_name] = excerpts

equipment_llm_inputs = build_all_equipment_prompt_contexts(
    equipment_contexts,
    normas_principais,
    normative_contexts=norm_map,  # ← injeção
)
```

---

## 7. Retrocompatibilidade

- Todos os campos são **opcionais** com default `[]`.
- Código existente que não passa `normative_context` / `literature_context`
  continua funcionando sem alterações.
- A função `build_equipment_user_prompt()` também aceita keyword args
  legados (`normative_excerpts`, `literature_excerpts`) como `list[str]`
  e os mescla com os dados do model.

---

## 8. Testes

Testes existentes cobrem:

| Arquivo                              | Cenários novos                    |
|--------------------------------------|-----------------------------------|
| `test_equipment_user_prompt.py`      | Model-level excerpts, merge, etc. |
| `test_equipment_prompt_context.py`   | Passthrough, batch maps, default  |

Executar: `pytest tests/ -v` para validar.
