# Export Omi Goals to Markdown Checklist Trees (Obsidian / Notion / Second Brain)

Use this recipe to export and synchronize long-term goals, active milestones, and success criteria captured by your Omi wearable device into structured, interactive Markdown checklists.

The generated Markdown notes feature CommonMark task checklists (`- [ ]` / `- [x]`), inline ASCII progress bars, hierarchical subtasks, success criteria trees, and metadata frontmatter, ready for **Obsidian**, **Notion**, **Logseq**, or personal task vaults.

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

### 1. Direct Pipeline Stream (Stdout)

Stream goals directly from the CLI output pipeline into formatted CommonMark:

```sh
omi --json goal list --include-inactive --limit 100 | python goals_to_markdown.py -
```

### 2. Export to a Dedicated Vault Note

Export your goals into a single Markdown note with atomic file replacement:

```sh
omi --json goal list --include-inactive --limit 100 | python goals_to_markdown.py - -o ~/vault/Goals.md --force
```


### 3. Multi-File Ingestion & Deduplication

Merge multiple export snapshots (or paginated JSON dumps). Duplicate goals sharing the same ID are deduplicated automatically, with the newest `updated_at` (or `created_at`) timestamp winning:

```sh
python goals_to_markdown.py backup_page1.json backup_page2.json -o ~/vault/MasterGoals.md --force
```

### 4. Filter by Status Category

Export only active or accomplished goals:

```sh
# Only active goals
python goals_to_markdown.py goals.json --status active -o ~/vault/ActiveGoals.md

# Only achieved goals
python goals_to_markdown.py goals.json --status achieved -o ~/vault/AchievedGoals.md
```

### 5. Group by Goal Type

Group your goals into numeric, scale, and boolean sections:

```sh
python goals_to_markdown.py goals.json --group-by type -o ~/vault/GroupedGoals.md
```

### 6. Split into Vault Directory Notes

Split goals by category or type into separate individual Markdown files inside a destination folder:

```sh
python goals_to_markdown.py goals.json -d ~/vault/Goals/ --group-by type --force
```

---

## CLI Options

| Option | Flag | Description | Default |
| :--- | :--- | :--- | :--- |
| `sources` | `Positional` | One or more JSON files, or `-` for stdin | *(Required)* |
| `--output` | `-o` | Output file path (writes all items to this file) | `stdout` |
| `--output-dir` | `-d` | Output directory to write individual or grouped files | `None` |
| `--status` | `--status` | Filter by status: `all`, `active`, `achieved`, `inactive` | `all` |
| `--type` | `--type` | Filter by goal type: `all`, `numeric`, `scale`, `boolean` | `all` |
| `--group-by` | `--group-by` | Section grouping strategy: `status`, `type`, `none` | `status` |
| `--title` | `--title` | Document header title | `"Omi Goals Checklist"` |
| `--force` | `-f` | Overwrite destination file(s) if they already exist | `False` |

---

## Output Structure

### Sample Exported Note (`Goals.md`)

> **Note on Omi API Schema:** The converter seamlessly renders both official Omi API `success_criteria` arrays (present on `GoalResponse` models) and custom user `subtasks` / `tasks` lists into nested task checkboxes:

```markdown
---
type: goals
total: 3
active: 2
achieved: 1
inactive: 0
overall_progress: 73.3%
exported_at: "2026-10-03T12:00:00+00:00"
tags:
  - omi
  - goals
  - obsidian
  - checklist
---

# Omi Goals Checklist

> **Summary:** 2 active, 1 achieved, 0 inactive (3 total). Overall Progress: 73.3%. Exported from Omi CLI.

## 🟢 Active Goals

- [ ] **Run 100 Kilometers this Month** `[======....] 60.0%` *(60 / 100 km · `#goal_run_100k`)*
  > **Outcome:** Improve marathon cardiovascular endurance.
  > **Why:** Build stamina for the upcoming spring half-marathon.
  - [x] Run 25 km in week 1
  - [x] Run 25 km in week 2
  - [ ] Complete 30 km long run
  - [ ] Complete final 20 km taper run
- [ ] **Launch Developer Portfolio** `[====......] 40.0%` *(Scale · `#goal_portfolio`)*
  > **Outcome:** Establish public open source portfolio and engineering presence.
  - [x] Build automated CI/CD pipeline and integration tests
  - [ ] Publish 3 architecture walkthroughs
  - [ ] Deploy custom analytics dashboard

## ✅ Achieved Goals

- [x] **Complete Morning Meditation Routine** `[==========] 100.0%` *(Boolean · `#goal_meditation`)*
  > **Outcome:** Establish daily mindfulness practice.
  - [x] Meditate for 15 minutes before breakfast
  - [x] Log streak in Omi daily review

## ⚪ Inactive Goals

_No inactive goals._
```

---

## Integration Workflows

### Obsidian Vault Inbox Sync

Add a scheduled task or startup hook to keep your Obsidian goal checklist continuously in sync:

```sh
omi --json goal list --include-inactive --limit 100 | python goals_to_markdown.py - -o ~/Documents/Obsidian/Vault/OmiGoals.md --force
```

- **Interactive Checkboxes**: Checking or unchecking boxes in Obsidian works immediately as standard Markdown tasks.
- **Backlinks & Tags**: Goal IDs are tagged with `#goal_<id>`, allowing you to link project notes directly to your goal ID.
- **YAML Frontmatter**: Dataview and Obsidian properties automatically parse `overall_progress`, `active`, and `achieved` counters.

### Notion Import

1. Run the command to generate `goals.md`:
   ```sh
   omi --json goal list --include-inactive --limit 100 | python goals_to_markdown.py - -o goals.md
   ```

2. In Notion, open your target page or dashboard.
3. Click **Settings & members** &rarr; **Import** (or use `/import` inline) and select **Markdown & CSV**.
4. Select `goals.md`. Notion will automatically transform the document into native interactive To-do blocks, callouts, and hierarchical subtasks.
