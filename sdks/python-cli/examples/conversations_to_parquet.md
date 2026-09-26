# Export Omi Conversations to Apache Parquet Columnar Dataset

This recipe exports Omi conversations, multi-speaker dialogue transcripts, and structured conversation summaries into an **Apache Parquet** columnar dataset optimized for LLM fine-tuning, retrieval datasets, and analytical queries via **DuckDB**, **Polars**, **Pandas**, and **Apache Arrow**.

Apache Parquet is an open-source, columnar storage file format providing high-efficiency data compression (Snappy, Gzip, Zstandard), zero-copy reads, and predicate pushdown. It is the industry gold standard for machine learning training datasets (Hugging Face Datasets) and local data lakes.

---

## Features

- **Columnar Performance**: Dramatically reduces storage footprint with Snappy/Zstandard compression while speeding up filtering and aggregations by up to 50x compared to raw JSON.
- **AI & Analytics Ready**: Ingests directly into DuckDB, Polars, Pandas, PySpark, or Hugging Face `datasets` for LLM instruction tuning and dialogue dataset compilation.
- **Strict CLI Model Alignment**: Faithfully maps fields from the official CLI `Conversation` model (`omi_cli.models.Conversation`), derives duration from `finished_at - started_at`, extracts clean action-item descriptions, and parses multi-speaker segment text.
- **Flexible Ingestion**: Reads directly from standard input (UNIX pipe) or saved JSON files, with built-in `--limit` constraints, schema inspection (`--schema`), and automatic zero-dependency fallback when `pyarrow` is not installed.

---

## Quickstart

### 1. Install Dependencies

Parquet serialization uses the standard `pyarrow` library:

```bash
pip install pyarrow
```

### 2. Stream Conversations from Omi CLI to Parquet

Pipe JSON output directly into `conversations_to_parquet.py`. To capture dialogue text, include `--include-transcript`:

```bash
# Export up to 200 conversations with multi-speaker transcripts into a compressed Parquet file
omi --json conversation list --include-transcript --limit 200 | python examples/conversations_to_parquet.py -o conversations.parquet
```

> **Note**: The Omi CLI list endpoint omits transcripts by default for bandwidth optimization. Adding `--include-transcript` instructs the server to include `transcript_segments`.

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
# Overall conversation count and total duration in minutes
duckdb -c "SELECT count(*) AS total_conversations, round(sum(duration_seconds)/60.0, 1) AS total_minutes FROM 'conversations.parquet';"

# Find conversations with multiple speakers and their word counts
duckdb -c "SELECT id, title, num_speakers, word_count FROM 'conversations.parquet' WHERE num_speakers > 1 ORDER BY word_count DESC LIMIT 10;"

# Filter conversations by category
duckdb -c "SELECT id, title, category, round(duration_seconds/60.0, 1) AS duration_min FROM 'conversations.parquet' WHERE category = 'work' LIMIT 10;"
```

---

## Loading in Python (Polars & Pandas)

### With Polars (Recommended for Speed)

```python
import polars as pl

df = pl.read_parquet("conversations.parquet")
print(df.schema)
print(df.filter(pl.col("num_speakers") > 1).select(["id", "title", "duration_seconds", "word_count"]))
```

### With Pandas

```python
import pandas as pd

df = pd.read_parquet("conversations.parquet")
print(f"Loaded {len(df)} conversations")
print(df.groupby("category")["duration_seconds"].mean())
```

---

## Parquet Schema Reference

The schema faithfully mirrors the official `omi_cli.models.Conversation` attributes emitted by `omi --json conversation list`:

| Column Name | Type | Description |
|:---|:---|:---|
| `id` | `string` | Unique conversation identifier |
| `title` | `string` | Structured conversation title |
| `overview` | `string` | Structured overview / summary |
| `category` | `string` | Normalized category (e.g. `work`, `lifestyle`, `interesting`) |
| `language` | `string` | Detected language code (e.g. `en`) |
| `source` | `string` | Source origin (e.g. `omi`, `audio_transcript`) |
| `created_at` | `string` | UTC ISO-8601 creation timestamp |
| `updated_at` | `string` | UTC ISO-8601 last update timestamp |
| `started_at` | `string` | UTC ISO-8601 audio / dialogue start timestamp |
| `finished_at` | `string` | UTC ISO-8601 audio / dialogue end timestamp |
| `duration_seconds` | `float64` | Derived conversation duration (`finished_at - started_at`) in seconds |
| `num_segments` | `int64` | Total number of transcript segments |
| `num_speakers` | `int64` | Number of distinct speakers identified |
| `full_transcript` | `string` | Full formatted multi-speaker transcript text |
| `action_items` | `string` | JSON string array of action item descriptions |
| `char_len` | `int64` | Character length of the full transcript |
| `word_count` | `int64` | Word count of the full transcript |

---

## Compatibility

- Fully compatible with Python 3.10, 3.11, and 3.12.
- Fully compatible with DuckDB, Polars, Pandas, Apache Arrow, and PySpark.
- Automatic zero-dependency fallback to structured columnar JSON if `pyarrow` is not installed.
