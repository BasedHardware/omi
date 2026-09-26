# Export Omi Action Items to Apache Parquet Columnar Dataset

This recipe exports Omi action items, tasks, deadlines, and completion statuses into an **Apache Parquet** columnar dataset optimized for task SLA tracking, productivity analytics, and fast SQL aggregations via **DuckDB**, **Polars**, **Pandas**, and **Apache Arrow**.

Apache Parquet is an open-source, columnar storage file format providing high-ratio data compression (Snappy, Gzip, Zstandard), zero-copy reads, and predicate pushdown. It is the industry gold standard for large-scale analytical datasets and local data lakes.

---

## Features

- **Columnar Performance**: Dramatically compresses storage footprint with Snappy/Zstandard compression while speeding up filtering and aggregations by up to 50x compared to raw JSON.
- **Productivity & SLA Analytics**: Enables instant aggregation of task completion rates, deadline tracking, and overdue item detection in DuckDB and Polars.
- **Strict CLI Model Alignment**: Faithfully maps fields from the official CLI `ActionItem` model (`omi_cli.models.ActionItem`) including ISO-8601 UTC timestamps, due dates, completion timestamps, source conversations, and precomputed text metrics (`char_len`, `word_count`).
- **Flexible Ingestion**: Reads directly from standard input (UNIX pipe) or saved JSON files, with built-in `--limit` constraints, schema inspection (`--schema`), and automatic zero-dependency fallback when `pyarrow` is not installed.

---

## Quickstart

### 1. Install Dependencies

Parquet serialization uses the standard `pyarrow` library:

```bash
pip install pyarrow
```

### 2. Stream Action Items from Omi CLI to Parquet

Pipe JSON output directly into `action_items_to_parquet.py`:

```bash
# Export up to 100 action items into a compressed Parquet file
omi --json action-item list --limit 100 | python examples/action_items_to_parquet.py -o action_items.parquet
```

### 3. Convert an Existing JSON Export

```bash
# Convert an existing export with Zstandard high-ratio compression
python examples/action_items_to_parquet.py -i action_items_export.json -o action_items.parquet --compression zstd
```

### 4. Inspect Parquet Table Schema

Inspect the columnar schema and row count without writing to disk:

```bash
python examples/action_items_to_parquet.py -i action_items_export.json --schema
```

---

## Querying with DuckDB

DuckDB queries Parquet files directly with zero database setup:

```bash
# Overall task completion summary
duckdb -c "SELECT count(*) AS total_tasks, sum(CASE WHEN completed THEN 1 ELSE 0 END) AS completed_tasks, round(avg(CASE WHEN completed THEN 1.0 ELSE 0.0 END)*100, 1) AS completion_pct FROM 'action_items.parquet';"

# Find open tasks with upcoming due dates
duckdb -c "SELECT id, description, due_at FROM 'action_items.parquet' WHERE completed = false AND due_at IS NOT NULL ORDER BY due_at ASC LIMIT 10;"

# Find tasks linked to a specific conversation
duckdb -c "SELECT id, description, completed, created_at FROM 'action_items.parquet' WHERE conversation_id IS NOT NULL ORDER BY created_at DESC LIMIT 10;"
```

---

## Loading in Python (Polars & Pandas)

### With Polars (Recommended for Speed)

```python
import polars as pl

df = pl.read_parquet("action_items.parquet")
print(df.schema)
print(df.filter(pl.col("completed") == False).select(["id", "description", "due_at"]))
```

### With Pandas

```python
import pandas as pd

df = pd.read_parquet("action_items.parquet")
print(f"Loaded {len(df)} action items")
print(df["completed"].value_counts())
```

---

## Parquet Schema Reference

The schema faithfully mirrors the official `omi_cli.models.ActionItem` attributes emitted by `omi --json action-item list`:

| Column Name | Type | Description |
|:---|:---|:---|
| `id` | `string` | Unique action item identifier |
| `description` | `string` | Task description or title |
| `completed` | `bool` | Completion state indicator |
| `created_at` | `string` | UTC ISO-8601 creation timestamp |
| `updated_at` | `string` | UTC ISO-8601 last update timestamp |
| `due_at` | `string` | UTC ISO-8601 task deadline timestamp |
| `completed_at` | `string` | UTC ISO-8601 task completion timestamp |
| `conversation_id` | `string` | ID of the source conversation (if extracted from dialogue) |
| `char_len` | `int64` | Character length of the task description |
| `word_count` | `int64` | Word count of the task description |

---

## Compatibility

- Fully compatible with Python 3.10, 3.11, and 3.12.
- Fully compatible with DuckDB, Polars, Pandas, Apache Arrow, and PySpark.
- Automatic zero-dependency fallback to structured columnar JSON if `pyarrow` is not installed.
