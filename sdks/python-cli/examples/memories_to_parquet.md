# Convert a memory export to Apache Parquet

Use this recipe to feed memories into DuckDB, Polars, Pandas, or Spark —
Parquet's columnar layout makes aggregations and scans fast at any scale.
It reads one or more `memory list` exports and writes one `.parquet` file.

Requires [`pyarrow`](https://pypi.org/project/pyarrow/) — Parquet is a
binary columnar format, not something the stdlib emits:

```sh
pip install pyarrow
```

Export your memories:

```sh
omi --json memory list > memories.json
```

## The converter

The script lives at [`memories_to_parquet.py`](memories_to_parquet.py) in
this directory.

**Typed schema** — not a stringly-typed dump:

```
id              string
content         string
category        string
tags            list<string>
visibility      string
manually_added  bool
reviewed        bool
app_id          string
created_at      timestamp[ms, UTC]
updated_at      timestamp[ms, UTC]
```

* Timestamps normalize to UTC `timestamp[ms]` — DuckDB/Spark see real
  datetimes, not strings.
* `tags` is a real `list<string>`; `manually_added`/`reviewed` are real
  booleans.
* Multi-page dedupe — each memory ID lands once.

## Usage

```sh
python memories_to_parquet.py memories.json -o memories.parquet
```

## Query it

```sh
# DuckDB
duckdb -c "SELECT category, COUNT(*) FROM 'memories.parquet' GROUP BY 1 ORDER BY 2 DESC"
```

```python
# Polars
import polars as pl
df = pl.read_parquet("memories.parquet")
df.group_by("category").len()
```

```python
# Pandas
import pandas as pd
df = pd.read_parquet("memories.parquet")
```

```python
# Spark
df = spark.read.parquet("memories.parquet")
```

## Safety

* `..` in the `-o` path is refused.
* Existing file never overwritten — `.partial` write then atomic rename.
* Malformed JSON or missing input exits `2`.
