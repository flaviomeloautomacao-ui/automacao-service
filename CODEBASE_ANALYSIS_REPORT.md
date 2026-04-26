# Análise Completa do Backend — PythonServiceAutomacao

**Data:** 2026-03-14  
**Escopo:** Todos os arquivos em `app/api/`, `app/application/`, `app/adapters/`, `app/domain/`, `app/infrastructure/`, `app/scripts/`  
**Total de arquivos analisados:** ~45 arquivos Python

---

## Sumário Executivo

O codebase segue uma arquitetura hexagonal (ports & adapters) bem estruturada, com separação clara entre domínio, aplicação e infraestrutura. No entanto, foram identificadas **6 issues críticas**, **12 issues médias** e **8 issues baixas** distribuídas entre as categorias de segurança, performance, consistência de código, concorrência e design.

---

## 🔴 CRITICAL (6 issues)

### C-01: httpx.AsyncClient criado por request — sem connection pooling

**Arquivos afetados:**
- `app/adapters/llm/openrouter_client.py` (linha 322)
- `app/adapters/norms/embedding_provider.py` (linha 149)
- `app/adapters/storage/supabase_storage.py` (linhas 120, 174, 222)

**Categoria:** Performance / Recurso  
**Impacto:** Cada chamada HTTP cria e destrói um `httpx.AsyncClient`, o que implica: novo TCP handshake, nova negociação TLS, nenhum reuso de conexões HTTP/2. Em cenários com múltiplos equipamentos (8+), isso significa ~40+ handshakes TLS desnecessários por job.

```python
# openrouter_client.py L322
async with httpx.AsyncClient(timeout=self._timeout) as client:
    response = await client.post(url, headers=headers, json=payload)

# supabase_storage.py L120
async with httpx.AsyncClient(timeout=self._UPLOAD_TIMEOUT) as client:
    response = await client.put(url, ...)

# embedding_provider.py L149
async with httpx.AsyncClient(timeout=self._timeout) as client:
    response = await client.post(url, ...)
```

**Correção recomendada:** Criar um `httpx.AsyncClient` como atributo de instância (com `limits=httpx.Limits(max_connections=10)`) e reutilizá-lo durante toda a vida do objeto. Implementar `async def close()` para cleanup e chamar no lifespan do FastAPI.

---

### C-02: `_do_request()` retorna tupla mas type hints e tenacity esperam `str`

**Arquivo:** `app/adapters/llm/openrouter_client.py` (linhas 325–380)  
**Categoria:** Lógica / Type Safety

A inner function `_do_request()` está decorada com `@retry` e retorna `(content, api_usage)` (tupla), mas o type annotation implícito e o padrão tenacity tratam como `str`. O código funciona por acidente porque o resultado é desempacotado na linha 389:

```python
# L376-377 — função retorna tupla
return content, api_usage

# L389 — desempacotamento correto, mas sem type safety
result_tuple = await _do_request()
content_result, api_usage = result_tuple
```

**Risco:** Se alguém alterar a inner function sem atualizar o desempacotamento, produzirá erro silencioso. Sem type hints explícitos, ferramentas de análise estática não detectam o mismatch.

**Correção recomendada:** Tipar o retorno como `tuple[str, dict | None]` e incluir um `NamedTuple` ou `dataclass` para clareza.

---

### C-03: Rate Limiter com crescimento ilimitado de memória e não thread-safe

**Arquivo:** `app/api/middleware/rate_limit.py` (linhas 27–78)  
**Categoria:** Memory Leak / Concorrência

```python
# L27 — dict global que cresce indefinidamente
_job_timestamps: dict[str, list[float]] = defaultdict(list)

# L44-46 — cleanup só remove > 1 hora, mas lista pode crescer entre cleanups
_job_timestamps[key] = [
    t for t in _job_timestamps[key] if now - t < 3600
]
```

**Problemas:**
1. **Memory leak:** Lista de timestamps cresce sem limite absoluto entre os cleanups. Com 50 jobs/hora × 24h = 1200 entries retidas.
2. **Não thread-safe:** Operações de leitura e escrita no dict global não têm lock. Em deploy com múltiplos workers (uvicorn `--workers > 1`), cada worker tem dict separado — rate limit não é efetivo.
3. **Sem TTL/eviction:** Chaves que param de ser usadas nunca são removidas.

**Correção recomendada:** Para single-instance, usar `asyncio.Lock` + limite máximo de entries. Para multi-worker, migrar para Redis com `INCR` + `EXPIRE`.

---

### C-04: ProcessJobUseCase acessa membros privados de ProcessUploadUseCase

**Arquivo:** `app/application/use_cases/process_job.py` (múltiplas linhas)  
**Categoria:** Encapsulamento / Manutenibilidade

```python
# Acessos a atributos _private do upload_use_case:
self._uc._llm          # client LLM
self._uc._storage      # client Storage
self._uc._bucket       # nome do bucket
self._uc._pdf_renderer # renderer PDF
```

**Impacto:** Qualquer refatoração interna de `ProcessUploadUseCase` (renomear atributos, mudar inicialização) quebra `ProcessJobUseCase` silenciosamente. Viola o princípio de encapsulamento da arquitetura hexagonal.

**Correção recomendada:** Expor esses colaboradores via properties públicas em `ProcessUploadUseCase` ou injetar diretamente em `ProcessJobUseCase` via constructor.

---

### C-05: SQL f-string para table name em NormVectorRepository

**Arquivo:** `app/adapters/norms/norm_repository.py` (linhas 108–119, 195–207)  
**Categoria:** Segurança (SQL Injection potencial)

```python
# L108-119
sql = text(f"""
    SELECT
        id,
        {DEFAULT_CONTENT_COLUMN} AS content,
        {DEFAULT_METADATA_COLUMN} AS metadata,
        1 - ({DEFAULT_EMBEDDING_COLUMN} <=> (:query_embedding)::vector) AS similarity
    FROM {self._table_name}
    WHERE ...
""")
```

**Análise de risco atual:** O `table_name` vem de `Settings.RAG_NORM_TABLE` (env var), não de input do usuário. O risco imediato é **baixo** neste momento, mas:
1. Nenhuma validação/sanitização do valor é feita.
2. Se alguém passar `table_name` via parâmetro de API no futuro, vira SQL injection.
3. Column names também são interpolados sem validação.

**Correção recomendada:** Validar `table_name` contra whitelist (`^[a-zA-Z_][a-zA-Z0-9_]*$`) no construtor. Ou usar `sqlalchemy.table()` para referências dinâmicas seguras.

---

### C-06: Auth middleware desabilitada em desenvolvimento sem aviso claro

**Arquivo:** `app/api/middleware/auth.py`  
**Categoria:** Segurança

```python
async def verify_internal_api_key(...):
    settings = get_settings()
    # Se INTERNAL_API_KEY não estiver definida → SKIP AUTH
    if not settings.INTERNAL_API_KEY:
        return  # ← Qualquer pessoa pode chamar a API
```

**Risco:** Se a env var `INTERNAL_API_KEY` não for definida em produção (deploy incorreto), a API fica totalmente exposta sem autenticação. Não há proteção failsafe.

**Correção recomendada:** Em produção (`ENV=production`), lançar erro se `INTERNAL_API_KEY` não estiver definida, em vez de silenciosamente desabilitar a auth.

---

## 🟡 MEDIUM (12 issues)

### M-01: Rota `GET /reports/{report_id}` retorna HTTP 200 com body de erro em vez de 404

**Arquivo:** `app/api/routes/documents.py` (linhas 42–43)  
**Categoria:** Inconsistência de API / REST

```python
if report is None:
    return {"data": None, "error": {"code": "NOT_FOUND", "message": "Relatório não encontrado."}}
    # ↑ Retorna 200 OK com body de erro — viola convenção REST
```

**Impacto:** Clientes HTTP que checam status code receberão `200` e precisarão parsear o body para detectar "not found". Quebra integração com proxies, caches e clients padrão.

**Correção recomendada:** Usar `raise HTTPException(status_code=404, detail="...")`.

---

### M-02: `get_storage()` e `get_llm()` criam nova instância a cada chamada

**Arquivo:** `app/infrastructure/dependencies.py` (linhas 166–177, 189–211)  
**Categoria:** Performance / Design

```python
def get_storage() -> "SupabaseStorage":
    settings = get_settings()
    return SupabaseStorage(...)  # Nova instância a cada Depends()

def get_llm() -> "OpenRouterClient":
    return OpenRouterClient(...)  # Nova instância a cada Depends()
```

**Impacto:** Combinado com C-01 (sem connection pooling), cada request cria novos objetos que nunca reutilizam conexões. O `OpenRouterClient` tem state interno (circuit breaker, tracking context) que é perdido a cada recriação.

**Correção recomendada:** Usar `@lru_cache` ou manter singletons no app state do FastAPI (`app.state.llm_client`).

---

### M-03: `MockLLMClient.call_chat()` não aceita `model_override` como keyword argument

**Arquivo:** `app/adapters/llm/mock_client.py` (linhas 42–60)  
**Categoria:** Inconsistência de Interface

```python
# MockLLMClient
async def call_chat(self, system: str, user: str) -> str:
    # ↑ SEM model_override

# OpenRouterClient  
async def call_chat(self, system_prompt: str, user_prompt: str, *, model_override: str | None = None) -> str:
    # ↑ COM model_override
```

**Impacto:** O `generate_equipment_narrative()` tenta chamar `llm_call(sys, usr, model_override)` com 3 argumentos. O fallback `try/except TypeError` em `_do_call` mascara o problema, mas adiciona overhead e esconde bugs reais.

**Correção recomendada:** Adicionar `*, model_override: str | None = None` na assinatura de `MockLLMClient.call_chat()`.

---

### M-04: `BudgetGuard.__init__()` lê `os.environ` diretamente em vez de usar Settings injetado

**Arquivo:** `app/domain/services/budget_guard.py` (linhas 44–53)  
**Categoria:** Inconsistência de Design / Testabilidade

```python
def __init__(self, settings: "Settings | None" = None) -> None:
    self._max_cost_per_job: float = float(
        os.environ.get("LLM_MAX_COST_PER_JOB_USD", "2.00")
    )
    self._max_cost_per_day: float = float(
        os.environ.get("LLM_MAX_COST_PER_DAY_USD", "50.00")
    )
    # ↑ Ignora completamente o parâmetro `settings`
```

**Impacto:** O parâmetro `settings` é aceito mas **nunca usado**. Testes unitários que passam Settings customizado não conseguem overridar os limites. Viola a arquitetura de injeção de dependências do projeto.

**Correção recomendada:** Usar `settings.LLM_MAX_COST_PER_JOB_USD` (ou adicionar esses campos ao Settings se ausentes).

---

### M-05: Manual async generator protocol em `get_abnt_retriever()`

**Arquivo:** `app/infrastructure/dependencies.py` (linhas 350–395)  
**Categoria:** Fragilidade de Código

```python
rag_session_gen = _get_rag_session()
rag_session = await rag_session_gen.__anext__()
try:
    # ... usar sessão ...
    yield retriever
finally:
    try:
        await rag_session_gen.__anext__()
    except StopAsyncIteration:
        pass
```

**Risco:** Manipulação manual do protocolo de async generator (`__anext__`) é frágil. Se `_get_rag_session()` mudar a lógica interna (ex: ter 2 yields), o cleanup pode falhar silenciosamente ou não executar rollback/commit da sessão.

**Correção recomendada:** Usar `contextlib.asynccontextmanager` para encapsular a sessão RAG ou criar uma factory function dedicada que retorna `AsyncContextManager[AsyncSession]`.

---

### M-06: Sem CORS middleware configurado

**Arquivo:** `app/api/main.py`  
**Categoria:** Funcionalidade / Segurança

`create_app()` não registra `CORSMiddleware`. Se o frontend Next.js faz chamadas diretas à API Python (em vez de via proxy), as requests serão bloqueadas pelo navegador.

**Correção recomendada:** Adicionar:
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=[...], ...)
```

---

### M-07: Sem lifecycle events (startup/shutdown)

**Arquivo:** `app/api/main.py`  
**Categoria:** Resource Management

Não há `@app.on_event("startup")` / `@app.on_event("shutdown")` nem `lifespan` context manager. Consequências:
- Conexões de database pool não são pre-aquecidas no startup
- httpx clients (se refatorados para singleton) não terão cleanup no shutdown
- Logs de startup/shutdown para observabilidade estão ausentes

**Correção recomendada:** Usar `lifespan` async context manager do FastAPI.

---

### M-08: Circuit breaker state não é persistido entre recriações do `OpenRouterClient`

**Arquivo:** `app/adapters/llm/openrouter_client.py` (linhas 127–128)  
**Categoria:** Lógica

```python
self._consecutive_failures: int = 0
self._circuit_breaker_threshold: int = 5
```

Combinado com M-02 (nova instância a cada chamada), o circuit breaker **nunca dispara** — `_consecutive_failures` sempre começa em 0.

**Correção recomendada:** Tornar o client singleton OU externalizar o state do circuit breaker para módulo-level ou Redis.

---

### M-09: File upload lê arquivo inteiro em memória

**Arquivo:** `app/api/routes/uploads.py`  
**Categoria:** Performance / Resource

```python
file_bytes = await file.read()  # Lê o arquivo INTEIRO na RAM
```

Para planilhas grandes (10+ MB), isso consome memória proporcional ao tamanho do arquivo. Sem limite de tamanho no upload.

**Correção recomendada:** Adicionar validação de tamanho máximo e considerar streaming para disco temporário se necessário.

---

### M-10: `JobRepository` faz commit individual por cada update de step

**Arquivo:** `app/adapters/db/job_repository.py`  
**Categoria:** Performance

Cada chamada a `update_job_status()`, `start_step()`, `complete_step()`, `fail_step()` faz:
```python
await self._session.commit()
```

No pipeline de um job com 5 steps × 2 updates cada = ~10 commits individuais quando poderiam ser batched.

**Correção recomendada:** Considerar flush + commit de batch no caller, ou usar savepoints para operações intermediárias.

---

### M-11: `lazy="selectin"` em TODAS as relationships dos ORM models

**Arquivo:** `app/adapters/db/models.py`, `app/adapters/db/job_models.py`  
**Categoria:** Performance

```python
# Exemplo em job_models.py
steps = relationship("JobStep", back_populates="job", lazy="selectin")
rows = relationship("SpreadsheetRowModel", back_populates="upload", lazy="selectin")
```

`selectin` loading emite queries extras automaticamente toda vez que o parent é carregado, mesmo quando os filhos não são necessários. Para queries que só precisam de dados do job (sem steps), isso é overhead desnecessário.

**Correção recomendada:** Usar `lazy="raise"` ou `lazy="noload"` como default e eager-load explicitamente onde necessário via `options(selectinload(...))`.

---

### M-12: Duplicação de lógica de JSON parsing entre dois módulos

**Arquivos:**
- `app/domain/services/json_utils.py` — `parse_llm_json()`
- `app/adapters/llm/openrouter_client.py` — `_try_parse_json()`

Ambos fazem parse de JSON com remoção de blocos markdown. O `_try_parse_json` adiciona validação de chaves obrigatórias, mas a lógica base é duplicada.

**Correção recomendada:** Consolidar em `json_utils.py` com parâmetro opcional `required_keys`.

---

## 🟢 LOW (8 issues)

### L-01: `CleanupExpiredUseCase` é placeholder (não implementado)

**Arquivo:** `app/application/use_cases/cleanup_expired.py`  
**Categoria:** Funcionalidade incompleta

O caso de uso existe mas é `pass` / placeholder. Arquivos temporários de uploads expirados nunca são limpos automaticamente.

---

### L-02: `domain/schemas/__init__.py` e `application/dto/__init__.py` são arquivos vazios

**Arquivos:** `app/domain/schemas/__init__.py`, `app/application/dto/__init__.py`  
**Categoria:** Dead code / Organização

Módulos declarados na arquitetura mas sem conteúdo. Sugere features planejadas mas não implementadas.

---

### L-03: Sem validação de tamanho máximo de arquivo no upload

**Arquivo:** `app/api/routes/uploads.py`  
**Categoria:** Robustez

Não há check de `Content-Length` ou validação de bytes máximos antes de ler o arquivo. Um upload de 1 GB seria aceito.

**Correção recomendada:** Adicionar `UploadFile` com validação ou middleware de tamanho máximo.

---

### L-04: `request.client` pode ser `None` no rate limiter

**Arquivo:** `app/api/middleware/rate_limit.py` (linhas 58, 68)  

```python
request.client.host if request.client else "unknown"
```

Tratado corretamente com fallback, mas o rate limiting usa chave `"global"` hardcoded em vez de IP/user — portanto um único client abusivo bloqueia todos os demais.

---

### L-05: `_SYSTEM_PROMPT_CACHE` usa variável global mutável com `global` keyword

**Arquivo:** `app/domain/services/equipment_narrative_generator.py` (linhas 70–78)  
**Categoria:** Design

```python
_SYSTEM_PROMPT_CACHE: str | None = None

def _load_base_system_prompt() -> str:
    global _SYSTEM_PROMPT_CACHE
    ...
```

Funciona em single-process, mas em produção com `--workers > 1` cada worker terá cache independente (sem problema funcional, mas desperdício mínimo de memória).

---

### L-06: `version_snapshot.py` calcula hashes mas ignora `rag_config`, `llm_model` e `embedding_model`

**Arquivo:** `app/domain/services/version_snapshot.py`  
**Categoria:** Lógica

```python
def compute_version_fingerprint(...) -> tuple[str, str]:
    prompt_hash = hashlib.sha256(system_prompt.encode()).hexdigest()
    schema_hash = hashlib.sha256(
        json.dumps(output_schema, sort_keys=True).encode()
    ).hexdigest()
    return prompt_hash, schema_hash
    # ↑ rag_config, llm_model, embedding_model são IGNORADOS
```

Os parâmetros `rag_config`, `llm_model` e `embedding_model` são aceitos pela função mas **nunca usados** no cálculo do fingerprint. Mudanças nesses valores não alteram o hash, comprometendo a rastreabilidade.

---

### L-07: `_shrink_to_budget` tem safety limit de 50 iterações mas sem log quando atinge o limite

**Arquivo:** `app/domain/services/equipment_prompt_context.py` (linhas 151–175)  
**Categoria:** Observabilidade

```python
for _ in range(50):  # safety limit
    size = _estimate_json_size(payload)
    if size <= budget:
        return payload
    # ... remove itens ...
# ← Se sair do loop sem caber no budget, passa silenciosamente para Fase 2
```

Sem log quando o safety limit é atingido, dificultando debug em cenários com payloads muito grandes.

---

### L-08: Scripts usam `sys.path` hacking para importações

**Arquivos:** `app/scripts/debug_parse.py`, `app/scripts/generate_mock_pdf.py`, `app/scripts/generate_sample_pdf.py`  
**Categoria:** Manutenibilidade

```python
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
```

**Correção recomendada:** Usar `python -m app.scripts.debug_parse` (que já funciona) e remover o hack de `sys.path`, ou configurar como entry points do `pyproject.toml`.

---

## Resumo por Categoria

| Categoria | Crítico | Médio | Baixo | Total |
|-----------|---------|-------|-------|-------|
| Performance | 1 | 4 | 1 | 6 |
| Segurança | 2 | 1 | 0 | 3 |
| Lógica / Consistência | 2 | 3 | 2 | 7 |
| Memory Leak | 1 | 0 | 0 | 1 |
| Concorrência | 0 (incl. C-03) | 0 | 1 | 1 |
| Design / Manutenibilidade | 0 | 4 | 4 | 8 |
| **Total** | **6** | **12** | **8** | **26** |

---

## Pontos Positivos

1. **Arquitetura hexagonal bem implementada** — domain ports isolados, adapters concretos, DI via FastAPI Depends
2. **Validação de input/output robusta** — pipeline IV-01…IV-09 e OV-01…OV-14 com fallback determinístico
3. **Budget guard** — proteção proativa contra gastos LLM descontrolados
4. **Circuit breaker** no OpenRouterClient (design correto, mas state se perde — ver M-08)
5. **Logging estruturado** com loguru em todos os módulos
6. **Tratamento gracioso de degradação** — ABNT retriever retorna `None` se indisponível
7. **Contrato de equipamento bem documentado** — `equipment_llm_contract.md` com regras claras
8. **Deduplicação de jobs** via `input_hasher` com SHA-256 determinístico
