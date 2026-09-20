# Convert a goal-list export to SQLite

Use this recipe to store, query, and analyze your Omi tracked goals in a local
SQLite database. It reads saved JSON exports, makes no network requests,
computes completion percentages, and normalises timestamps to UTC text so SQLite
date and time functions work seamlessly.

You need Python 3.10+ and an authenticated `omi-cli` for the initial export. The `python -m sqlite3` interactive shell examples below require Python 3.12+.

Export tracked goals:

```sh
omi --json goal list --limit 100 > goals.json
```

Run the loader:

```sh
python goals_to_sqlite.py goals.sqlite goals.json
```

Query the database. Find all active goals ordered by progress:

```sh
python -m sqlite3 goals.sqlite "SELECT title, current_value, target_value, unit, progress_pct FROM goals WHERE is_active = 1 ORDER BY progress_pct DESC"
```

Average progress across goals:

```sh
python -m sqlite3 goals.sqlite "SELECT ROUND(AVG(progress_pct), 1) AS avg_progress FROM goals WHERE is_active = 1 AND progress_pct IS NOT NULL"
```

Count goals by type:

```sh
python -m sqlite3 goals.sqlite "SELECT goal_type, COUNT(*) AS count FROM goals GROUP BY goal_type"
```

`created_at` and `updated_at` are stored as UTC `YYYY-MM-DD HH:MM:SS` text, and
`raw_json` preserves the complete original payload for `json_extract`. Loading
is idempotent via `INSERT OR REPLACE`, so re-running on new exports updates
existing rows without creating duplicates.
