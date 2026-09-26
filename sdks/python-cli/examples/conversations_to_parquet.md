# Export Omi Conversations to Apache Parquet Columnar Dataset

This recipe exports Omi conversations, multi-speaker transcripts, summaries, and action items into an **Apache Parquet** columnar dataset optimized for LLM fine-tuning, analytics, and high-performance SQL queries via **DuckDB**, **Polars**, **Pandas**, and **Apache Arrow**.

Apache Parquet is an open-source, columnar storage file format providing high-ratio data compression (Snappy, Gzip, Zstandard), zero-copy reads, and predicate pushdown. It is the industry gold standard for large-scale language model dialogue datasets (Hugging Face Datasets) and local data lakes.

---

## Features

- **Columnar Performance**: Dramatically compresses storage footprint with Snappy/Zstandard compression while speeding up filtering and aggregations by up to 50x compared to raw JSON.
- **LLM Training & Fine-Tuning Ready**: Prepares unified dialogue transcripts, speaker turns, and metadata for Hugging Face `datasets`, SFT training pipelines, and RAG semantic search.
- **Rich Multi-Modal Schema**: Captures ISO-8601 UTC timestamps, speaker counts, segment statistics, duration, structured categories, language codes, and computed text metrics (`char_len`, `word_count`).
- **Flexible Ingestion**: Reads directly from standard input (UNIX pipe) or saved JSON files, with built-in `--limit` constraints and schema inspection (`--schema`).

---

## Quickstart

### 1. Install Dependencies

Parquet serialization uses the standard `pyarrow` library:

```bash
pip install pyarrow
```

### 2. Stream Conversations from Omi CLI to Parquet

Pipe JSON output directly into `conversations_to_parquet.py`:

```bash
# Export up to 200 conversations into a compressed Parquet file
omi conversations list --json --limit 200 | python examples/conversations_to_parquet.py -o conversations.parquet
```

### 3. Convert an Existing JSON Export

```bash
# Convert an existing export with Zstandard high-ratio compression
python examples/conversations_to_parquet.py -i conversations_export.json -o conversations.parquet --compression zstd
```

### 4. Inspect Parquet Table Schema

Inspect the columnar schema and row count without writing to disk:

```bash
python examples/conversations_to_parquet.py -i conversations_export.json --schema
```

---

## Querying with DuckDB

DuckDB queries Parquet files directly with zero database setup:

```bash
# Count conversations and total recorded duration by category
duckdb -c "SELECT category, count(*) AS total_conversations, round(sum(duration_seconds)/60.0, 1) AS total_minutes FROM 'conversations.parquet' GROUP BY category ORDER BY total_minutes DESC;"

# Search for conversations mentioning specific engineering terms
duckdb -c "SELECT id, title, category, num_speakers FROM 'conversations.parquet' WHERE lower(full_transcript) LIKE '%parquet%' LIMIT 10;"
```

---

## Loading in Python (Polars & Pandas)

### With Polars (Recommended for Speed)

```python
import polars as pl

df = pl.read_parquet("conversations.parquet")
print(df.schema)
print(df.filter(pl.col("num_speakers") > 1).select(["id", "title", "duration_seconds"]))
```

### With Pandas

```python
import pandas as pd

df = pd.read_parquet("conversations.parquet")
print(f"Loaded {len(df)} conversations")
print(df.groupby("category")["word_count"].mean())
```

---

## Parquet Schema Reference

| Column Name | Type | Description |
|:---|:---|:---|
| `id` | `string` | Unique conversation identifier |
| `title` | `string` | Conversation title or heading |
| `overview` | `string` | High-level summary / overview |
| `category` | `string` | Normalized category (e.g. `work`, `personal`, `ideas`) |
| `language` | `string` | ISO language code (e.g. `en`) |
| `source` | `string` | Conversation source origin (`omi`, `desktop`, etc.) |
| `user_id` | `string` | User identifier |
| `created_at` | `string` | UTC timestamp in ISO-8601 format (`YYYY-MM-DDTHH:MM:SSZ`) |
| `updated_at` | `string` | Last updated timestamp in ISO-8601 format |
| `started_at` | `string` | Session start timestamp |
| `finished_at` | `string` | Session finish timestamp |
| `duration_seconds` | `float64` | Total audio/session duration in seconds |
| `is_discarded` | `bool` | Discarded/deleted flag |
| `num_segments` | `int64` | Total count of transcription segments |
| `num_speakers` | `int64` | Number of distinct identified speakers |
| `full_transcript` | `string` | Full multi-speaker concatenated dialogue transcript |
| `action_items` | `string` | JSON-encoded string array of identified action items |
| `char_len` | `int64` | Total character count of full transcript |
| `word_count` | `int64` | Word count of full transcript |
