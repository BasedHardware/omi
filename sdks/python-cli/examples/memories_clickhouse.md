<content>
# Omi Memories to ClickHouse Analytical Warehouse

This guide demonstrates how to stream your Omi memories to ClickHouse for high-performance temporal analytics, category trend calculation, and large-scale columnar queries.

## Overview

ClickHouse is an open-source column-oriented OLAP database management system that allows generating real-time analytical reports using SQL queries at high speed. By storing your memories in ClickHouse, you can:

- Perform fast temporal analytics on your thoughts and insights
- Calculate trends across categories over time
- Run complex analytical queries on large datasets
- Use ClickHouse's materialized views for real-time aggregations

## Prerequisites

1. ClickHouse server installed and running
2. Python 3.6+
3. Omi memories exported as JSON files

## Setup

### 1. Create the ClickHouse Table

Use the provided script to generate the DDL for the memories table:

```bash
python memories_to_clickhouse.py /path/to/your/memories --dry-run
```

This will output the CREATE TABLE statement. Execute it in your ClickHouse client:

```sql
CREATE TABLE IF NOT EXISTS omi.memories
(
    id String,
    title String,
    content String,
    category Enum('work' = 'work', 'personal' = 'personal', 'learning' = 'learning', 'uncategorized' = 'uncategorized'),
    created_at DateTime,
    updated_at DateTime,
    tags Array(String),
    metadata String,
    _source_file String,
    _loaded_at DateTime,
    EVENTTIME DateTime MATERIALIZED updated_at
)
ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY toYYYYMM(created_at)
ORDER BY (id, category, created_at)
SETTINGS index_granularity = 8192;
```

### 2. Stream Data to ClickHouse

#### Option 1: Using INSERT Statements

```bash
python memories_to_clickhouse.py /path/to/your/memories --format insert | clickhouse-client --query "INSERT INTO omi.memories FORMAT TabSeparatedRaw"
```

#### Option 2: Using JSONEachRow (Recommended for large datasets)

```bash
python memories_to_clickhouse.py /path/to/your/memories --format json | curl -X POST --data-binary @- 'http://localhost:8123?query=INSERT INTO omi.memories FORMAT JSONEachRow'
```

## Advanced Usage

### Custom Categories

The script automatically detects categories from your memories. If you have custom categories, you can modify the DDL to include them:

```sql
CREATE TABLE omi.memories
(
    -- ... other fields ...
    category Enum('your_custom_category' = 'your_custom_category', 'another_category' = 'another_category'),
    -- ... other fields ...
)
```

### Partitioning Strategy

The table is partitioned by month (`toYYYYMM(created_at)`). For very large datasets, consider:

- Daily partitioning: `PARTITION BY toYYYYMM(created_at) * 100 + toDayOfMonth(created_at)`
- Hash partitioning: `PARTITION BY hash(category)`

### Materialized Views for Analytics

Create materialized views for pre-aggregated analytics:

```sql
CREATE MATERIALIZED VIEW omi.memories_daily_stats
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(created_at)
ORDER BY (category, toYYYYMMDD(created_at))
AS SELECT
    category,
    toYYYYMMDD(created_at) as date,
    count() as count,
    uniq(id) as unique_memories
FROM omi.memories
GROUP BY category, toYYYYMMDD(created_at);
```

## Analytical Queries

### Memory Count by Category

```sql
SELECT
    category,
    count() as total_memories
FROM omi.memories
GROUP BY category
ORDER BY total_memories DESC;
```

### Monthly Trends

```sql
SELECT
    toStartOfMonth(created_at) as month,
    category,
    count() as memory_count
FROM omi.memories
GROUP BY month, category
ORDER BY month, category;
```

### Tag Analysis

```sql
SELECT
    tag,
    count() as frequency
FROM omi.memories
ARRAY JOIN tags as tag
GROUP BY tag
ORDER BY frequency DESC
LIMIT 20;
```

### Time-Based Analysis

```sql
SELECT
    category,
    timeGroupInterval(created_at, '1 week') as week,
    count() as memories_created
FROM omi.memories
GROUP BY category, week
ORDER BY week, category;
```

## Performance Optimization

1. **Indexing**: The table is ordered by `(id, category, created_at)` for optimal query performance
2. **Partitions**: Monthly partitions improve query performance for time-based analysis
3. **Compression**: ClickHouse uses LZ4 compression by default
4. **Sampling**: For large datasets, consider using sampling:

```sql
SELECT *
FROM omi.memories
SAMPLE 0.1  -- Sample 10% of data
WHERE category = 'learning';
```

## Integration with Omi CLI

You can automate the streaming process by adding it to your Omi workflow:

```bash
#!/bin/bash
# sync_memories.sh

# Export memories from Omi
omi export /path/to/memories

# Stream to ClickHouse
python memories_to_clickhouse.py /path/to/memories --format json | \
  curl -X POST --data-binary @- 'http://localhost:8123?query=INSERT INTO omi.memories FORMAT JSONEachRow'
```

Make this script executable and run it periodically to keep your ClickHouse warehouse updated.

## Troubleshooting

### Connection Issues

If you can't connect to ClickHouse:

1. Verify the server is running: `clickhouse-client --query "SELECT 1"`
2. Check the host and port configuration
3. Verify network connectivity

### Data Format Issues

If you encounter JSON parsing errors:

1. Ensure your memory files are valid JSON
2. Check for special characters in your content
3. Use the `--dry-run` option to inspect the data before streaming

### Performance Issues

For slow imports:

1. Use JSONEachRow format instead of INSERT statements
2. Increase `index_granularity` in the table settings
3. Consider batching multiple records in a single request

## References

- [ClickHouse Documentation](https://clickhouse.com/docs/)
- [ClickHouse SQL Syntax](https://clickhouse.com/docs/en/sql-reference/)
- [ClickHouse Performance Best Practices](https://clickhouse.com/docs/en/operations/optimize/)
</content>