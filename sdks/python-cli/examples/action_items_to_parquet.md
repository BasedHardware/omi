# Export Omi Action Items to Apache Parquet Columnar Dataset

This recipe exports Omi action items, tasks, deadlines, and completion statuses into an **Apache Parquet** columnar dataset optimized for task SLA tracking, productivity analytics, and fast SQL aggregations via **DuckDB**, **Polars**, **Pandas**, and **Apache Arrow**.

Apache Parquet is an open-source, columnar storage file format providing high-ratio data compression (Snappy, Gzip, Zstandard), zero-copy reads, and predicate pushdown. It is the industry gold standard for large-scale analytical datasets and local data lakes.

---

## Features

- **Columnar Performance**: Dramatically compresses storage footprint with Snappy/Zstandard compression while speeding up filtering and aggregations by up to 50x compared to raw JSON.
- **Productivity & SLA Analytics**: Enables instant aggregation of task completion rates, category distributions, priority breakdowns, and overdue item tracking in DuckDB and Polars.
- **Rich Task Schema**: Captures ISO-8601 UTC timestamps, due dates, completion timestamps, categories, priorities, source conversations, and computed text metrics (`char_len`, `word_count`).
- **Flexible Ingestion**: Reads directly from standard input (UNIX pipe) or saved JSON files, with built-in `--limit` constraints and schema inspection (`--schema`).

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
# Export up to 200 action items into a compressed Parquet file
omi action-items list --json --limit 200 | python examples/action_items_to_parquet.py -o action_items.parquet
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
# Task completion rate by category
duckdb -c "SELECT category, count(*) AS total_tasks, sum(CASE WHEN completed THEN 1 ELSE 0 END) AS completed_tasks, round(avg(CASE WHEN completed THEN 1.0 ELSE 0.0 END)*100, 1) AS completion_pct FROM 'action_items.parquet' GROUP BY category ORDER BY total_tasks DESC;"

# Find open high-priority tasks with due dates
duckdb -c "SELECT id, description, priority, due_at FROM 'action_items.parquet' WHERE completed = false AND priority = 'high' ORDER BY due_at ASC LIMIT 10;"
```

---

## Loading in Python (Polars & Pandas)

### With Polars (Recommended for Speed)

```python
import polars as pl

df = pl.read_parquet("action_items.parquet")
print(df.schema)
print(df.filter(pl.col("completed") == False).select(["id", "description", "priority", "due_at"]))
```

### With Pandas

```python
import pandas as pd

df = pd.read_parquet("action_items.parquet")
print(f"Loaded {len(df)} action items")
print(df.groupby("priority")["completed"].value_counts())
```

---

## Parquet Schema Reference

| Column Name | Type | Description |
|:---|:---|:---|
| `id` | `string` | Unique action item identifier |
| `description` | `string` | Task description or title |
| `completed` | `bool` | Completion state indicator |
| `category` | `string` | Normalized category (e.g. `work`, `personal`, `general`) |
| `priority` | `string` | Priority level (`low`, `normal`, `high`) |
| `created_at` | `string` | UTC timestamp in ISO-8601 format (`YYYY-MM-DDTHH:MM:SSZ`) |
| `updated_at` | `string` | Last updated timestamp in ISO-8601 format |
| `due_at` | `string` | Task deadline timestamp (nullable) |
| `completed_at` | `string` | Task completion timestamp (nullable) |
| `conversation_id` | `string` | Associated conversation ID (nullable) |
| `user_id` | `string` | User identifier |
| `is_deleted` | `bool` | Soft-deleted flag |
| `char_len` | `int64` | Total character count of description |
| `word_count` | `int64` | Word count of description |
