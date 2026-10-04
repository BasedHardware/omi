# Recipe: Export Action Items to JSON Lines (JSONL / NDJSON)

Export Omi action items and tasks into standard newline-delimited JSON Lines (`.jsonl` / NDJSON, RFC 8259 compliant).

## Why JSON Lines?

While Markdown and CSV exports are ideal for human reading and spreadsheets, **JSON Lines (JSONL)** is the preferred data exchange format for:
- **Streaming & Unix Pipelines**: Process tasks line-by-line using `jq`, `grep`, `awk`, or `sed` without loading entire JSON trees into memory.
- **Analytics & SQL Engines**: Query task data directly with [DuckDB](https://duckdb.org/) (`SELECT * FROM read_ndjson('tasks.jsonl')`) or Apache Spark without preprocessing.
- **Data Science**: Direct ingestion into Pandas using `pd.read_json("tasks.jsonl", lines=True)`.
- **LLM Prompting & Fine-Tuning**: Feed discrete task records into context windows or dataset preparation pipelines for autonomous AI agents.

---

## Prerequisites

1. Install and authenticate the Omi CLI:
   ```bash
   pip install -e .
   omi auth login
   ```
2. Verify access by listing existing tasks:
   ```bash
   omi action-item list --limit 5
   ```

---

## Quick Start

### 1. Unix Pipeline (Stream to stdout or file)

Stream live task records directly through standard input (`-`):

```bash
# Export all action items to tasks.jsonl via stdin pipeline
omi --json action-item list --limit 200 | python examples/action_items_to_jsonl.py - -o tasks.jsonl
```

Or print directly to stdout for shell piping:

```bash
# Print JSONL lines to stdout
omi --json action-item list | python examples/action_items_to_jsonl.py -
```

### 2. File-Based Export

Export to a JSON file first, then convert:

```bash
# Step 1: Export raw action items
omi --json action-item list --limit 200 > tasks.json

# Step 2: Convert to clean JSONL
python examples/action_items_to_jsonl.py tasks.json -o tasks.jsonl
```

### 3. Filter by Status

Only export pending/open tasks:

```bash
# Filter open tasks only
omi --json action-item list | python examples/action_items_to_jsonl.py - --status open -o open_tasks.jsonl
```

Only export completed tasks:

```bash
# Filter completed tasks only
omi --json action-item list | python examples/action_items_to_jsonl.py - --status completed -o completed_tasks.jsonl
```

---

## Multi-Page Export & Deduplication

If you have a large number of action items across multiple pagination requests, you can dump several pages and merge them cleanly into one deduplicated `.jsonl` file.

The converter automatically merges records with identical IDs, keeping the record with the most recent `updated_at` (or `created_at`) timestamp:

```bash
# Export multiple pages using --limit and --offset
omi --json action-item list --limit 100 --offset 0 > page1.json
omi --json action-item list --limit 100 --offset 100 > page2.json

# Combine and deduplicate into a single JSONL file
python examples/action_items_to_jsonl.py page1.json page2.json -o all_tasks.jsonl
```

---

## Command Options Reference

| Option | Default | Description |
| :--- | :--- | :--- |
| `inputs` | *(required)* | One or more JSON files, or `-` for standard input. |
| `-o, --output` | `stdout` | Destination `.jsonl` file path. |
| `-f, --overwrite` | `False` | Overwrite destination file if it already exists. |
| `--status` | `all` | Filter by task status: `all`, `open`, or `completed`. |
| `--sort` | `created_desc` | Sort order: `created_desc`, `created_asc`, `due_date`, `none`. |

---

## JSONL Output Specification

Each line in the resulting `.jsonl` file is a self-contained, valid JSON object (RFC 8259) terminated by `\n` without outer brackets or trailing commas:

```json
{"id":"act_01h7x89q","description":"Review quarterly project roadmap","completed":false,"status":"open","created_at":"2026-10-01T14:30:00Z","updated_at":"2026-10-01T14:30:00Z","due_date":"2026-10-08T18:00:00Z","conversation_id":"conv_99f2a1"}
{"id":"act_01h7x91b","description":"Send signed agreement to supplier","completed":true,"status":"completed","created_at":"2026-09-29T10:15:00Z","updated_at":"2026-09-30T08:20:00Z","due_date":null,"conversation_id":null}
```

### Schema Attributes

- `id` *(string)*: Unique task identifier. Falls back to a deterministic SHA-256 synthetic ID (`syn_<hash>`) if the record omitted an ID.
- `description` *(string)*: Clean text description of the action item.
- `completed` *(boolean)*: Canonical boolean (`true` / `false`), normalized across string booleans (`"true"`, `"1"`, `"done"`, etc.).
- `status` *(string)*: Derived status indicator (`"open"` or `"completed"`).
- `created_at` *(string / null)*: ISO-8601 / RFC 3339 UTC timestamp with `Z` suffix.
- `updated_at` *(string / null)*: ISO-8601 / RFC 3339 UTC timestamp with `Z` suffix.
- `due_date` *(string / null)*: ISO-8601 / RFC 3339 UTC due timestamp, or `null` if unassigned.
- `conversation_id` *(string / null)*: Associated conversation identifier, or `null`.

---

## Data Analysis & Pipeline Recipes

### Query Directly with DuckDB

Run high-performance SQL analytics directly over your JSON Lines export without setting up a database:

```sql
-- Query task summary statistics
SELECT
    status,
    count(*) AS task_count,
    count(due_date) AS tasks_with_deadlines
FROM read_ndjson('tasks.jsonl')
GROUP BY status;
```

### Filter with `jq`

Extract high-priority tasks due within the upcoming week:

```bash
cat tasks.jsonl | jq -c 'select(.completed == false and .due_date != null)'
```

Count open tasks:

```bash
cat tasks.jsonl | jq -s '[.[] | select(.completed == false)] | length'
```

### Load into Pandas DataFrame

```python
import pandas as pd

df = pd.read_json("tasks.jsonl", lines=True)
print(df[["id", "description", "status", "due_date"]].head())
```

---

## Design Principles

- **Zero Third-Party Dependencies**: Written entirely with the Python 3.9+ standard library (`argparse`, `datetime`, `hashlib`, `json`, `os`, `pathlib`, `sys`, `tempfile`).
- **Atomic File Writing**: Writes via a temporary file in the destination directory and performs an atomic replace (`os.replace`) to prevent corrupted or partial outputs.
- **Path Traversal Defense**: Rejects parent directory traversal tokens (`..`) in destination paths.
- **Pipeline Integrity**: Handles `BrokenPipeError` gracefully when downstream commands (such as `head` or `less`) terminate early.
