```markdown
# Memories to Apache Parquet Dataset

This guide demonstrates how to convert memories data to an Apache Parquet dataset using various Python libraries.

## Prerequisites

Install the required libraries:

```bash
pip install pandas pyarrow
# For DuckDB
pip install duckdb
# For Polars
pip install polars
# For Pandas (already installed with pandas)
```

## Quickstart Examples

### Using DuckDB

```python
import duckdb
import pandas as pd

# Load the Parquet file
df = duckdb.read_parquet("output.parquet")

# Query the data
result = df.execute("SELECT COUNT(*) FROM df").fetchall()
print(f"Total memories: {result[0][0]}")

# Filter memories
memories_with_high_score = df.execute("SELECT * FROM df WHERE score > 0.8").fetchdf()
print(memories_with_high_score)
```

### Using Polars

```python
import polars as pl

# Load the Parquet file
df = pl.read_parquet("output.parquet")

# Query the data
total_memories = df.height
print(f"Total memories: {total_memories}")

# Filter memories
memories_with_high_score = df.filter(pl.col("score") > 0.8)
print(memories_with_high_score)
```

### Using Pandas

```python
import pandas as pd

# Load the Parquet file
df = pd.read_parquet("output.parquet")

# Query the data
total_memories = len(df)
print(f"Total memories: {total_memories}")

# Filter memories
memories_with_high_score = df[df["score"] > 0.8]
print(memories_with_high_score)
```

## Command Line Usage

Convert memories JSON files to a Parquet dataset:

```bash
python memories_to_parquet.py input1.json input2.json -o output.parquet
```

This will combine all memories from the input JSON files and save them as a single Parquet file.
```