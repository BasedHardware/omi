```markdown
# Conversions to Apache Parquet

This guide demonstrates how to convert conversations to an Apache Parquet dataset using the `conversations_to_parquet.py` CLI script.

## Quickstart

### Using DuckDB

```bash
# Install dependencies
pip install duckdb

# Convert conversations to Parquet
python sdks/python-cli/examples/conversations_to_parquet.py conversations.json conversations.parquet

# Query with DuckDB
duckdb "
    SELECT conversation_id, role, content
    FROM 'conversations.parquet'
    WHERE role = 'user'
    LIMIT 5
"
```

### Using Polars

```bash
# Install dependencies
pip install polars

# Convert conversations to Parquet
python sdks/python-cli/examples/conversations_to_parquet.py conversations.json conversations.parquet

# Read with Polars
import polars as pl

df = pl.read_parquet("conversations.parquet")
print(df.head())
```

### Using Pandas

```bash
# Install dependencies
pip install pandas pyarrow

# Convert conversations to Parquet
python sdks/python-cli/examples/conversations_to_parquet.py conversations.json conversations.parquet

# Read with Pandas
import pandas as pd

df = pd.read_parquet("conversations.parquet")
print(df.head())
```

## Input Format

The input JSON file should be a list of conversation objects, each containing:

```json
[
  {
    "id": "conversation_1",
    "messages": [
      {
        "role": "user",
        "content": "Hello",
        "timestamp": "2023-01-01T00:00:00Z"
      },
      {
        "role": "assistant",
        "content": "Hi there!",
        "timestamp": "2023-01-01T00:00:01Z"
      }
    ]
  }
]
```

## Output Format

The output Parquet file will contain the following columns:

- `conversation_id`: ID of the conversation
- `role`: Role of the message author (user/assistant)
- `content`: Message content
- `timestamp`: Message timestamp