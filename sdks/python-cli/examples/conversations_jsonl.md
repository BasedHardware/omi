# Stream and convert conversations to JSON Lines (JSONL / NDJSON)

Use this recipe to stream and export Omi conversation records into newline-delimited JSON (JSONL / NDJSON). This format is universally supported by Pandas (`read_json(..., lines=True)`), DuckDB (`read_json_auto(...)`), Apache Spark, embeddings/vector pipelines, and fine-tuning datasets.

It processes raw exports without external dependencies (pure Python standard library), normalizes timestamps to UTC ISO strings, extracts structured highlights, and automatically deduplicates cross-page records.

## Exporting Conversations

Fetch conversations with `omi-cli`:

```bash
omi --json conversation list --limit 200 > conversations.json
```

Or pipe directly via standard input:

```bash
omi --json conversation list | python conversations_to_jsonl.py - -o conversations.jsonl
```

## Running the Exporter

Run the script across single or multiple JSON batch files:

```bash
python conversations_to_jsonl.py conversations.json -o conversations.jsonl
```

Or merge multiple pages into one clean JSONL file:

```bash
python conversations_to_jsonl.py page1.json page2.json page3.json -o full_archive.jsonl
```

## Downstream Analysis Examples

### Pandas / Python

```python
import pandas as pd

df = pd.read_json("conversations.jsonl", lines=True)
print(df[["id", "title", "category", "started_at", "turns_count"]].head())
```

### DuckDB / SQL

```sql
SELECT
    category,
    count(*) AS total_conversations,
    avg(turns_count) AS avg_turns
FROM read_json_auto('conversations.jsonl')
GROUP BY category
ORDER BY total_conversations DESC;
```
