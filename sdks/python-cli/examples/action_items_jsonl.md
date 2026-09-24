# Stream and convert action items to JSON Lines (JSONL / NDJSON)

Use this recipe to stream and export Omi action items and tasks into newline-delimited JSON (JSONL / NDJSON). This format is universally supported by Pandas (`read_json(..., lines=True)`), DuckDB (`read_json_auto(...)`), task tracking agents, and data warehousing pipelines.

It processes action item JSON exports with zero external dependencies (pure Python standard library), normalizes timestamps and boolean completion states, deduplicates cross-file records, and enables fast status filtering.

## Exporting Action Items

Fetch action items with `omi-cli`:

```bash
omi --json action-item list --limit 200 > action_items.json
```

Or pipe directly via standard input:

```bash
omi --json action-item list | python action_items_to_jsonl.py - -o tasks.jsonl
```

## Running the Exporter

Run the script across single or multiple JSON batch files:

```bash
python action_items_to_jsonl.py action_items.json -o tasks.jsonl
```

Filter for pending / open tasks only:

```bash
python action_items_to_jsonl.py action_items.json -o open_tasks.jsonl --status open
```

Merge multiple pages into one clean JSONL file:

```bash
python action_items_to_jsonl.py page1.json page2.json -o all_tasks.jsonl
```

## Downstream Analysis Examples

### Pandas / Python

```python
import pandas as pd

df = pd.read_json("tasks.jsonl", lines=True)
print(df[~df["completed"]][["id", "description", "due_at"]])
```

### DuckDB / SQL

```sql
SELECT
    completed,
    count(*) AS total_items
FROM read_json_auto('tasks.jsonl')
GROUP BY completed;
```
