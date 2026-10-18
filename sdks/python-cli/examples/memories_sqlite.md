# Import a memory-list export into SQLite

Use this recipe to query, report on, or search memories offline with SQL. It
reads saved JSON exports, makes no network requests, and builds a local
database that tolerates multi-page merges. You need Python 3.10+ and an
authenticated `omi-cli` for the initial export.

## Paginate the export

`omi memory list` returns one page at a time. Export each page with a
different filename — feed all pages to the converter in one run:

```sh
omi --json memory list --limit 200 --offset 0   > memories_p1.json
omi --json memory list --limit 200 --offset 200 > memories_p2.json
```

Check that each command succeeded before converting. Changes to the account
between requests can affect offset pagination; this recipe does not promise a
consistent snapshot.

## The converter

The script lives at [`memories_to_sqlite.py`](memories_to_sqlite.py) in this
directory — stdlib-only (`sqlite3`, `json`, `sys`, `pathlib`, `datetime`).

**Schema** (`users/{uid}`-scoped fields flattened; raw JSON preserved):

```sql
memories(id PRIMARY KEY, content, category, tags, visibility,
         manually_added, app_id, created_at, updated_at, raw_json)
```

Indexed on `category`, `created_at`, and `manually_added`. `tags` joins the
export's array with `|`; `manually_added` coerces to `0`/`1`; timestamps
normalize to UTC `YYYY-MM-DD HH:MM:SS` text so `strftime`/`julianday` work
natively; `raw_json` keeps the untouched record for fields the columns drop.

## Usage

```sh
python memories_to_sqlite.py memories_p1.json memories_p2.json -o memories.db
```

Each run is **idempotent**: re-importing the same page updates existing rows
(`INSERT OR REPLACE` keyed on `id`) and never duplicates them — safe to
re-run after a partial export or to fold new pages into an existing DB.

## Example queries

```sql
-- memories per category
SELECT category, COUNT(*) FROM memories GROUP BY category ORDER BY 2 DESC;

-- memories added this week
SELECT content FROM memories
 WHERE created_at >= strftime('%Y-%m-%d %H:%M:%S', 'now', '-7 days');

-- hand-typed (not imported) memories
SELECT content FROM memories WHERE manually_added = 1;

-- full-text search over the raw JSON
SELECT id, content FROM memories WHERE raw_json LIKE '%standup%';
```

## Safety

* `..` in the `-o` path is refused.
* An existing non-SQLite file is never overwritten (magic-byte check).
* A malformed input page aborts before the DB is touched — a bad export
  can't corrupt the database.
