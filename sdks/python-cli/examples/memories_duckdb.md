# Analyze memories with DuckDB (embedded OLAP SQL)

Use this recipe to export Omi memories into an optimized SQL script for ingestion and
lightning-fast OLAP analytical queries in [DuckDB](https://duckdb.org/).

DuckDB is the premier in-process analytical SQL database (the "SQLite for Analytics").
This recipe creates strongly typed schemas with native array columns (`VARCHAR[]`),
visibility attributes, and `TIMESTAMPTZ` timestamp support, allowing unnesting tags
and running analytical aggregations offline.

The companion script [`memories_to_duckdb.py`](memories_to_duckdb.py) runs on Python
3.10+ using only standard library modules (`argparse`, `json`, `sys`, `pathlib`).

## 1. Export memories from Omi

Export memories from your device or account:

```sh
omi --json memory list --limit 100 > memories.json
```

Or pipe directly from `omi-cli`:

```sh
omi --json memory list --limit 100 | python memories_to_duckdb.py - -o memories.sql
```

## 2. Convert to DuckDB SQL script

Run the converter script:

```sh
python memories_to_duckdb.py memories.json -o memories.sql
```

### Custom table name

Specify a custom table name if you are maintaining multiple datasets:

```sh
python memories_to_duckdb.py memories.json -o memories.sql --table-name work_memories
```

### Combining multiple exports

Merge multiple export files into one script with deduplication by memory ID:

```sh
python memories_to_duckdb.py day1.json day2.json -o memories.sql --force
```

## 3. Load and query in DuckDB

Run the script directly into a persistent DuckDB database file using the DuckDB CLI:

```sh
duckdb memories.duckdb < memories.sql
```

Or query in-memory without saving to disk:

```sh
duckdb -c ".read memories.sql" -c "SELECT category, COUNT(*) as count FROM memories GROUP BY category ORDER BY count DESC;"
```

### Analytical SQL examples

#### Most frequent tags (using DuckDB unnest):

```sql
SELECT tag, COUNT(*) AS count
FROM (SELECT UNNEST(tags) AS tag FROM memories)
GROUP BY tag
ORDER BY count DESC
LIMIT 10;
```

#### Memory creation volume over time:

```sql
SELECT DATE_TRUNC('month', created_at) AS month, COUNT(*) AS count
FROM memories
GROUP BY month
ORDER BY month DESC;
```

## Converter options

| Option | Description | Default |
| :--- | :--- | :--- |
| `INPUT ...` | One or more JSON files, or `-` for stdin | *(required)* |
| `-o`, `--output` | Destination `.sql` file | *(required)* |
| `--table-name` | Target DuckDB table name | `memories` |
| `-f`, `--force` | Overwrite destination file if it exists | `False` |

## Verification

Run the automated test suite:

```sh
python sdks/python-cli/tests/test_memories_to_duckdb.py
```
