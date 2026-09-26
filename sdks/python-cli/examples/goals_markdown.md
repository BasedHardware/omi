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

---

## Quickstart

### 1. Direct Pipeline Export (Stdout)

Generate Markdown directly from the CLI output stream:

```sh
omi --json goal list | python goals_to_markdown.py -
```

### 2. Export to a Dedicated Goals Vault Note

Export all tracked goals into a single Markdown note (e.g. for an Obsidian vault or Notion import):

```sh
omi --json goal list | python goals_to_markdown.py - --output ~/vault/Goals.md
```

### 3. Filter by Status (Active Goals Only)

Export only open, active goals:

```sh
omi --json goal list | python goals_to_markdown.py - --status active --output ~/vault/Active_Goals.md
```

### 4. Group by Goal Type into Separate Notes

Split goals across dedicated category notes (`Goals_Target.md`, `Goals_Habit.md`, `Goals_Metric.md`):

```sh
omi --json goal list | python goals_to_markdown.py - --output-dir ~/vault/goals/ --group-by type
```

---

## Sample Markdown Output

```markdown
# Omi Tracked Goals

---
**Generated:** `2026-09-26 12:00 UTC`
**Total Goals:** `2` (`2 active`, `0 completed`)
---

## Active Goals

### 🎯 Read 12 books in 2026
**Status:** 🟢 Active • **Type:** Target Milestone • **Progress:** 8 / 12 books • `[███████░░░] 66%`

Tracking nonfiction tech & business reading.
> *Created: 2026-01-01 | Updated: 2026-09-26 | ID: `goal_001`*

### ⚡ Morning 5km Run
**Status:** 🟢 Active • **Type:** Habit / Consistency • **Progress:** 21 / 30 days • `[███████░░░] 70%`

Run daily before 8am.
> *Created: 2026-09-01 | Updated: 2026-09-26 | ID: `goal_002`*
```

---

## Automation (Daily Vault Sync via Cron)

To keep your personal knowledge base continuously synchronized with your Omi goals, configure a cron job on your host machine:

```sh
# Run every night at midnight UTC to refresh goals
0 0 * * * omi --json goal list --limit 50 | python /path/to/goals_to_markdown.py - --output ~/vault/Goals.md
```
