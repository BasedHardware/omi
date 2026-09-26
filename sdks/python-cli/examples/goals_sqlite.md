# Export Omi Goals to a Local SQLite Database

Use this recipe to export and query your Omi goals in a local, self-contained SQLite database. It reads a saved JSON export or stdin stream, creates an indexed SQLite database, stores numerical metrics as SQLite `REAL` types, normalizes timestamps to UTC `YYYY-MM-DD HH:MM:SS`, and preserves full raw JSON payloads for lossless `json_extract` queries.

You need Python 3.10+ and an authenticated `omi-cli`.

---

## 1. Export Goals from Omi CLI

Export up to 100 goals (including completed/inactive goals):

```sh
omi --json goal list --limit 100 --include-inactive > goals.json
```

Or stream directly to the converter via standard input:

```sh
omi --json goal list --limit 100 --include-inactive | python goals_to_sqlite.py - goals.db
```

---

## 2. Converter Script (`goals_to_sqlite.py`)

The companion script [`goals_to_sqlite.py`](goals_to_sqlite.py) is located in this directory.

### Run the Converter:

```sh
python goals_to_sqlite.py goals.json goals.db
```

---

## 3. Database Schema

The script creates an indexed table `goals` with WAL mode enabled:

```sql
CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    goal_type TEXT,
    target_value REAL,
    current_value REAL,
    min_value REAL,
    max_value REAL,
    unit TEXT,
    is_active INTEGER NOT NULL,
    created_at TEXT,
    updated_at TEXT,
    raw_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_goals_is_active ON goals(is_active);
CREATE INDEX IF NOT EXISTS idx_goals_goal_type ON goals(goal_type);
```

---

## 4. Useful SQL Queries

Open the database using `sqlite3`:

```sh
sqlite3 goals.db
```

### View All Active Goals and Progress Percentage

```sql
SELECT
    id,
    title,
    goal_type,
    current_value,
    target_value,
    unit,
    CASE
        WHEN target_value IS NOT NULL AND target_value > 0
        THEN ROUND((current_value / target_value) * 100.0, 1)
        ELSE NULL
    END AS progress_pct
FROM goals
WHERE is_active = 1;
```

### Find Completed or Inactive Goals

```sql
SELECT id, title, goal_type, updated_at
FROM goals
WHERE is_active = 0
ORDER BY updated_at DESC;
```

### Query Custom JSON Fields using `json_extract`

```sql
SELECT
    id,
    title,
    json_extract(raw_json, '$.category') AS category
FROM goals
WHERE json_extract(raw_json, '$.category') IS NOT NULL;
```

### Goals Grouped by Goal Type

```sql
SELECT
    COALESCE(goal_type, 'qualitative') AS type,
    COUNT(*) AS total_count,
    SUM(is_active) AS active_count
FROM goals
GROUP BY goal_type;
```

---

## 5. Python Interactive Query Example

You can easily query your exported goals in Python:

```python
import sqlite3

conn = sqlite3.connect("goals.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

for row in cursor.execute("SELECT title, current_value, target_value, unit FROM goals WHERE is_active = 1"):
    unit = f" {row['unit']}" if row['unit'] else ""
    target = f" / {row['target_value']}" if row['target_value'] is not None else ""
    current = row['current_value'] if row['current_value'] is not None else "Active"
    print(f"• {row['title']}: {current}{target}{unit}")

conn.close()
```
