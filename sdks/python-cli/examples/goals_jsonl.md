# Export Omi Goals to Streaming JSON Lines (JSONL)

Convert your Omi goal and habit progress JSON exports into newline-delimited JSON Lines (`.jsonl` / NDJSON).
This recipe produces a clean, flat record per line suitable for streaming analytics, `jq` processing, vector database
ingestion, BigQuery/Snowflake loading, and pandas/Spark pipelines (`pd.read_json("goals.jsonl", lines=True)`).

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

Verify that the export file was populated before running the converter. You can combine multiple exports;
the converter deduplicates goals by their unique ID.

---

## Quickstart

### 1. Direct Pipeline Stream (Stdout)

Stream goals directly from the CLI into JSONL without creating intermediate files:

```sh
set -o pipefail
omi --json goal list --limit 100 --include-inactive | python goals_to_jsonl.py -
```

### 2. Export to a Dedicated JSONL File

Write normalized JSON Lines to a standalone file:

```sh
python goals_to_jsonl.py goals.json -o ~/Reports/goals.jsonl
```

### 3. Filter by Goal Status

Generate a JSONL dataset containing only active goals:

```sh
python goals_to_jsonl.py goals.json --status active -o ~/Reports/active_goals.jsonl
```

---

## CLI Options

| Option | Flag | Description | Default |
| :--- | :--- | :--- | :--- |
| `inputs` | Positional | One or more JSON export files, or `-` for stdin | *(Required)* |
| `--output` | `-o` | Destination JSONL file path | `stdout` |
| `--status` | `--status` | Filter goals by status (`all`, `active`, `completed`, `inactive`) | `all` |
| `--overwrite` | `--overwrite` | Allow overwriting existing destination files | `False` |

---

## JSONL Schema Reference

Each line is a complete, self-contained JSON object without outer wrappers or trailing commas:

| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | `string` | Unique goal identifier (e.g. `goal_abc123`) |
| `title` | `string` | Goal title or milestone summary |
| `goal_type` | `string \| null` | Type of goal (`numeric`, `boolean`, `scale`) |
| `current_value` | `number \| null` | Current recorded progress value |
| `target_value` | `number \| null` | Target milestone value to achieve |
| `min_value` | `number \| null` | Minimum scale value |
| `max_value` | `number \| null` | Maximum scale value |
| `unit` | `string \| null` | Metric unit label (e.g. `books`, `km`, `hours`) |
| `is_active` | `boolean` | Active status flag (`true` or `false`) |
| `is_completed` | `boolean` | Completed status flag (`true` or `false`) |
| `progress_pct` | `number \| null` | Calculated completion percentage (e.g. `75.5`) |
| `created_at` | `string \| null` | ISO-8601 UTC timestamp (`YYYY-MM-DDTHH:MM:SSZ`) |
| `updated_at` | `string \| null` | ISO-8601 UTC timestamp (`YYYY-MM-DDTHH:MM:SSZ`) |

### Sample Record Structure

```json
{
  "id": "goal_01",
  "title": "Read 20 Books",
  "goal_type": "numeric",
  "current_value": 12.0,
  "target_value": 20.0,
  "unit": "books",
  "is_active": true,
  "is_completed": false,
  "progress_pct": 60.0,
  "created_at": "2026-09-01T12:00:00Z",
  "updated_at": "2026-09-15T15:30:00Z"
}
```

---

## Practical `jq` Filtering Snippets

Filter and query your goals JSONL stream directly in the terminal:

```sh
# List all active goals with completion percentage >= 50%
cat goals.jsonl | jq -c 'select(.is_active and .progress_pct >= 50)'

# Extract titles and progress for active goals
cat goals.jsonl | jq -r 'select(.is_active) | "\(.title): \(.progress_pct)%"'
```
