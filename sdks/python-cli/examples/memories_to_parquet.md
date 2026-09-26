# Export Omi Memories to Apache Parquet Columnar Dataset

This recipe exports Omi memories, facts, and learnings into an **Apache Parquet** columnar dataset optimized for AI model fine-tuning, analytics, and ultra-fast analytical queries using modern data lake engines such as **DuckDB**, **Polars**, **Pandas**, and **Apache Arrow**.

Apache Parquet is an open-source, columnar storage file format providing high-efficiency data compression (Snappy, Gzip, ZSTD), zero-copy reads, and predicate pushdown. It is the industry gold standard for machine learning training datasets (Hugging Face Datasets) and local data lakes.

---

## Features

- **Columnar Performance**: Dramatically reduces storage footprint with Snappy/Zstandard compression while speeding up filtering and aggregations by up to 50x compared to raw JSON.
- **AI & Analytics Ready**: Ingests directly into DuckDB, Polars, Pandas, PySpark, or Hugging Face `datasets` for LLM fine-tuning and evaluation.
- **Strict CLI Model Alignment**: Faithfully maps fields from the official CLI `Memory` model (`omi_cli.models.Memory`) including ISO-8601 UTC timestamps, categories, visibility, user flags (`manually_added`, `reviewed`, `edited`), tags, and pre-computed text length metrics (`char_len`, `word_count`).
- **Flexible Ingestion**: Reads directly from standard input (UNIX pipe) or saved JSON files, with built-in `--limit` constraints, schema inspection (`--schema`), and automatic zero-dependency fallback when `pyarrow` is not installed.

---

## Quickstart

### 1. Install Dependencies

Parquet serialization uses the standard `pyarrow` library:

```bash
pip install pyarrow
```

### 2. Stream Memories from Omi CLI to Parquet

Pipe JSON output directly into `memories_to_parquet.py`:

```bash
# Export up to 200 memories into a compressed Parquet file
omi --json memory list --limit 200 | python examples/memories_to_parquet.py -o memories.parquet
```

### 3. Convert an Existing JSON Export

```bash
# Convert an existing export with Zstandard high-ratio compression
python examples/memories_to_parquet.py -i memories_export.json -o memories.parquet --compression zstd
```

### 4. Inspect Parquet Table Schema

Inspect the columnar schema and row count without writing to disk:

```bash
python examples/memories_to_parquet.py -i memories_export.json --schema
```

---

## Querying with DuckDB

DuckDB queries Parquet files directly with zero database setup:

```bash
# Count memories by category
duckdb -c "SELECT category, count(*) AS count FROM 'memories.parquet' GROUP BY category ORDER BY count DESC;"

# Filter reviewed work memories
duckdb -c "SELECT id, content FROM 'memories.parquet' WHERE reviewed = true AND category = 'work' LIMIT 10;"
```

---

## Loading in Python (Polars & Pandas)

### With Polars (Recommended for Speed)

```python
import polars as pl

df = pl.read_parquet("memories.parquet")
print(df.schema)
print(df.filter(pl.col("reviewed") == True).select(["id", "content", "category"]))
```

### With Pandas

```python
import pandas as pd

df = pd.read_parquet("memories.parquet")
print(f"Loaded {len(df)} memories")
print(df.groupby("category")["char_len"].mean())
```

---

## Parquet Schema Reference

The schema faithfully mirrors the official `omi_cli.models.Memory` attributes emitted by `omi --json memory list`:

| Column Name | Type | Description |
|:---|:---|:---|
| `id` | `string` | Unique memory identifier |
| `content` | `string` | Memory text content |
| `category` | `string` | Memory category from `MemoryCategory` (e.g. `interesting`, `system`, `work`, `lifestyle`, `hobbies`, `other`) |
| `visibility` | `string` | Access scope from `MemoryVisibility` (`private`, `public`) |
| `created_at` | `string` | UTC timestamp in ISO-8601 format (`YYYY-MM-DDTHH:MM:SSZ`) |
| `updated_at` | `string` | Last updated timestamp in ISO-8601 format |
| `tags` | `string` | JSON-encoded string array of assigned tags |
| `manually_added` | `bool` | Whether memory was manually created |
| `reviewed` | `bool` | Whether memory has been reviewed by the user |
| `edited` | `bool` | Whether memory was edited after creation |
| `char_len` | `int64` | Total character count of memory content |
| `word_count` | `int64` | Word count of memory content |
