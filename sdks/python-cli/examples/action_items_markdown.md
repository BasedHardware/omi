# Export Omi Action Items to Markdown (Obsidian / Notion / Second Brain)

Use this recipe to export and synchronize action items captured by your Omi wearable device into clean, interactive Markdown checklists. The resulting files include YAML frontmatter, standard GFM task checkboxes (`- [ ]` / `- [x]`), due dates, and links back to originating conversations, ready for **Obsidian**, **Notion**, **Logseq**, or personal task vaults.

---

## Prerequisites

Ensure you have the `omi` CLI installed and authenticated:

```sh
pip install omi-cli
omi auth login
```

Verify you can list your action items:

```sh
omi action-item list
```

---

## Quickstart

### 1. Direct Pipeline Export (Stdout)

Generate Markdown directly from the CLI output stream:

```sh
omi --json action-item list | python action_items_to_markdown.py -
```

### 2. Export to a Dedicated Tasks File

Export your tasks into a single Markdown note (e.g. for an Obsidian vault or Notion import):

```sh
omi --json action-item list | python action_items_to_markdown.py - --output ~/vault/Tasks.md
```

### 3. Filter by Status (Pending Tasks Only)

Export only open, pending action items:

```sh
omi --json action-item list --open | python action_items_to_markdown.py - --status open --output ~/vault/PendingTasks.md
```

### 4. Group by Due Date into Daily Notes

Split action items into separate daily/dated notes in a folder:

```sh
python action_items_to_markdown.py action_items.json --output-dir ./vault/daily-tasks/ --group-by date
```

---

## CLI Options

| Option | Flag | Description | Default |
| :--- | :--- | :--- | :--- |
| `input` | Position 1 | Path to JSON file, or `-` for stdin | *(Required)* |
| `--output` | `-o` | Output file path (writes all items to this file) | `stdout` |
| `--output-dir` | `-d` | Output directory to write Markdown file(s) | `None` |
| `--status` | `--status` | Filter items: `all`, `open`, or `completed` | `all` |
| `--group-by` | `--group-by` | Grouping strategy: `status`, `date`, or `none` | `status` |
| `--title` | `--title` | Custom header title for the note | `"Omi Action Items"` |

---

## Output Structure

### Sample Exported Note (`Tasks.md`)

```markdown
---
type: action-items
total: 3
open: 2
completed: 1
exported_at: "2026-09-14T15:00:00+00:00"
tags:
  - omi
  - action-items
  - tasks
---

# Omi Action Items

> **Summary:** 2 open, 1 completed (3 total). Exported from Omi CLI.

## 📌 Pending Tasks

- [ ] Email quarterly financial update to investment team
  *(📅 Due: 2026-09-15 18:00 UTC · 🔗 [[conversation_a1b2c3d4]] · `#act_99182`)*
- [ ] Review pull request for memory sync latency optimization
  *(🔗 [[conversation_e5f6g7h8]] · `#act_99183`)*

## ✅ Completed Tasks

- [x] Configure Luno exchange sell limit order for portfolio rebalancing
  *(📅 Due: 2026-09-14 05:30 UTC · `#act_99180`)*
```

---

## Integration Workflows

### Obsidian Vault Inbox Sync

Add this one-liner to your daily startup script or cron job to automatically append fresh action items to your Obsidian inbox:

```sh
omi --json action-item list --open | python action_items_to_markdown.py - --status open --output ~/Documents/Obsidian/Inbox/OmiTasks.md
```

### Notion Import

1. Run:
   ```sh
   omi --json action-item list | python action_items_to_markdown.py - --output omi_tasks.md
   ```
2. In Notion, open any page, click **Import** in the sidebar or menu, select **Markdown & CSV**, and choose `omi_tasks.md`. Notion will automatically turn checkboxes into interactive To-Do items.

---

## Design Principles

- **Zero Third-Party Dependencies:** Uses only standard library modules (`json`, `argparse`, `pathlib`, `re`, `datetime`, `sys`).
- **Safe & Resilient:** Automatically handles UTF-8 with BOM (Byte Order Mark) commonly emitted on Windows PowerShell.
- **Traversal Protection:** Sanitizes all date and title components against path traversal attacks.
- **Second Brain Ready:** Uses standard YAML frontmatter supported by Obsidian Dataview, Logseq, and Notion.
