# Convert a memory export to SQLite

Use this recipe to store, query, and search your Omi memories and facts in
a local SQLite database. It reads saved JSON exports, makes no network
requests, and normalises timestamps to UTC text so SQLite date and time functions
work seamlessly. You need Python 3.10+ and an authenticated `omi-cli` for the
initial export.

Export memories:

```sh
omi --json memory list --limit 200 --offset 0 > memories_0.json
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account backup. To retrieve another page, increase `--offset`
by 200 and use a different filename.

Save the conversion script as `memories_to_sqlite.py`:

```python
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    category TEXT,
    created_at TEXT,
    updated_at TEXT,
    deleted INTEGER NOT NULL DEFAULT 0,
    conversation_id TEXT,
    raw_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS memories_created_at ON memories (created_at);
CREATE INDEX IF NOT EXISTS memories_category ON memories (category);
CREATE INDEX IF NOT EXISTS memories_deleted ON memories (deleted);
CREATE INDEX IF NOT EXISTS memories_conversation_id ON memories (conversation_id);
"""
```

Load your exported JSON files into `memories.sqlite`:

```sh
python memories_to_sqlite.py memories.sqlite memories_0.json
```

To load multiple export files or page dumps in one pass:

```sh
python memories_to_sqlite.py memories.sqlite memories_0.json memories_1.json
```

The script is idempotent. Running it against overlapping exports will update
modified memories without creating duplicates.

## Example SQL Queries

Open the database using the standard SQLite shell:

```sh
sqlite3 memories.sqlite
```

### 1. Count active memories by category

```sql
SELECT category, COUNT(*) AS count
FROM memories
WHERE deleted = 0
GROUP BY category
ORDER BY count DESC;
```

### 2. Search memories for a specific topic

```sql
SELECT id, category, content, created_at
FROM memories
WHERE deleted = 0
  AND content LIKE '%project%'
ORDER BY created_at DESC;
```

### 3. List recently created memories from the last 7 days

```sql
SELECT id, category, content, created_at
FROM memories
WHERE deleted = 0
  AND created_at >= datetime('now', '-7 days')
ORDER BY created_at DESC;
```
