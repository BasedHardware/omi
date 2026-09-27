# Convert conversation-list exports to Apache Parquet dataset

Convert exported Omi conversations into an **Apache Parquet** dataset file. Parquet is an open-source, columnar storage format optimized for fast analytical queries, high data compression, and direct ingestion into data science and ML frameworks (Pandas, Polars, DuckDB, PySpark).

This recipe complements [`conversations_csv.md`](conversations_csv.md) and [`conversations_sqlite.md`](conversations_sqlite.md).

## Prerequisites

- Python 3.10+
- `pyarrow` (optional for binary Parquet export; falls back to columnar JSON if not installed):
  ```sh
  pip install pyarrow
  ```

## Export from Omi CLI

To export conversations with full speaker diarization and transcript turns, pass `--include-transcript` with the `--json` root flag:

```sh
omi --json conversation list --include-transcript --limit 200 > conversations.json
```

Or pipe directly into the converter script:

```sh
omi --json conversation list --include-transcript --limit 200 | python sdks/python-cli/examples/conversations_to_parquet.py -o conversations.parquet
```

## Convert Saved JSON Files

Convert one or more saved JSON pages into a Parquet dataset:

```sh
python sdks/python-cli/examples/conversations_to_parquet.py conversations.json -o conversations.parquet
```

Merge multiple pagination export files into a single Parquet dataset:

```sh
python sdks/python-cli/examples/conversations_to_parquet.py page1.json page2.json page3.json -o conversations.parquet
```

Choose compression codec (`snappy` default, `gzip`, or `none`):

```sh
python sdks/python-cli/examples/conversations_to_parquet.py conversations.json -o conversations.parquet -c gzip
```

## Parquet Schema

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | `string` | No | Unique conversation identifier |
| `title` | `string` | Yes | Extracted or custom conversation title |
| `overview` | `string` | Yes | LLM summary overview of conversation |
| `category` | `string` | Yes | Category tag (e.g. `work`, `personal`, `education`) |
| `source` | `string` | Yes | Recording source (e.g. `omi`, `desktop`, `phone_call`) |
| `language` | `string` | Yes | ISO 639-1 language code |
| `user_id` | `string` | Yes | Account user identifier (if present) |
| `started_at` | `string` | Yes | UTC timestamp (`YYYY-MM-DDTHH:MM:SSZ`) |
| `finished_at` | `string` | Yes | UTC timestamp (`YYYY-MM-DDTHH:MM:SSZ`) |
| `created_at` | `string` | Yes | UTC timestamp of record creation |
| `updated_at` | `string` | Yes | UTC timestamp of record update |
| `duration_seconds`| `float64`| No | Computed duration (`finished_at - started_at` in seconds) |
| `is_discarded` | `bool` | No | Flag indicating if conversation was marked discarded |
| `action_items` | `string` | Yes | JSON array of action item description strings |
| `num_action_items`| `int32` | No | Total count of action items extracted |
| `full_transcript`| `string` | Yes | Formatted multi-speaker transcript turns |
| `num_segments` | `int32` | No | Total count of speech segments |
| `num_speakers` | `int32` | No | Count of distinct diarized speakers |
| `char_len` | `int32` | No | Character length of full transcript |
| `word_count` | `int32` | No | Word count of full transcript |

## Analytical Queries

### Query with DuckDB

DuckDB executes fast SQL directly on Parquet files without database installation:

```python
import duckdb

# Connect in-memory
con = duckdb.connect()

# Total speaking time & conversation count by category
df = con.execute("""
    SELECT 
        category,
        COUNT(*) AS total_conversations,
        ROUND(SUM(duration_seconds) / 60.0, 1) AS total_minutes,
        SUM(num_action_items) AS total_actions
    FROM 'conversations.parquet'
    GROUP BY category
    ORDER BY total_conversations DESC
""").df()

print(df)
```

### Query with Polars

```python
import polars as pl

df = pl.read_parquet("conversations.parquet")

# Filter multi-speaker meetings with transcripts
meetings = df.filter(
    (pl.col("num_speakers") > 1) & (pl.col("word_count") > 50)
).select(["started_at", "title", "num_speakers", "duration_seconds", "word_count"])

print(meetings)
```

### Query with Pandas

```python
import pandas as pd

df = pd.read_parquet("conversations.parquet")
print(f"Total conversations: {len(df)}")
print(f"Average duration: {df['duration_seconds'].mean() / 60:.1f} mins")
```
