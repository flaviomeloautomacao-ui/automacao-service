# Perfis de Análise & Edição Visual do PDF

> Guia para gerenciar perfis de análise de risco e personalizar a aparência do relatório PDF gerado.

---

## 1. Visão Geral dos Perfis

O sistema suporta **3 perfis de análise** que determinam:

| ID | Nome | Foco |
|---|---|---|
| `dust` | DHA — Dust Hazard Analysis | Poeiras combustíveis, explosões, NFPA 652/654/68/69 |
| `gas` | Análise de Riscos — Gases Inflamáveis | Gases inflamáveis, classificação de zonas, IEC 60079-10-1 |
| `vapors` | Análise de Riscos — Vapores Inflamáveis | Vapores de líquidos inflamáveis, ponto de fulgor |

Cada perfil controla:
- **Título e subtítulo** da capa do relatório
- **Normas referenciadas** na seção de referências normativas
- **Seção de materiais**: se o relatório inclui "Caracterização de Materiais Combustíveis/Inflamáveis"
- **Instrução ao LLM**: tom e foco técnico do texto gerado pela IA
- **Numeração de seções**: ajustada automaticamente conforme presença da seção de materiais

---

## 2. Como Adicionar ou Editar um Perfil

### 2.1 Backend: `app/adapters/llm/prompts.py`

Localize o dict `PROFILE_CONFIG` (logo no início do arquivo). Cada chave é um ID de perfil.

```python
PROFILE_CONFIG: dict[str, dict[str, Any]] = {
    "dust": {
        "label": "DHA — Dust Hazard Analysis",
        "titulo_relatorio": "RELATÓRIO TÉCNICO\nDHA (Dust Hazard Analysis)",
        "subtitulo": "Análise de Perigos por Poeira Combustível",
        "normas_principais": [
            "NFPA 652:2022 — Standard on the Fundamentals of Combustible Dust",
            # ... mais normas
        ],
        "materiais_section": True,   # True → inclui seção de materiais
        "foco": "análise de perigos por poeira combustível (DHA)...",
        "tipo_atmosfera": "atmosferas explosivas por poeira combustível",
    },
    # ... outros perfis
}
```

**Para adicionar um novo perfil:**

1. Copie um bloco existente
2. Altere a chave (ex.: `"nr12"`)
3. Preencha todos os campos
4. Adicione o mesmo ID no frontend (passo 2.2)

**Campos do perfil:**

| Campo | Tipo | Descrição |
|---|---|---|
| `label` | `str` | Nome legível exibido em logs e no contexto LLM |
| `titulo_relatorio` | `str` | Título na capa do PDF (use `\n` para quebra de linha) |
| `subtitulo` | `str` | Subtítulo na capa |
| `normas_principais` | `list[str]` | Normas listadas na seção de referências |
| `materiais_section` | `bool` | Se `True`, adiciona seção "Caracterização de Materiais" |
| `foco` | `str` | Descrição do foco técnico (instrui o LLM) |
| `tipo_atmosfera` | `str` | Descrição da atmosfera perigosa (usada no texto fallback) |

### 2.2 Frontend: `components/upload/ProfileSelect.tsx`

Localize o array `PROFILES` e adicione uma entrada correspondente:

```tsx
const PROFILES = [
  { value: "dust",   label: "DHA – Poeiras Combustíveis" },
  { value: "gas",    label: "Gases Inflamáveis" },
  { value: "vapors", label: "Vapores Inflamáveis" },
  // Adicionar novo perfil aqui:
  { value: "nr12",   label: "NR-12 — Segurança de Máquinas" },
];
```

> **Importante:** O `value` no frontend DEVE coincidir exatamente com a chave em `PROFILE_CONFIG` no backend.

---

## 3. Como Editar o Visual do PDF

O relatório PDF é gerado a partir de 3 arquivos na pasta `app/adapters/pdf/templates/`:

| Arquivo | Controla |
|---|---|
| `report.html` | Estrutura e conteúdo do relatório (Jinja2) |
| `styles.css` | Aparência visual (cores, fontes, margens, espaçamentos) |
| Logo | Coloque `logo.png` na pasta `templates/` e referencie no HTML |

### 3.1 Alterações Rápidas via `styles.css`

O arquivo está organizado em seções comentadas. Busque pelos comentários para encontrar o que deseja alterar:

| O que alterar | Onde buscar no CSS |
|---|---|
| Margens da página | `@page { margin: ... }` |
| Tamanho do papel | `@page { size: A4 }` (ou `Letter`, `Legal`) |
| Rodapé (texto) | `@bottom-center { content: ... }` |
| Cores principais | `.cover-title`, `.section-number` — busque `#0f3460` |
| Cor de destaque | `.cover-divider` — busque `#e94560` |
| Fonte do corpo | `body { font-family: ... }` |
| Tamanho da fonte | `body { font-size: 10pt }` |
| Cabeçalho de tabela | `.inventory-table thead { background-color: ... }` |
| Estilo dos equipamentos | `.equipment-block`, `.equipment-title` |
| Assinatura | `.signature-block`, `.signature-line` |

**Exemplo — trocar a cor primária de azul para verde:**
```css
/* Antes */
.cover-title { color: #0f3460; }
.section-number { color: #0f3460; }

/* Depois */
.cover-title { color: #1a7a3c; }
.section-number { color: #1a7a3c; }
```

### 3.2 Alterações Estruturais via `report.html`

O template Jinja2 é dividido em blocos bem comentados:

```
CAPA                    → div.cover
SUMÁRIO                 → div.toc
INTRODUÇÃO              → seção 1
MATERIAIS               → seção 2 (condicional)
METODOLOGIA             → seção 3
EQUIPAMENTOS            → seção 4 (loop por equipamento)
  ├── Descrição         → 4.x.1
  ├── Perigos           → 4.x.2
  ├── Causas            → 4.x.3
  ├── Consequências     → 4.x.4
  ├── Classificação     → 4.x.5
  ├── Medidas existentes→ 4.x.6
  ├── Recomendações     → 4.x.7
  └── Justificativas    → 4.x.8
CONCLUSÃO               → seção 5
REFERÊNCIAS             → seção 6
ENCERRAMENTO            → seção 7
ANEXO — INVENTÁRIO      → tabela final
```

**Variáveis disponíveis no template:**

| Variável | Tipo | Descrição |
|---|---|---|
| `metadata` | `dict` | Dados da empresa (razao_social, cnpj, site, etc.) |
| `rows` | `list[dict]` | Todas as linhas de risco da planilha |
| `llm_sections` | `dict` | Seções geradas pelo LLM (introducao, materiais, metodologia, conclusao) |
| `equipments` | `list[dict]` | Equipamentos agrupados para análise individual |
| `profile_config` | `dict` | Configuração do perfil ativo (normas, títulos, etc.) |

**Campos de cada equipamento (`equipments[i]`):**

| Campo | Tipo | Origem |
|---|---|---|
| `index` | `int` | Número sequencial (1, 2, 3...) |
| `nome` | `str` | Nome do equipamento |
| `descricao` | `str` | Descrição (mais longa encontrada) |
| `perigos` | `list[str]` | Lista de perigos identificados |
| `causas` | `list[str]` | Lista de causas possíveis |
| `consequencias` | `list[str]` | Lista de consequências potenciais |
| `severidade` | `str` | Categoria de severidade |
| `risco` | `str` | Categoria de risco |
| `medidas_existentes` | `list[str]` | Medidas preventivas existentes |
| `medidas_implementar` | `list[str]` | Recomendações técnicas |
| `observacoes` | `list[str]` | Observações / justificativas |
| `riscos_desc` | `list[str]` | Descrição dos riscos |

### 3.3 Macros Jinja2 Disponíveis

| Macro | Uso |
|---|---|
| `render_text(text)` | Converte texto plano (com `\n\n` e bullets) em HTML formatado |
| `render_bullet_list(items)` | Renderiza uma lista Python como `<ul><li>` |

### 3.4 Adicionar Logo

1. Coloque `logo.png` em `app/adapters/pdf/templates/`
2. No `report.html`, adicione na seção `.cover-content`:
   ```html
   <img src="logo.png" style="width: 200px; margin-bottom: 1em;" alt="Logo" />
   ```

---

## 4. Fluxo Completo: Upload → PDF

```
Upload (Frontend)
  │
  ├── file (XLSX/CSV)
  ├── profile ("dust" / "gas" / "vapors")
  │
  ▼
ProcessUploadUseCase.execute()
  │
  ├── 1. Persiste upload no storage
  ├── 2. Parse da planilha → MachineRiskRow[]
  ├── 3. Validação determinística
  ├── 4. Cria draft no banco
  ├── 4.5. Agrupa por equipamento → group_rows_by_equipment()
  ├── 5. Gera seções via LLM (usando prompts do perfil)
  ├── 5.5. Normaliza seções LLM
  ├── 6-7. Renderiza HTML (report.html + styles.css) → PDF
  └── 8-9. Armazena PDF e persiste relatório
```

---

## 5. Testando Alterações

Para gerar um PDF de teste **sem LLM**, use o script de exemplo:

```bash
python -m app.scripts.generate_sample_pdf
```

O PDF é salvo em `output/sample_report.pdf`. Para trocar o perfil de teste, edite a constante `_SAMPLE_PROFILE` no script.

---

## 6. Dados da Empresa (CompanyMetadata)

Os seguintes campos podem ser preenchidos para a capa e contexto:

| Campo | Capa | Contexto LLM | Exemplo |
|---|---|---|---|
| `razao_social` | ✅ | ✅ | "Bunge Alimentos S.A." |
| `cnpj` | ✅ | ✅ | "84.046.101/0035-93" |
| `site` | ✅ | ✅ | "São Francisco do Sul — SC" |
| `endereco` | ✅ | ✅ | "Rua XV de Novembro, 815" |
| `responsavel` | ✅ | ✅ | "Eng. João Silva" |
| `registro_profissional` | ✅ | ✅ | "CREA-SC 098765" |
| `elaboracao` | ✅ | ✅ | "Konis Ex Engenharia" |
| `local_vistoriado` | ✅ | ✅ | "Terminal Portuário — Granéis" |
| `contrato` | ✅ | ✅ | "CT-2025/042" |
| `data_avaliacao` | ✅ | ✅ | "10/03/2025" |
