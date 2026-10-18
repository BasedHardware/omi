# Convert a conversation export to Apache Parquet

Use this recipe to feed conversations into DuckDB, Polars, Pandas, or
Spark — columnar Parquet makes per-day/category/duration aggregation fast
at any scale. It reads one or more `conversation list` exports and writes
one `.parquet` file.

Requires [`pyarrow`](https://pypi.org/project/pyarrow/):

```sh
pip install pyarrow
```

## The converter

The script lives at [`conversations_to_parquet.py`](conversations_to_parquet.py)
in this directory.

**Typed schema:**

```
id                       string
title                    string     (from structured fallback)
category                 string     (from structured fallback)
overview                 string     (from structured fallback)
source                   string
language                 string
started_at               timestamp[ms, UTC]
finished_at              timestamp[ms, UTC]
duration_minutes         double     (NULL when incomplete)
action_items_count       int64
transcript_segment_count int64
raw_json                 string     (the untouched record)
```

* `raw_json` keeps every field the columns drop — query it with JSON
  functions when you need something off-schema.
* Multi-page dedupe — each conversation ID lands once.

## Usage

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
python conversations_to_parquet.py conversations.json -o conversations.parquet
```

## Query it

```sh
duckdb -c "SELECT category, COUNT(*), AVG(duration_minutes)
           FROM 'conversations.parquet' GROUP BY 1 ORDER BY 2 DESC"
```

```python
import polars as pl
df = pl.read_parquet("conversations.parquet")
df.group_by("category").agg(pl.col("duration_minutes").mean())
```

```python
import pandas as pd
df = pd.read_parquet("conversations.parquet")
```

```python
df = spark.read.parquet("conversations.parquet")
```

## Safety

* `..` in the `-o` path is refused.
* Existing file never overwritten — `.partial` write then atomic rename.
* Malformed JSON or missing input exits `2`.
