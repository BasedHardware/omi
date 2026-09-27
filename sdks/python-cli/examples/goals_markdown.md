# Export Omi Goals to Markdown (Obsidian / Notion / Second Brain)

Use this recipe to export and synchronize goals and progress metrics tracked by your Omi wearable device into clean, interactive Markdown dashboards and notes. The resulting documents include visual progress indicators, metric tracking, status badges (`🟢 Active` / `⚪ Completed`), and metadata, ready for **Obsidian**, **Notion**, **Logseq**, or personal goal dashboards.

---

## Prerequisites

Ensure you have the `omi` CLI installed and authenticated:

```sh
pip install omi-cli
omi auth login
```

Verify you can list your tracked goals:

```sh
omi goal list
```

> **Note on `--include-inactive`:** By default, `omi goal list` fetches only currently active goals (up to `--limit 100`). To export both active and completed/archived goals, or to generate reports containing completed milestones, always pass `--include-inactive`.

---

## Quickstart

### 1. Direct Pipeline Export (Stdout)

Generate Markdown directly from the CLI output stream including completed/archived goals:

```sh
omi --json goal list --limit 100 --include-inactive | python goals_to_markdown.py -
```

### 2. Export to a Dedicated Goals Vault Note

Export all tracked goals into a single Markdown note (e.g. for an Obsidian vault or Notion import):

```sh
omi --json goal list --limit 100 --include-inactive | python goals_to_markdown.py - --output ~/vault/Goals.md
```

### 3. Filter by Status (Completed or Active Goals)

Export only completed milestones:

```sh
omi --json goal list --limit 100 --include-inactive | python goals_to_markdown.py - --status completed --output ~/vault/Completed_Goals.md
```

Export only open, active goals:

```sh
omi --json goal list --limit 100 | python goals_to_markdown.py - --status active --output ~/vault/Active_Goals.md
```

### 4. Group by Goal Type into Separate Notes

Split goals across dedicated category notes (`Goals_Numeric.md`, `Goals_Scale.md`, `Goals_Boolean.md`):

```sh
omi --json goal list --limit 100 --include-inactive | python goals_to_markdown.py - --output-dir ~/vault/goals/ --group-by type
```

---

## Sample Markdown Output

```markdown
# Omi Tracked Goals

---
**Generated:** `2026-09-27 12:00 UTC`  
**Total Goals:** `2` (`1 active`, `1 completed`)  
---

## Active Goals

### 🎯 Read 12 books in 2026
**Status:** 🟢 Active • **Type:** Numeric Target • **Progress:** 8 / 12 books • `[███████░░░] 67%`

Complete nonfiction tech and engineering reading list.
> *Created: 2026-01-01 | Updated: 2026-09-27 | ID: `goal_001`*

---

## Completed / Inactive Goals

### 📊 Morning Focus Session
**Status:** ⚪ Completed • **Type:** Scale (1-10) • **Progress:** 10 / 10 • `[██████████] 100%`

Daily 30-minute deep work routine.
> *Created: 2026-01-01 | Updated: 2026-09-20 | ID: `goal_002`*
```

---

## Automation (Daily Vault Sync via Cron)

To keep your personal knowledge base continuously synchronized with your Omi goals, configure a cron job on your host machine:

```sh
# Run every night at midnight UTC to refresh goals
0 0 * * * omi --json goal list --limit 100 --include-inactive | python /path/to/goals_to_markdown.py - --output ~/vault/Goals.md
```
