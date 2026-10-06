# Convert memories export to an Apache Parquet dataset (.parquet)

Use this recipe to convert Omi memories into an **Apache Parquet** columnar dataset.
Parquet provides high-performance columnar storage, efficient Snappy/ZSTD compression,
and native integration with modern analytical and AI tooling such as **DuckDB**,
**Polars**, **Pandas**, and Hugging Face `datasets`.

You need Python 3.10+, an authenticated `omi-cli`, and [`pyarrow`](https://pypi.org/project/pyarrow/):

```sh
pip install pyarrow
```

## Step 1: Export memories

Export up to 200 memories (the maximum page size supported by `memory list`):

```sh
omi --json memory list --limit 200 --offset 0 > memories_0.json
```

Check that the command succeeded before converting the file. This represents one page.
To retrieve subsequent pages, increase `--offset` by 200 and save to a new filename:

```sh
omi --json memory list --limit 200 --offset 200 > memories_200.json
```

## Step 2: Convert to Parquet

Run the converter script [`memories_to_parquet.py`](memories_to_parquet.py) (from `sdks/python-cli/examples/` or using its relative path):

```sh
python sdks/python-cli/examples/memories_to_parquet.py memories_0.json -o memories.parquet
```

To configure compression (e.g. `zstd`, `gzip`, or `snappy`):

```sh
python sdks/python-cli/examples/memories_to_parquet.py memories_0.json -o memories.parquet -c zstd
```

To overwrite an existing dataset:

```sh
python sdks/python-cli/examples/memories_to_parquet.py memories_0.json -o memories.parquet --overwrite
```

Or pipe directly from `omi-cli`:

```sh
omi --json memory list --limit 200 | python sdks/python-cli/examples/memories_to_parquet.py - -o memories.parquet
```

## Schema & Columnar Fields

The dataset schema mirrors `omi_cli.models.Memory` exactly, plus precomputed text dimensions:

| Field | Parquet Type | Description |
|---|---|---|
| `id` | `string` | Unique memory identifier. |
| `content` | `string` | Full memory text content. |
| `category` | `string` | Memory classification (e.g. `work`, `learning`, `personal`). |
| `visibility` | `string` | Visibility tier (`private` or `public`). |
| `tags` | `list<string>` | Associated tags array. |
| `created_at` | `string` | ISO 8601 UTC creation timestamp. |
| `updated_at` | `string` | ISO 8601 UTC update timestamp. |
| `manually_added` | `bool` | True if entered manually by user. |
| `reviewed` | `bool` | True if reviewed by user. |
| `edited` | `bool` | True if modified after creation. |
| `char_len` | `int64` | Total character count of content. |
| `word_count` | `int64` | Total whitespace-separated word count. |

## Querying with DuckDB, Polars, or Pandas

### DuckDB
```sql
SELECT category, count(*), avg(word_count)
FROM 'memories.parquet'
GROUP BY category;
```

### Polars
```python
import polars as pl

df = pl.read_parquet("memories.parquet")
print(df.group_by("category").agg(pl.len(), pl.col("word_count").mean()))
```

### Pandas
```python
import pandas as pd

df = pd.read_parquet("memories.parquet")
print(df.describe())
```

## Security & Reliability Invariants

- **Columnar Integrity**: Strict schema matching `omi_cli.models.Memory` with zero phantom fields.
- **Atomic File Writing**: Generates the dataset to a `.partial` file before atomically renaming via `os.replace`.
- **Path Traversal Protection**: Rejects destination paths containing `..` components.
