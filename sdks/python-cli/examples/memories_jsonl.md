# Stream and convert memories to JSON Lines (JSONL / NDJSON)

Use this recipe to stream and export Omi memories, facts, and learnings into newline-delimited JSON (JSONL / NDJSON). This format is universally supported by Pandas (`read_json(..., lines=True)`), DuckDB (`read_json_auto(...)`), vector databases (Chroma, Pinecone, Qdrant, Weaviate), RAG pipelines, and LLM fine-tuning datasets.

It processes memory JSON exports with zero external dependencies (pure Python standard library), normalizes timestamps to UTC, cleans category and tag arrays, and supports cross-file deduplication.

## Exporting Memories

Fetch memories with `omi-cli`:

```bash
omi --json memory list --limit 200 > memories.json
```

Or pipe directly via standard input:

```bash
omi --json memory list | python memories_to_jsonl.py - -o memories.jsonl
```

## Running the Exporter

Run the script across single or multiple JSON batch files:

```bash
python memories_to_jsonl.py memories.json -o memories.jsonl
```

Filter by specific categories:

```bash
python memories_to_jsonl.py memories.json -o work_memories.jsonl --category work,skills
```

Merge multiple pages into one clean JSONL file:

```bash
python memories_to_jsonl.py page1.json page2.json page3.json -o all_memories.jsonl
```

## Downstream Analysis Examples

### Vector Embedding / RAG Ingestion

```python
import json

with open("memories.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        record = json.loads(line)
        # Ingest directly into embedding or vector storage
        print(f"Embedding memory [{record['id']}]: {record['content'][:50]}...")
```

### DuckDB / SQL

```sql
SELECT
    category,
    count(*) AS total_memories
FROM read_json_auto('memories.jsonl')
GROUP BY category
ORDER BY total_memories DESC;
```
