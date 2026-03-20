# Mapeamento de Custo e Uso de LLM — AutomacaoDHA

> Gerado em 2026-03-17 — Baseado no código real do projeto

---

## 1. Resumo Executivo

O sistema usa **2 providers** e **2 modelos** para geração de laudos técnicos:

| Provider   | Modelo                    | Tipo       | Custo (USD/1K tokens)      |
|------------|---------------------------|------------|---------------------------|
| OpenRouter | `openai/gpt-4o`           | Generation | Input: $0.0025 / Output: $0.010 |
| OpenAI     | `text-embedding-3-small`  | Embedding  | Input: $0.00002 / Output: $0.000 |

**Fluxo principal**: `POST /process` (pipeline de job assíncrono)  
**Fluxo legado**: `POST /uploads` (upload síncrono, sem RAG/per-equipment)

---

## 2. Inventário de Pontos de Chamada LLM

### CP-01: Seções Globais do Laudo (Generation)

| Campo | Valor |
|-------|-------|
| **Arquivo** | `app/adapters/llm/openrouter_client.py` |
| **Classe** | `OpenRouterClient` |
| **Função** | `generate_sections(context)` |
| **Finalidade** | Gera introdução, metodologia, conclusão e materiais do relatório |
| **Modelo** | `openai/gpt-4o` (configurável via `LLM_MODEL`) |
| **Provider** | OpenRouter |
| **Tipo** | `generation` |
| **Retry** | Se JSON inválido: 1 retry com prompt reforçado (máx 2 chamadas) |
| **Input estimado** | 2.000–5.000 tokens |
| **Output estimado** | 1.000–3.000 tokens |
| **Custo estimado** | $0.005–$0.035 por chamada |

### CP-02: Narrativa Per-Equipment (Generation)

| Campo | Valor |
|-------|-------|
| **Arquivo** | `app/adapters/llm/openrouter_client.py` |
| **Classe** | `OpenRouterClient` |
| **Função** | `call_chat(system_prompt, user_prompt)` |
| **Finalidade** | Gera recomendações técnicas e justificativas por equipamento |
| **Modelo** | `openai/gpt-4o` (configurável via `LLM_MODEL`) |
| **Provider** | OpenRouter |
| **Tipo** | `generation` |
| **Retry** | Attempt 1: padrão → Attempt 2: reforçado → Attempt 3: fallback determinístico |
| **Input estimado** | 2.500–4.000 tokens (system ~2.500 + user 500–1.500) |
| **Output estimado** | 500–1.500 tokens |
| **Custo estimado** | $0.004–$0.015 por equipamento |

### CP-03: Embedding para RAG (Embedding)

| Campo | Valor |
|-------|-------|
| **Arquivo** | `app/adapters/norms/embedding_provider.py` |
| **Classe** | `OpenAIEmbeddingProvider` |
| **Função** | `embed_text(text)` |
| **Finalidade** | Gera embedding vetorial da query semântica para busca de normas ABNT |
| **Modelo** | `text-embedding-3-small` (configurável via `EMBEDDING_MODEL`) |
| **Provider** | OpenAI |
| **Tipo** | `embedding` |
| **Retry** | Sem retry — falha retorna resultado vazio (graceful degradation) |
| **Input estimado** | 50–200 tokens |
| **Output** | 0 tokens (retorno é vetor, não texto) |
| **Custo estimado** | $0.000001–$0.000004 por chamada |

---

## 3. Fluxos e Custos por Endpoint

### 3.1 `POST /process` — Pipeline Principal de Job

**Arquivo**: `app/api/routes/process.py` → `ProcessJobUseCase.execute()`  
**Execução**: Assíncrono (background task)

#### Chamadas LLM por etapa:

```
┌─────────────────────────────────────────────────────────────┐
│                    POST /process                             │
│                                                              │
│  1. data_processing                                          │
│     └─ RAG embedding: N chamadas (1/equip) ─── CP-03        │
│        Custo: ~$0.000005/equip (desprezível)                 │
│                                                              │
│  2. llm_analysis                                             │
│     ├─ Seções globais: 1-2 chamadas ──────── CP-01           │
│     │  Custo: ~$0.010-$0.035                                 │
│     │                                                        │
│     └─ Per-equipment: N-2N chamadas ──────── CP-02           │
│        Custo: ~$0.008/equip (maior vilão)                    │
│                                                              │
│  3. pdf_rendering ── sem LLM                                 │
│  4. report_storage ── sem LLM                                │
└─────────────────────────────────────────────────────────────┘
```

#### Estimativa de custo para N equipamentos:

| Métrica | 3 equip. | 5 equip. | 10 equip. | 20 equip. |
|---------|----------|----------|-----------|-----------|
| Chamadas embedding | 3 | 5 | 10 | 20 |
| Chamadas geração | 4 | 6 | 11 | 21 |
| **Total chamadas** | **7** | **11** | **21** | **41** |
| Custo embedding | $0.00002 | $0.00003 | $0.00005 | $0.0001 |
| Custo global | $0.015 | $0.015 | $0.015 | $0.020 |
| Custo per-equip | $0.024 | $0.040 | $0.080 | $0.160 |
| **Custo total** | **$0.039** | **$0.055** | **$0.095** | **$0.180** |
| % per-equip | 62% | 73% | 84% | 89% |

> ⚠️ Com retries (pior caso), chamadas de geração podem dobrar.

#### Cenário DEVLLM=true (desenvolvimento):

| Métrica | Valor |
|---------|-------|
| Chamadas embedding | 1 |
| Chamadas geração | 2 (1 global + 1 per-equipment) |
| Custo estimado | ~$0.020 |
| Economia vs 10 equip | ~79% |

### 3.2 `POST /uploads` — Pipeline Legado

**Arquivo**: `app/api/routes/uploads.py` → `ProcessUploadUseCase.execute()`  
**Execução**: Síncrono

| Etapa | Chamadas | Custo |
|-------|----------|-------|
| Seções globais (CP-01) | 1-2 | $0.010-$0.035 |
| **Total** | **1-2** | **$0.010-$0.035** |

> Este fluxo **não usa RAG** e **não gera narrativas per-equipment**.

---

## 4. Distribuição de Custos — Onde Estou Gastando Mais

### Por tipo de chamada (job típico com 10 equipamentos):

```
Per-equipment narratives ████████████████████████████  84% (~$0.080)
Seções globais           ████                          16% (~$0.015)
RAG embeddings           ▏                             <0.1% (~$0.00005)
```

### Por componente de custo:

```
Output tokens (generation) ████████████████████         75%
Input tokens (generation)  ██████                       24%
Input tokens (embedding)   ▏                            <1%
```

### Maior vilão: **Chamadas per-equipment com GPT-4o**

Cada equipamento gera 1-2 chamadas ao GPT-4o com system prompt de ~2.500 tokens.
O system prompt é **idêntico** para todos os equipamentos do mesmo perfil,
mas é enviado N vezes (uma por equipamento).

---

## 5. Contagem de Chamadas por Relatório

Para um relatório completo (pipeline `POST /process`):

| Cenário | Embedding | Geração | Total |
|---------|-----------|---------|-------|
| 3 equipamentos (sem retry) | 3 | 4 | 7 |
| 5 equipamentos (sem retry) | 5 | 6 | 11 |
| 10 equipamentos (sem retry) | 10 | 11 | 21 |
| 10 equipamentos (todos com retry) | 10 | 21 | 31 |
| DEVLLM=true (qualquer N) | 1 | 2 | 3 |

**Fórmula**:
- Embedding: `N` (ou 0 se RAG desabilitado)
- Geração: `1 + N` (melhor caso) a `2 + 2N` (pior caso)
- Total: `N + 1 + N` = `2N + 1` (melhor caso)

---

## 6. Instrumentação Implementada

### 6.1 Módulo de tracking

**Arquivo**: `app/infrastructure/llm_cost_tracker.py`

Registra automaticamente cada chamada com:
- Fluxo / endpoint / job
- Etapa (global_sections, per_equipment_narrative, rag_embedding)
- Provider e modelo
- Input / output / total tokens
- Fonte dos tokens (API real ou estimativa)
- Custo estimado em USD
- Duração em ms
- Sucesso/erro
- Job ID e nome do equipamento

### 6.2 Pontos instrumentados

| Arquivo | O que é rastreado |
|---------|-------------------|
| `openrouter_client.py` | Todas as chamadas de geração (generate_sections + call_chat) |
| `embedding_provider.py` | Todas as chamadas de embedding |
| `process_job.py` | Contexto de fluxo (job_id, step, flow) para cada chamada |
| `process_upload.py` | Contexto de fluxo (flow=upload) para seções globais |

### 6.3 Fonte dos dados de token

| Situação | Fonte | Precisão |
|----------|-------|----------|
| OpenRouter retorna `usage` na resposta | API real | **Exata** |
| OpenAI Embedding retorna `usage` | API real | **Exata** |
| API não retorna `usage` | Estimativa (~4 chars/token) | **Aproximada** |

O campo `tokens_source` em cada registro indica se os tokens vieram da API (`"api"`) ou foram estimados (`"estimate"`).

### 6.4 Endpoints de consulta

| Endpoint | Descrição |
|----------|-----------|
| `GET /costs/summary` | Resumo geral (total tokens, custo, chamadas) |
| `GET /costs/by-flow` | Custos por fluxo (process_job vs upload) |
| `GET /costs/by-step` | Custos por etapa (global_sections, per_equipment, rag_embedding) |
| `GET /costs/by-model` | Custos por modelo (gpt-4o vs embedding) |
| `GET /costs/by-job` | Custos por job_id (com detalhamento per-equipment) |
| `GET /costs/ranking` | Chamadas mais caras |
| `GET /costs/records` | Todos os registros em JSON |
| `GET /costs/records/csv` | Todos os registros em CSV |
| `POST /costs/persist` | Força persistência em disco |
| `DELETE /costs/records` | Limpa registros em memória |

### 6.5 Persistência

Os registros são automaticamente salvos em `output/llm_usage_log.json` a cada 5 chamadas.
Também são persistidos ao final do pipeline de cada job.

---

## 7. Sugestões de Otimização — Priorizadas por Impacto

### 🔴 ALTO IMPACTO

#### OPT-01: Modelo mais barato para per-equipment

**Problema**: Todas as chamadas per-equipment usam GPT-4o ($0.010/1K output).  
**Solução**: Usar GPT-4o-mini ($0.0006/1K output) para narrativas per-equipment.  
**Economia**: ~85% do custo per-equipment.  
**Implementação**: Adicionar variável `LLM_MODEL_PER_EQUIPMENT` com default `openai/gpt-4o-mini`.
O GPT-4o-mini é capaz de seguir instruções JSON e gerar texto técnico adequado para esta tarefa.

| Cenário (10 equip) | GPT-4o | GPT-4o-mini | Economia |
|---------------------|--------|-------------|----------|
| Custo per-equipment | $0.080 | $0.012 | 85% |
| Custo total job | $0.095 | $0.027 | 72% |

#### OPT-02: Structured Outputs (JSON Schema)

**Problema**: Retries de formato JSON aumentam chamadas em até 50%.  
**Solução**: Usar `response_format: { type: "json_schema", json_schema: {...} }` no payload.  
**Economia**: Elimina ~100% dos retries de formato.  
**Implementação**: Definir JSON schemas para os dois tipos de resposta e enviar no payload.

#### OPT-03: Batching de equipamentos similares

**Problema**: Cada equipamento com perigos idênticos gera chamada separada.  
**Solução**: Agrupar 2-3 equipamentos similares em uma única chamada.  
**Economia**: 30-50% das chamadas per-equipment.  
**Risco**: Aumenta complexidade de parsing e pode misturar contextos.

### 🟡 MÉDIO IMPACTO

#### OPT-04: Compressão do system prompt per-equipment

**Problema**: System prompt fixo de ~2.500 tokens é enviado N vezes.  
**Solução**: Reescrever para ~1.500 tokens sem perder instruções essenciais.  
**Economia**: ~20-30% dos input tokens per-equipment.  
**Implementação**: Refatorar `prompts/equipment_system_prompt.txt`.

#### OPT-05: Cache de seções globais

**Problema**: Reprocessamento do mesmo job regenera seções globais.  
**Solução**: Cache baseado em hash dos dados de entrada (rows + metadata).  
**Economia**: 100% em reprocessamentos.  
**Implementação**: SHA-256 do contexto → lookup em cache (memória/Redis/disco).

#### OPT-06: Reduzir taxa de retry

**Problema**: Retries dobram o custo quando ocorrem.  
**Solução**: Análise dos logs de retry para identificar padrões de falha e ajustar prompts.  
**Economia**: Reduz chamadas extras em até 50%.  

### 🟢 BAIXO IMPACTO

#### OPT-07: Cache de embeddings

**Problema**: Mesmos equipamentos em jobs diferentes geram embeddings repetidos.  
**Solução**: Cache em memória por hash do query text.  
**Economia**: Desprezível em custo (~$0.000004/chamada), mas reduz latência.

---

## 8. Tabela de Custos por Modelo

| Modelo | Input/1K tok | Output/1K tok | Uso no projeto |
|--------|-------------|---------------|----------------|
| `openai/gpt-4o` | $0.0025 | $0.010 | Geração (atual) |
| `openai/gpt-4o-mini` | $0.00015 | $0.0006 | Alternativa per-equipment |
| `openai/gpt-4.1` | $0.002 | $0.008 | Alternativa futura |
| `openai/gpt-4.1-mini` | $0.0004 | $0.0016 | Alternativa futura |
| `openai/gpt-4.1-nano` | $0.0001 | $0.0004 | Alternativa para tarefas simples |
| `text-embedding-3-small` | $0.00002 | $0.000 | Embedding RAG (atual) |
| `text-embedding-3-large` | $0.00013 | $0.000 | Alternativa embedding |

---

## 9. Perguntas e Respostas

### Onde estou gastando mais?
**Nas chamadas per-equipment** (CP-02). Com 10 equipamentos, representam ~84% do custo total.

### Quanto custa cada fluxo?
- `POST /process` com 10 equip: **~$0.095** (melhor caso)
- `POST /uploads`: **~$0.015**

### Quantas chamadas por relatório?
- Com 10 equipamentos: **21 chamadas** (10 embedding + 1 global + 10 per-equipment)
- Pior caso com retries: **31 chamadas**

### Onde posso reduzir custo sem perder qualidade?
1. **GPT-4o-mini para per-equipment** → economia de 72% no custo total
2. **Structured outputs** → elimina retries de formato
3. **Cache de seções globais** → elimina custo em reprocessamentos

### Custo mensal estimado?
| Volume | Custo GPT-4o | Custo com GPT-4o-mini |
|--------|-------------|----------------------|
| 10 jobs/dia (10 equip) | ~$28.50/mês | ~$8.10/mês |
| 50 jobs/dia (10 equip) | ~$142.50/mês | ~$40.50/mês |
| 100 jobs/dia (10 equip) | ~$285/mês | ~$81/mês |

---

## 10. Arquivos Modificados/Criados

### Novos arquivos:
| Arquivo | Propósito |
|---------|-----------|
| `app/infrastructure/llm_cost_tracker.py` | Módulo de tracking de custos LLM |
| `app/api/routes/costs.py` | Endpoints REST para consultar custos |
| `docs/llm_cost_mapping.json` | Inventário JSON estruturado |
| `docs/llm-cost-tracking.md` | Este documento |

### Arquivos modificados:
| Arquivo | Mudança |
|---------|---------|
| `app/adapters/llm/openrouter_client.py` | + tracking de custo em cada chamada + captura de usage da API |
| `app/adapters/norms/embedding_provider.py` | + tracking de custo em cada chamada + captura de usage da API |
| `app/application/use_cases/process_job.py` | + contexto de tracking (flow/step/job_id) para cada etapa |
| `app/application/use_cases/process_upload.py` | + contexto de tracking (flow=upload) para seções globais |
| `app/api/main.py` | + registro do router `/costs` |
