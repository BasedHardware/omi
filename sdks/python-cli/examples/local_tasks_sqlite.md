# Store Omi Desktop local tasks in SQLite database

Use this recipe to import and sync Omi Desktop local tasks
into a local SQLite database for offline SQL queries, task status tracking, and
relational analytics. It reads JSON or search exports from `omi-cli`, makes no network requests,
and creates indexed tables for fast task querying.

The companion script [`local_tasks_to_sqlite.py`](local_tasks_to_sqlite.py) runs on Python
3.10+ using only standard library modules (`sqlite3`, `json`, `re`, `hashlib`, `argparse`).

## 1. Export local tasks from Omi Desktop

### Method A: Full snapshot via Desktop SQL (Recommended)

Export all open and completed tasks directly from the Desktop SQLite store (`action_items` table):

```sh
omi --json local sql "SELECT id, description, completed, created_at, due_at FROM action_items WHERE deleted = 0" > tasks.json
```

> **Note on Desktop Action Items Schema**:
> - Tasks are stored in the `action_items` table (where `deleted = 0`).
> - **Windows Desktop**: Timestamp columns use snake_case (`created_at`, `due_at`):
>   `omi --json local sql "SELECT id, description, completed, created_at, due_at FROM action_items WHERE deleted = 0" > tasks.json`
> - **macOS Desktop**: Timestamp columns use camelCase (`createdAt`, `dueAt`):
>   `omi --json local sql "SELECT id, description, completed, createdAt AS created_at, dueAt AS due_at FROM action_items WHERE deleted = 0" > tasks.json`
> - **Cross-Platform Core**: `SELECT id, description, completed FROM action_items WHERE deleted = 0` works identically across all desktop platforms. The converter automatically maps `description` to `title` and natively recognizes both camelCase (`createdAt`/`dueAt`) and snake_case (`created_at`/`due_at`) timestamps.

### Method B: Semantic task search

Export tasks relevant to a specific topic or keyword:

```sh
omi --json local task search "meeting" --include-completed > meeting_tasks.json
```

> **Note on Task Search**: `omi local task search` performs semantic similarity matching and returns up to 10 top results formatted as checklist items with similarity scores and IDs (e.g. `1. [x] Review spec [high] (similarity: 0.91, id: abc, source: action_items)`). The converter natively parses both structured JSON arrays from SQL exports and search text output. Priority tags (e.g. `[high]`, `[medium]`) are cleanly extracted into record metadata without cluttering task titles. When IDs are omitted, deterministic SHA-256 hashes are derived from task descriptions to prevent collisions across imports.

## 2. Import into SQLite database

Run the converter to populate or update your SQLite database:

```sh
python local_tasks_to_sqlite.py tasks.json -o tasks.db
```

Or pipe directly from `omi-cli`:

```sh
omi --json local sql "SELECT id, description, completed FROM action_items WHERE deleted = 0" | python local_tasks_to_sqlite.py - -o tasks.db
```

Or pipe semantic search results:

```sh
omi --json local task search "meeting" --include-completed | python local_tasks_to_sqlite.py - -o tasks.db
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
| `inputs` | One or more JSON or search text files, or `-` for stdin | `-` |
| `-o`, `--output` | Destination SQLite database file path (required) | none |
| `-f`, `--force` | Recreate database from scratch if it already exists | `false` |

## Database schema

The script creates the `local_tasks` table with the following schema:

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
```

Indexes are automatically created on `completed`, `due_at`, and `category` for fast filtering.
