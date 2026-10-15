# Export Omi Goals to a SQLite Database

Convert your Omi goal and milestone JSON exports into a structured, indexed SQLite database (`.sqlite`).
This recipe enables offline SQL queries, progress metrics calculation, habit tracking analytics, and multi-page
export merges with automatic deduplication.

---

## Prerequisites

You need Python 3.10+ and an authenticated `omi-cli` installed:

```sh
pip install omi-cli
omi auth login
```

Export your tracked goals (including completed and inactive milestones):

```sh
omi --json goal list --limit 100 --include-inactive > goals.json
```

Verify that the export file was populated before running the converter. You can combine multiple exports
(such as team goal exports or periodic backups); the converter idempotently upserts records by their unique goal ID.

---

## Quickstart

### 1. Direct Export to a SQLite Database

Load a goal export into a local SQLite database:

```sh
python goals_to_sqlite.py ~/Documents/omi_goals.sqlite goals.json
```

### 2. Multi-Export Merge

Merge multiple snapshots, team exports, or backups into a single unified database. Note that `omi goal list`
caps exports at `--limit 100` and currently provides no pagination offset, so each export covers the newest 100
milestones; ingesting more than 100 goals requires other data sources or separate scoped exports:

```sh
python goals_to_sqlite.py omi_goals.sqlite export_team_a.json export_team_b.json
```

Duplicate goal IDs across files update existing entries rather than creating duplicate rows.

### 3. Pipeline Stream (Stdin)

Stream live CLI output directly into the SQLite database without intermediate files:

```sh
set -o pipefail
omi --json goal list --limit 100 --include-inactive | python goals_to_sqlite.py omi_goals.sqlite -
```

---

## Database Schema

The database creates a single table `goals` with secondary indexes on `is_active`, `is_completed`,
`goal_type`, and `created_at`:

| Column | Type | Index | Description |
| :--- | :--- | :--- | :--- |
| `id` | `TEXT` | `PRIMARY KEY` | Unique goal identifier (e.g. `goal_abc123`) |
| `title` | `TEXT` | | Goal title or milestone summary |
| `goal_type` | `TEXT` | Yes | Type of goal (`numeric`, `boolean`, `scale`) |
| `current_value` | `REAL` | | Current recorded progress value |
| `target_value` | `REAL` | | Target milestone value to achieve |
| `min_value` | `REAL` | | Minimum range value for scale goals |
| `max_value` | `REAL` | | Maximum range value for scale goals |
| `unit` | `TEXT` | | Metric unit label (e.g. `books`, `km`, `hours`) |
| `is_active` | `INTEGER` | Yes | Active status flag (`1` for active, `0` for inactive) |
| `is_completed` | `INTEGER` | Yes | Completed status flag (`1` for completed, `0` for open) |
| `progress_pct` | `REAL` | | Computed completion percentage (e.g. `75.5`) |
| `created_at` | `TEXT` | Yes | Creation timestamp in UTC (`YYYY-MM-DD HH:MM:SS`) |
| `updated_at` | `TEXT` | | Last update timestamp in UTC (`YYYY-MM-DD HH:MM:SS`) |
| `raw_json` | `TEXT` | | Full verbatim source JSON object |

---

## Practical SQL Analytics Queries

Open the database using `sqlite3`:

```sh
sqlite3 omi_goals.sqlite
```

### 1. Active Goals Ranked by Progress

```sql
SELECT
    title,
    current_value,
    target_value,
    unit,
    progress_pct
FROM goals
WHERE is_active = 1
ORDER BY progress_pct DESC;
```

### 2. Goal Type Breakdown and Average Completion

```sql
SELECT
    COALESCE(goal_type, 'unspecified') AS goal_type,
    COUNT(*) AS total_count,
    SUM(is_active) AS active_count,
    SUM(is_completed) AS completed_count,
    ROUND(AVG(progress_pct), 1) AS avg_progress_pct
FROM goals
GROUP BY goal_type;
```

### 3. Completed Milestones

```sql
SELECT
    title,
    target_value,
    unit,
    created_at
FROM goals
WHERE is_completed = 1
ORDER BY created_at DESC;
```
