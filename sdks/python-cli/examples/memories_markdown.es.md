# Exportar recuerdos y conocimientos de Omi a Markdown (Obsidian / Notion / Segundo Cerebro)

Utiliza esta receta para exportar y sincronizar hechos, aprendizajes, ideas y recuerdos capturados por tu dispositivo portátil Omi en notas Markdown estructuradas. Las notas resultantes cuentan con encabezados YAML limpios (frontmatter), agrupaciones de emojis específicas por categoría, etiquetas de Obsidian (`#work`, `#skills`, etc.), fechas de creación e indicadores de visibilidad privada, optimizados para **Obsidian**, **Notion**, **Logseq** o grafos de conocimiento personal.

---

## Requisitos previos

Asegúrate de tener instalada y autenticada la CLI de `omi`:

```sh
pip install omi-cli
omi auth login
```

Verifica que puedes listar tus recuerdos:

```sh
omi memory list
```

---

## Inicio rápido

### 1. Exportación directa por canalización (Stdout)

Genera Markdown directamente desde el flujo de salida de la CLI (usando `--limit 200` para capturar hasta el límite máximo de una sola página):

```sh
omi --json memory list --limit 200 | python memories_to_markdown.py -
```

### 2. Exportar a una nota dedicada de la bóveda

Exporta recuerdos recientes en una sola nota Markdown estructurada (por ejemplo, para una bóveda de Obsidian o importación en Notion):

```sh
omi --json memory list --limit 200 | python memories_to_markdown.py - --output ~/vault/Memories.md
```

> **Nota sobre paginación:** `omi memory list` tiene un valor predeterminado de `--limit 25` y acepta hasta `--limit 200`. Para bóvedas con más de 200 recuerdos, pagina con lotes de `--offset` (por ejemplo, `--limit 200 --offset 200`) y canaliza o combina las salidas.

### 3. Filtrar por categoría (Solo trabajo y aprendizajes)

Exporta únicamente categorías específicas de recuerdos utilizando el filtro del lado del servidor de la CLI:

```sh
omi --json memory list --limit 200 --categories work,learnings | python memories_to_markdown.py - --output ~/vault/WorkMemories.md
```

*(Nota: El script también proporciona un indicador `--category` del lado del cliente para filtrar archivos JSON exportados previamente, por ejemplo, `python memories_to_markdown.py memories.json --category work,learnings`)*

### 4. Agrupar por categoría en notas separadas

Divide los recuerdos en notas de categorías separadas en una carpeta designada:

```sh
python memories_to_markdown.py memories.json --output-dir ./vault/memories/ --group-by category
```

Esto crea archivos como `work_memories.md`, `skills_memories.md`, `learnings_memories.md`, etc.

### 5. Agrupar por fecha en notas diarias

Divide los recuerdos en registros diarios:

```sh
python memories_to_markdown.py memories.json --output-dir ./vault/daily/ --group-by date
```

---

## Opciones de la CLI

| Opción | Indicador | Descripción | Predeterminado |
| :--- | :--- | :--- | :--- |
| `input` | Posición 1 | Ruta al archivo JSON, o `-` para stdin | *(Requerido)* |
| `--output` | `-o` | Ruta del archivo de salida (escribe todos los elementos aquí) | `stdout` |
| `--output-dir` | `-d` | Directorio de salida para escribir archivos Markdown separados | `None` |
| `--category` | `-c` | Filtrar por categoría (separadas por comas: ej. `work,skills`) | `None` (todas) |
| `--visibility` | `--visibility` | Filtrar elementos: `all`, `public` o `private` | `all` |
| `--group-by` | `-g` | Estrategia de agrupación: `category`, `date` o `none` | `category` |
| `--title` | `-t` | Título de encabezado personalizado para la nota | `"Omi Memories & Knowledge Base"` |

---

## Estructura de salida

### Ejemplo de nota exportada (`Memories.md`)

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

## Flujos de trabajo de integración

### Sincronización del grafo de conocimiento en Obsidian

Agrega esta sola línea al inicio de tu shell diario o script de automatización para sincronizar tus últimos recuerdos de Omi directamente en tu segundo cerebro de Obsidian:

```sh
omi --json memory list --limit 200 | python memories_to_markdown.py - --output ~/Documents/Obsidian/Vault/OmiMemories.md
```

Obsidian indexará automáticamente las categorías, etiquetas del frontmatter y metadatos para utilizarlos con consultas de **Obsidian Dataview**:

```dataview
TABLE file.mtime AS "Updated"
FROM #memories
WHERE contains(categories, "work")
```

### Importación en base de datos de Notion

1. Exporta tus recuerdos:
   ```sh
   omi --json memory list --limit 200 | python memories_to_markdown.py - --output omi_memories.md
   ```
2. En Notion, abre cualquier página de tu espacio de trabajo, haz clic en **Importar** en la barra lateral, selecciona **Markdown y CSV** y elige `omi_memories.md`. Notion procesará los encabezados, etiquetas y bloques de categorías en secciones interactivas de la base de datos.

---

## Principios de diseño

- **Cero dependencias de terceros:** Implementado utilizando exclusivamente módulos de la biblioteca estándar de Python (`json`, `argparse`, `pathlib`, `re`, `datetime`, `sys`).
- **Seguro y resiliente:** Gestiona automáticamente UTF-8 con BOM (Byte Order Mark) emitido por Windows PowerShell o consolas de comandos.
- **Protección contra salto de directorios:** Desinfecta todos los nombres de archivo y rutas de directorio contra ataques de salto de directorio (traversal attacks) mediante expresiones regulares y comprobaciones estrictas de resolución.
- **Listo para Segundo Cerebro:** Genera encabezados YAML compatibles con Obsidian, Logseq y Notion.
