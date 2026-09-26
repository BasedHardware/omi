# Store and search memories with Redis Stack (RedisJSON + RediSearch)

Use this recipe to export Omi memories into [Redis Stack](https://redis.io/) (Redis with JSON and RediSearch modules) for high-performance in-memory caching, document storage, and real-time secondary search.

Redis Stack allows storing documents as native JSON structures with `JSON.SET` and performing full-text and tag searches across memories using `FT.SEARCH`.

The companion script [`memories_to_redis.py`](memories_to_redis.py) runs on Python 3.10+ using only standard library modules (`argparse`, `json`, `sys`, `pathlib`).

## 1. Export memories from Omi

Export memories from your device or account:

```sh
omi --json memory list --limit 100 > memories.json
```

Or pipe directly from `omi-cli`:

```sh
omi --json memory list --limit 100 | python memories_to_redis.py - -o memories.redis
```

## 2. Convert to Redis commands script

Run the converter script:

```sh
python memories_to_redis.py memories.json -o memories.redis
```

### Custom key prefix

Specify a custom key prefix if you run multiple datasets on the same Redis instance:

```sh
python memories_to_redis.py memories.json -o memories.redis --key-prefix user1:memory:
```

### Combining multiple exports

Merge multiple export files into one script with deduplication by memory ID:

```sh
python memories_to_redis.py day1.json day2.json -o memories.redis --force
```

## 3. Load and query in Redis Stack

### Start Redis Stack

Run Redis Stack via Docker:

```sh
docker run -d --name redis-stack -p 6379:6379 -p 8001:8001 redis/redis-stack:latest
```

### Create the search index

Create the RediSearch index using `redis-cli`:

```sh
redis-cli FT.CREATE idx:memories ON JSON PREFIX 1 "memory:" SCHEMA $.content AS content TEXT $.category AS category TAG $.tags.* AS tags TAG $.visibility AS visibility TAG $.created_at AS created_at TEXT
```

### Ingest documents

Pipe the generated commands directly into `redis-cli`:

```sh
cat memories.redis | redis-cli
```

> **Note**: The generated `.redis` file contains only executable `JSON.SET` commands without comment lines, allowing direct piped ingestion into `redis-cli`. Backslashes in memory content are preserved as literal characters without double-escaping.

### Sample RediSearch queries

Run searches directly via `redis-cli`:

#### 1. Full-text search memory content:

```sh
redis-cli FT.SEARCH idx:memories "meeting"
```

#### 2. Filter by category:

```sh
redis-cli FT.SEARCH idx:memories "@category:{work}"
```

#### 3. Filter by tag:

```sh
redis-cli FT.SEARCH idx:memories "@tags:{project}"
```

#### 4. Combined full-text and tag filter:

```sh
redis-cli FT.SEARCH idx:memories "design @category:{work}"
```

## Converter options

| Option | Description | Default |
| :--- | :--- | :--- |
| `INPUT ...` | One or more JSON files, or `-` for stdin | *(required)* |
| `-o`, `--output` | Destination `.redis` file | *(required)* |
| `--key-prefix` | Key prefix for Redis documents | `memory:` |
| `-f`, `--force` | Overwrite destination file if it exists | `False` |

## Verification

Run the automated test suite (7 unit tests):

```sh
python sdks/python-cli/tests/test_memories_to_redis.py
```
