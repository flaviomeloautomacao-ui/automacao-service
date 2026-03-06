# Automação de Laudos Técnicos — Python Service

Serviço backend que recebe planilhas de análise de riscos (XLSX/CSV), valida os dados, enriquece seções narrativas via LLM e gera um laudo técnico em PDF.

---

## 1. Configurar `.env`

Crie um arquivo `.env` na raiz do projeto:

```dotenv
ENV=development
API_PORT=8000

# Banco de dados (Postgres local ou Supabase)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/automacao

# Supabase Storage
SUPABASE_URL=https://SEU-PROJETO.supabase.co
SUPABASE_SERVICE_ROLE_KEY=sua-chave-service-role
SUPABASE_BUCKET=documents

# LLM (OpenRouter)
OPENROUTER_API_KEY=sua-chave-openrouter
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=openai/gpt-4o
```

> Para rodar apenas os testes, as variáveis de Supabase e OpenRouter podem ficar vazias.

---

## 2. Criar virtualenv e instalar dependências

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

---

## 3. Inicializar banco de dados local

Certifique-se de que o PostgreSQL está rodando e que o banco `automacao` existe:

```bash
# Criar banco (via psql)
psql -U postgres -c "CREATE DATABASE automacao;"
```

Depois, rode o script que cria todas as tabelas:

```bash
python -m app.scripts.init_db
```

---

## 4. Rodar o servidor

```bash
uvicorn app.api.main:app --reload --port 8000
```

O servidor estará disponível em `http://localhost:8000`.

- Docs interativa: http://localhost:8000/docs
- Health check: http://localhost:8000/health

---

## 5. Testar endpoint `/uploads`

Envie uma planilha via `curl` ou pela interface Swagger (`/docs`):

```bash
curl -X POST http://localhost:8000/uploads \
  -F "file=@planilha_riscos.xlsx"
```

Resposta esperada (JSON):

```json
{
  "upload_id": "uuid-...",
  "draft_id": "uuid-...",
  "report_id": "uuid-...",
  "pdf_url": "https://..."
}
```

---

## 6. Rodar testes

```bash
pytest tests/ -v
```

Os testes de parser e validator rodam sem infra externa. O teste do use case (`test_usecase_happy_path.py`) usa mocks para storage, banco e LLM.

---

## Estrutura do projeto

```
app/
  api/           → Rotas FastAPI (thin controllers)
  domain/        → Entidades, portas (interfaces), erros
  application/   → Casos de uso (orquestração)
  adapters/      → Implementações concretas (parser, storage, db, llm, pdf)
  infrastructure/→ Config, logging, DI, conexão DB
  scripts/       → Scripts utilitários (init_db)
tests/           → Testes automatizados
```
