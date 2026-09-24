# Store Omi Desktop local tasks in SQLite database

Use this recipe to import and sync Omi Desktop local tasks (`omi local task`)
into a local SQLite database for offline SQL queries, task status tracking, and
relational analytics. It reads JSON exports from `omi-cli`, makes no network requests,
and creates indexed tables for fast task querying.

The companion script [`local_tasks_to_sqlite.py`](local_tasks_to_sqlite.py) runs on Python
3.10+ using only standard library modules (`sqlite3`, `json`, `argparse`).

## 1. Export local tasks from Omi Desktop

Export open and completed local tasks:

```sh
omi --json local task search "" --include-completed > tasks.json
```

Or search for tasks matching a specific topic:

```sh
omi --json local task search "meeting" > meeting_tasks.json
```

## 2. Import into SQLite database

Run the converter to populate or update your SQLite database:

```sh
python local_tasks_to_sqlite.py tasks.json -o tasks.db
```

Or pipe directly from `omi-cli`:

```sh
omi --json local task search "" --include-completed | python local_tasks_to_sqlite.py - -o tasks.db
```

### Merging multiple exports

Re-running the converter with new files or piped exports merges records idempotently using
the task ID, updating completion status and timestamps without creating duplicates:

```sh
python local_tasks_to_sqlite.py day1.json day2.json -o tasks.db
```

## 3. Query your tasks with SQL

Open the database using the standard SQLite CLI or any database viewer:

```sh
# View open tasks ordered by due date
sqlite3 tasks.db "SELECT id, title, due_at FROM local_tasks WHERE completed = 0 ORDER BY due_at ASC;"

# Task completion stats by category
sqlite3 tasks.db "SELECT category, COUNT(*) as total, SUM(completed) as completed FROM local_tasks GROUP BY category;"
```

## Converter options

| Option | Description | Default |
| :--- | :--- | :--- |
| `inputs` | One or more JSON files, or `-` for stdin | `-` |
| `-o`, `--output` | Destination SQLite database file path (required) | none |
| `-f`, `--force` | Recreate database from scratch if it already exists | `false` |

## Database schema

The converter initializes the `local_tasks` table and supporting indexes:

```sql
CREATE TABLE IF NOT EXISTS local_tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    completed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT,
    updated_at TEXT,
    due_at TEXT,
    category TEXT,
    raw_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_local_tasks_completed ON local_tasks(completed);
CREATE INDEX IF NOT EXISTS idx_local_tasks_due_at ON local_tasks(due_at);
CREATE INDEX IF NOT EXISTS idx_local_tasks_category ON local_tasks(category);
```
