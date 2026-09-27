# Export Omi Goals to Markdown (Obsidian / Notion / PKM)

Use this recipe to export and synchronize goals, tracked habits, and progress metrics captured by your Omi wearable device into clean, interactive Markdown dashboards. The resulting files include YAML frontmatter, visual ASCII progress bars (`[████████░░] 80%`), standard GFM task checkboxes (`- [ ]` / `- [x]`), metric values with units, and metadata tags, ready for **Obsidian**, **Notion**, **Logseq**, or personal PKM vaults.

---

## Prerequisites

Ensure you have the `omi` CLI installed and authenticated:

```sh
pip install omi-cli
omi auth login
```

Verify you can list your goals:

```sh
omi goal list
```

---

## Quickstart

### 1. Direct Pipeline Export (Stdout)

Generate Markdown directly from the CLI output stream:

```sh
omi --json goal list | python goals_to_markdown.py -
```

### 2. Export to a Dedicated Goals Dashboard

Export your goals into a single Markdown note (e.g. for an Obsidian vault or Notion import):

```sh
omi --json goal list | python goals_to_markdown.py - --output ~/vault/Goals.md
```

Or using positional arguments with a saved JSON export:

```sh
python goals_to_markdown.py goals.json ~/vault/Goals.md
```

### 3. Filter by Active Status

Export only active, in-progress goals:

```sh
omi --json goal list | python goals_to_markdown.py - --active-only --output ~/vault/ActiveGoals.md
```

### 4. Group by Type into Separate Notes

Split goals into separate notes by metric type (`numeric`, `boolean`, `scale`) in a directory:

```sh
python goals_to_markdown.py goals.json --output-dir ./vault/goals/ --group-by type
```

Or group by active/completed status:

```sh
python goals_to_markdown.py goals.json --output-dir ./vault/goals/ --group-by status
```

---

## Document Features

### Frontmatter

Every generated note includes YAML frontmatter with metadata summarizing your goals:

```yaml
---
title: "Omi Goals"
type: goals
total: 12
active: 8
completed: 4
tags:
  - omi
  - goals
  - habits
updated_at: "2026-09-27 12:00:00Z"
---
```

### Visual Progress Bars & Task Checkboxes

Goals render as GFM task checkboxes with progress bars and current/target values:

```markdown
- [ ] **Read 50 Pages Daily** — [█████░░░░░] 50% (25/50 pages) <!-- `#numeric` · 🕒 2026-09-27 UTC · 🆔 `goal_01` -->
- [x] **Morning Meditation** — [██████████] 100% (Done) <!-- `#boolean` · 🕒 2026-09-26 UTC · 🆔 `goal_03` -->
```

### Path Traversal & Safe Overwrite Protection

Directory export strips dangerous path traversal sequences (`../`, `:`, etc.) to ensure notes are only written within the intended directory. Files are created safely with overwrite protection unless `--force` / `-f` is explicitly provided.
