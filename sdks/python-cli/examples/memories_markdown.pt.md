# Exportar memórias e conhecimento do Omi para Markdown (Obsidian / Notion / Segundo Cérebro)

Use esta receita para exportar e sincronizar fatos, aprendizados, insights e memórias capturados pelo seu dispositivo vestível Omi em notas Markdown estruturadas. As notas resultantes apresentam frontmatter YAML limpo, agrupamentos por categoria com emoji, tags do Obsidian (`#work`, `#skills`, etc.), datas de criação e indicadores de visibilidade privada, otimizadas para **Obsidian**, **Notion**, **Logseq** ou grafos de conhecimento pessoais.

---

## Pré-requisitos

Garanta que o CLI `omi` esteja instalado e autenticado:

```sh
pip install omi-cli
omi auth login
```

Verifique se você consegue listar suas memórias:

```sh
omi memory list
```

---

## Início rápido

### 1. Exportação direta por pipeline (stdout)

Gere Markdown diretamente do fluxo de saída do CLI (usando `--limit 200` para capturar até o limite máximo de uma página):

```sh
omi --json memory list --limit 200 | python memories_to_markdown.py -
```

### 2. Exportar para uma nota dedicada do cofre

Exporte memórias recentes para uma única nota Markdown estruturada (ex.: para um cofre Obsidian ou importação no Notion):

```sh
omi --json memory list --limit 200 | python memories_to_markdown.py - --output ~/vault/Memories.md
```

> **Nota sobre paginação:** `omi memory list` usa `--limit 25` por padrão e aceita até `--limit 200`. Para cofres com mais de 200 memórias, pagine com lotes de `--offset` (ex.: `--limit 200 --offset 200`) e canalize ou combine as saídas.

### 3. Filtrar por categoria (apenas trabalho e aprendizados)

Exporte apenas categorias específicas de memórias usando o filtro do lado do servidor do CLI:

```sh
omi --json memory list --limit 200 --categories work,learnings | python memories_to_markdown.py - --output ~/vault/WorkMemories.md
```

*(Nota: o script também oferece uma flag `--category` do lado do cliente para filtrar arquivos JSON pré-exportados, ex.: `python memories_to_markdown.py memories.json --category work,learnings`)*

### 4. Agrupar por categoria em notas separadas

Divida as memórias em notas separadas por categoria em uma pasta designada:

```sh
python memories_to_markdown.py memories.json --output-dir ./vault/memories/ --group-by category
```

Isso cria arquivos como `work_memories.md`, `skills_memories.md`, `learnings_memories.md`, etc.

### 5. Agrupar por data em notas diárias

Divida as memórias em registros diários:

```sh
python memories_to_markdown.py memories.json --output-dir ./vault/daily/ --group-by date
```

---

## Opções do CLI

| Opção | Flag | Descrição | Padrão |
| :--- | :--- | :--- | :--- |
| `input` | Posição 1 | Caminho do arquivo JSON, ou `-` para stdin | *(Obrigatório)* |
| `--output` | `-o` | Caminho do arquivo de saída (grava todos os itens neste arquivo) | `stdout` |
| `--output-dir` | `-d` | Diretório de saída para gravar arquivos Markdown separados | `None` |
| `--category` | `-c` | Filtrar por categoria (separadas por vírgula: ex. `work,skills`) | `None` (todas) |
| `--visibility` | `--visibility` | Filtrar itens: `all`, `public` ou `private` | `all` |
| `--group-by` | `-g` | Estratégia de agrupamento: `category`, `date` ou `none` | `category` |
| `--title` | `-t` | Título de cabeçalho personalizado para a nota | `"Omi Memories & Knowledge Base"` |

---

## Estrutura de saída

### Exemplo de nota exportada (`Memories.md`)

```markdown
---
type: omi-memories
total: 4
categories_count: 3
categories:
  - learnings
  - skills
  - work
exported_at: "2026-09-18T09:30:00+00:00"
tags:
  - omi
  - memories
  - second-brain
  - knowledge-base
---

# Omi Memories & Knowledge Base

> **Summary:** 4 memories across 3 categories. Exported from Omi CLI.

## 💼 Work

- Prefers asynchronous communication for architecture proposals and pull request reviews.
  *(📁 `work` · #management #workflow · 🔒 `private` · 📅 2026-09-15 · `#mem_8192a`)
- Leading the TypeScript SDK integration and CLI tooling initiative for Q4.
  *(📁 `work` · #typescript #devtools · 📅 2026-09-16 · `#mem_8192b`)

## 🎯 Skills

- Proficient in Python standard library tool design, FastAPI backend development, and KiCad S-expression parsers.
  *(📁 `skills` · #python #kicad #fastapi · 📅 2026-09-17 · `#mem_8192c`)

## 🧠 Learnings

- KiCad library table parsers require escaping double quotes in nicknames to avoid S-expression syntax errors.
  *(📁 `learnings` · #electronics #eda · 📅 2026-09-18 · `#mem_8192d`)
```

---

## Fluxos de integração

### Sincronização do grafo de conhecimento do cofre Obsidian

Adicione este one-liner à inicialização diária do seu shell ou script de automação para sincronizar suas memórias mais recentes do Omi diretamente no seu segundo cérebro Obsidian:

```sh
omi --json memory list --limit 200 | python memories_to_markdown.py - --output ~/Documents/Obsidian/Vault/OmiMemories.md
```

O Obsidian indexará automaticamente as categorias, tags do frontmatter e metadados para uso com consultas do **Obsidian Dataview**:

```dataview
TABLE file.mtime AS "Updated"
FROM #memories
WHERE contains(categories, "work")
```

### Importação para banco de dados do Notion

1. Exporte suas memórias:
   ```sh
   omi --json memory list --limit 200 | python memories_to_markdown.py - --output omi_memories.md
   ```
2. No Notion, abra qualquer página do workspace, clique em **Import** na barra lateral, selecione **Markdown & CSV** e escolha `omi_memories.md`. O Notion analisará cabeçalhos, tags e blocos de categoria em seções interativas de banco de dados.

---

## Princípios de design

- **Zero dependências de terceiros:** Implementado usando apenas módulos da biblioteca padrão do Python (`json`, `argparse`, `pathlib`, `re`, `datetime`, `sys`).
- **Seguro e resiliente:** Lida automaticamente com UTF-8 com BOM (Byte Order Mark) emitido pelo Windows PowerShell ou shells de comando.
- **Proteção contra travessia:** Sanitiza todos os nomes de arquivo e caminhos de diretório contra ataques de travessia usando regex estrita e verificações de resolução.
- **Pronto para o segundo cérebro:** Gera frontmatter YAML compatível suportado pelo Obsidian, Logseq e Notion.
