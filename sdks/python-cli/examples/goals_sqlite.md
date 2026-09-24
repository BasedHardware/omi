# Convert a goals export to SQLite

Use this recipe to store, query, and track your Omi goals, milestones, and OKRs in a local SQLite database. It reads saved JSON exports or piped input via `stdin`, makes no network requests, and normalises timestamps to UTC text so SQLite date and time functions work seamlessly. It also computes normalized progress percentages (`0.0%` to `100.0%`) for metric goals and creates indexes on status, type, and dates for fast querying. You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

## 1. Export your goals

Export your captured goals (up to 200 per page):

```sh
omi --json goal list --limit 200 --offset 0 > goals_0.json
```

Check that the command succeeded before converting the file. If you have more than 200 goals, retrieve subsequent pages into separate files:

```sh
omi --json goal list --limit 200 --offset 200 > goals_200.json
```

## 2. Load into SQLite

Run the companion script [`goals_to_sqlite.py`](goals_to_sqlite.py):

```sh
# Load one or more exported JSON files
python sdks/python-cli/examples/goals_to_sqlite.py goals.sqlite goals_0.json goals_200.json

# Or stream directly via stdin pipeline
omi --json goal list --limit 200 | python sdks/python-cli/examples/goals_to_sqlite.py goals.sqlite -
```

Each run is idempotent: re-importing the same files updates existing rows (`INSERT OR REPLACE` keyed on `id`) and never duplicates them.

## 3. Query the database

Query the database using Python's built-in `sqlite3` CLI or any SQLite browser.

### Summary by status and completion rate

```sh
python -m sqlite3 goals.sqlite "SELECT status, COUNT(*) AS total_goals, ROUND(AVG(progress_percentage), 1) AS avg_progress_pct FROM goals GROUP BY status;"
```

### List all active goals ordered by progress

```sh
python -m sqlite3 goals.sqlite "SELECT id, title, goal_type, current_value || '/' || target_value || ' ' || COALESCE(unit, '') AS metric, progress_percentage || '%' AS progress FROM goals WHERE status = 'active' ORDER BY progress_percentage ASC;"
```

### Distribution by goal type

```sh
python -m sqlite3 goals.sqlite "SELECT goal_type, COUNT(*) AS count FROM goals GROUP BY goal_type ORDER BY count DESC;"
```

### Goals created in the last 30 days

```sh
python -m sqlite3 goals.sqlite "SELECT id, title, status, created_at FROM goals WHERE created_at >= datetime('now', '-30 days') ORDER BY created_at DESC;"
```

### Query raw JSON payloads

Every original API object is preserved verbatim in `raw_json` for `json_extract`:

```sh
python -m sqlite3 goals.sqlite "SELECT id, json_extract(raw_json, '$.target_value') FROM goals WHERE goal_type = 'numeric';"
```

## 4. Database Schema

The database table and indexes are automatically created if they do not exist:

```sql
CREATE TABLE IF NOT EXISTS goals (
    id                  TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    status              TEXT NOT NULL,
    goal_type           TEXT NOT NULL,
    current_value       REAL,
    target_value        REAL,
    min_value           REAL,
    unit                TEXT,
    progress_percentage REAL,
    created_at          TEXT,
    updated_at          TEXT,
    raw_json            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_goals_status ON goals (status);
CREATE INDEX IF NOT EXISTS idx_goals_type ON goals (goal_type);
CREATE INDEX IF NOT EXISTS idx_goals_created_at ON goals (created_at);
```

- `created_at` and `updated_at` are stored as UTC `YYYY-MM-DD HH:MM:SS` text, so they sort chronologically and work with SQLite's `date()`, `datetime()`, and `strftime()`.
- `status` and `goal_type` are indexed for fast filtering across large datasets.
- `progress_percentage` is calculated as a float from `0.0` to `100.0` (or `NULL` for qualitative goals).

## 5. Automated Verification

Run the automated unit test suite with:

```sh
python sdks/python-cli/tests/test_goals_to_sqlite.py
```
