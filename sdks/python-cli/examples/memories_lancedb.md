# Export OMI Memories to LanceDB Vector Database

This recipe exports OMI memories, facts, and learnings into a **LanceDB** serverless vector database table for high-performance, low-latency local semantic search and Retrieval-Augmented Generation (RAG).

LanceDB is an open-source, embedded vector database built on Apache Arrow with zero server infrastructure overhead, making it ideal for local-first AI agents, desktop assistants, and offline semantic memory retrieval.

---

## Features

- **Zero-Dependency Core**: Converts OMI memory exports into PyArrow / LanceDB compatible schemas without requiring native C++ extensions or cloud API keys.
- **Embedded Serverless Architecture**: Writes directly to local disk (`.lance` tables) or standard JSONL streaming payloads.
- **Automatic Vector Normalization**: Generates reproducible, unit-normalized float vectors for schema compliance or seamlessly ingests existing multi-modal embeddings.
- **Deduplication & Metadata Preservation**: Automatically preserves timestamps, user IDs, categories, tags, and custom metadata attributes.

---

## Quickstart

### 1. Export Memories from OMI CLI

```bash
# Export all memories to JSON
omi memory list --limit 1000 --json > memories.json
```

### 2. Convert to LanceDB Ingestion Payload (Zero Dependencies)

```bash
python examples/memories_to_lancedb.py \
  --input memories.json \
  --output memories.jsonl \
  --table-name memories \
  --dim 384
```

### 3. Direct Ingestion (when `lancedb` is installed)

```bash
pip install lancedb pyarrow

python examples/memories_to_lancedb.py \
  --input memories.json \
  --output ./lancedb_data \
  --table-name memories \
  --mode direct \
  --overwrite
```

---

## Querying Memories in LanceDB

Once ingested, you can query your memories with sub-millisecond vector similarity search in Python:

```python
import lancedb

# 1. Connect to local LanceDB store
db = lancedb.connect("./lancedb_data")
table = db.open_table("memories")

# 2. Perform vector semantic search
query_vector = [0.05] * 384  # Replace with your embedding model (e.g., SentenceTransformers, OpenAI, Ollama)
results = table.search(query_vector).limit(5).to_pandas()

# 3. Inspect results
for idx, row in results.iterrows():
    print(f"[{row['category']}] (Score: {row['_distance']:.4f}) {row['content']}")
```

---

## Command-Line Options

| Option | Shorthand | Default | Description |
|---|---|---|---|
| `--input` | `-i` | *(required)* | Path to OMI memories JSON / JSONL file or `-` for stdin |
| `--output` | `-o` | *(required)* | Output file path (payload mode) or directory (direct mode) |
| `--table-name` | `-t` | `memories` | Destination LanceDB table name |
| `--dim` | `-d` | `384` | Vector embedding dimension size |
| `--mode` | `-m` | `payload` | `payload` (JSONL for LanceDB) or `direct` (native LanceDB table write) |
| `--no-dedup` | | `False` | Disable deduplication by memory ID |
| `--overwrite` | | `False` | Overwrite target output if it already exists |
| `--pretty` | | `False` | Pretty-print JSON summary output to stdout |

---

## Running the Recipe Tests

To execute the unit test suite:

```bash
pytest examples/test_memories_to_lancedb.py
```
