# Export Omi Goals to Markdown (Obsidian / Notion / Second Brain)

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

### 3. Filter by Active Status

Export only active, in-progress goals:

```sh
omi --json goal list --include-inactive=false | python goals_to_markdown.py - --active-only --output ~/vault/ActiveGoals.md
```

### 4. Group by Type into Separate Notes

Split goals into separate notes by metric type (`numeric`, `boolean`, `scale`) in a directory:

```sh
python goals_to_markdown.py goals.json --output-dir ./vault/goals/ --group-by type
```

---

## CLI Options

| Flag | Description | Default |
| :--- | :--- | :--- |
| `input` | Path to JSON file, or `-` for stdin | `-` |
| `-o`, `--output` | Destination path for a single `.md` file | `stdout` |
| `--output-dir` | Directory to write grouped Markdown files into | None |
| `--group-by` | Grouping strategy: `type` (numeric/boolean/scale) or `status` (active/completed) | None |
| `--active-only` | Filter out completed or inactive goals | `False` |
| `--title` | Custom document title | `Omi Goals` |

---

## Sample Markdown Output

```markdown
---
title: "Omi Goals"
type: goals
total: 3
active: 2
completed: 1
tags:
  - omi
  - goals
  - habits
updated_at: "2026-09-27T08:38:00Z"
---

# Omi Goals

## 📊 Numeric Goals (2)

- [ ] **Read 20 Pages Daily** — [████████░░] 75% (15/20 pages) <!-- `#numeric` · 🕒 2026-09-27 UTC · 🆔 `goal_01` -->
- [x] **Drink 2 Liters Water** — [██████████] 100% (2/2 liters) <!-- `#numeric` · 🕒 2026-09-27 UTC · 🆔 `goal_02` -->

## 🎯 Daily Habits & Boolean Targets (1)

- [ ] **Morning Meditation** — [░░░░░░░░░░] 0% (In Progress) <!-- `#boolean` · 🕒 2026-09-27 UTC · 🆔 `goal_03` -->
```
