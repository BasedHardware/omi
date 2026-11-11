# Export Omi Memories and Knowledge to Markdown (Obsidian / Notion / Second Brain)

Use this recipe to export and synchronize facts, learnings, insights, and memories captured by your Omi wearable device into structured Markdown notes. The resulting notes feature clean YAML frontmatter, category-specific emoji groupings, Obsidian tags (`#work`, `#skills`, etc.), creation dates, and private visibility indicators, optimized for **Obsidian**, **Notion**, **Logseq**, or personal knowledge graphs.

---

## Prerequisites

Ensure you have the `omi` CLI installed and authenticated:

```sh
pip install omi-cli
omi auth login
```

Verify you can list your memories:

```sh
omi memory list
```

---

## Quickstart

### 1. Direct Pipeline Export (Stdout)

Generate Markdown directly from the CLI output stream (using `--limit 200` to capture up to the max single-page limit):

```sh
omi --json memory list --limit 200 | python memories_to_markdown.py -
```

### 2. Export to a Dedicated Vault Note

Export recent memories into a single structured Markdown note (e.g., for an Obsidian vault or Notion import):

```sh
omi --json memory list --limit 200 | python memories_to_markdown.py - --output ~/vault/Memories.md
```

> **Note on Pagination:** `omi memory list` defaults to `--limit 25` and accepts up to `--limit 200`. For vaults with more than 200 memories, paginate with `--offset` batches (e.g., `--limit 200 --offset 200`) and pipe or combine the outputs.

### 3. Filter by Category (Work & Learnings Only)

Export only specific categories of memories using the CLI's server-side filter:

```sh
omi --json memory list --limit 200 --categories work,learnings | python memories_to_markdown.py - --output ~/vault/WorkMemories.md
```

*(Note: The script also provides a client-side `--category` flag for filtering pre-exported JSON files, e.g. `python memories_to_markdown.py memories.json --category work,learnings`)*

### 4. Group by Category into Separate Notes

Split memories into separate category notes in a designated folder:

```sh
python memories_to_markdown.py memories.json --output-dir ./vault/memories/ --group-by category
```

This creates files like `work_memories.md`, `skills_memories.md`, `learnings_memories.md`, etc.

### 5. Group by Date into Daily Notes

Split memories into daily logs:

```sh
python memories_to_markdown.py memories.json --output-dir ./vault/daily/ --group-by date
```

---

## CLI Options

| Option | Flag | Description | Default |
| :--- | :--- | :--- | :--- |
| `input` | Position 1 | Path to JSON file, or `-` for stdin | *(Required)* |
| `--output` | `-o` | Output file path (writes all items to this file) | `stdout` |
| `--output-dir` | `-d` | Output directory to write separated Markdown files | `None` |
| `--category` | `-c` | Filter by category (comma-separated: e.g. `work,skills`) | `None` (all) |
| `--visibility` | `--visibility` | Filter items: `all`, `public`, or `private` | `all` |
| `--group-by` | `-g` | Grouping strategy: `category`, `date`, or `none` | `category` |
| `--title` | `-t` | Custom header title for the note | `"Omi Memories & Knowledge Base"` |

---

## Output Structure

### Sample Exported Note (`Memories.md`)

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

## Integration Workflows

### Obsidian Vault Knowledge Graph Sync

Add this one-liner to your daily shell startup or automation script to sync your latest Omi memories directly into your Obsidian second brain:

```sh
omi --json memory list --limit 200 | python memories_to_markdown.py - --output ~/Documents/Obsidian/Vault/OmiMemories.md
```

Obsidian will automatically index the categories, frontmatter tags, and metadata for use with **Obsidian Dataview** queries:

```dataview
TABLE file.mtime AS "Updated"
FROM #memories
WHERE contains(categories, "work")
```

### Notion Database Import

1. Export your memories:
   ```sh
   omi --json memory list --limit 200 | python memories_to_markdown.py - --output omi_memories.md
   ```
2. In Notion, open any workspace page, click **Import** in the sidebar, select **Markdown & CSV**, and choose `omi_memories.md`. Notion will parse headers, tags, and category blocks into interactive database sections.

---

## Design Principles

- **Zero Third-Party Dependencies:** Implemented using pure Python standard library modules (`json`, `argparse`, `pathlib`, `re`, `datetime`, `sys`).
- **Safe & Resilient:** Automatically handles UTF-8 with BOM (Byte Order Mark) emitted by Windows PowerShell or command shells.
- **Traversal Protection:** Sanitizes all filenames and directory paths against traversal attacks using strict regex and resolution checks.
- **Second Brain Ready:** Generates compliant YAML frontmatter supported by Obsidian, Logseq, and Notion.
