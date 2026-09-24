# Stream and convert goals to JSON Lines (JSONL / NDJSON)

Use this recipe to stream and export Omi goals and habit progression into newline-delimited JSON (JSONL / NDJSON). This format is universally supported by Pandas (`read_json(..., lines=True)`), DuckDB (`read_json_auto(...)`), habit analytics dashboards, and autonomous goal-tracking agents.

It processes goal JSON exports with zero external dependencies (pure Python standard library), computes completion percentage (`progress_pct`), normalizes UTC timestamps, deduplicates cross-file records, and enables fast status filtering (`--status active|completed|all`).

## Exporting Goals

Fetch goals with `omi-cli`:

```bash
omi --json goal list --limit 200 > goals.json
```

Or pipe directly via standard input:

```bash
omi --json goal list | python goals_to_jsonl.py - -o goals.jsonl
```

## Running the Exporter

Run the script across single or multiple JSON batch files:

```bash
python goals_to_jsonl.py goals.json -o goals.jsonl
```

Filter for active goals only:

```bash
python goals_to_jsonl.py goals.json -o active_goals.jsonl --status active
```

Merge multiple pages into one clean JSONL file:

```bash
python goals_to_jsonl.py page1.json page2.json -o all_goals.jsonl
```

## Downstream Analysis Examples

### Pandas / Python

```python
import pandas as pd

df = pd.read_json("goals.jsonl", lines=True)
print(df[["title", "progress_pct", "completed", "target_date"]])
```

### DuckDB / SQL

```sql
SELECT
    completed,
    avg(progress_pct) AS avg_completion_pct,
    count(*) AS total_goals
FROM read_json_auto('goals.jsonl')
GROUP BY completed;
```
