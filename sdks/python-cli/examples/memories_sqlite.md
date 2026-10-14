# Convert a memory export to SQLite

Use this recipe to store, query, and search your Omi memories and facts in a
local SQLite database. It reads saved JSON exports, makes no network requests,
and normalises timestamps to UTC text so SQLite date and time functions work
seamlessly. You need Python 3.10+ and an authenticated `omi-cli` for the
initial export.

Export up to 200 memories:

```sh
omi --json memory list --limit 200 --offset 0 > memories_0.json
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account backup. To retrieve another page, increase `--offset`
by 200 and use a different filename. Changes to the account between requests
can affect offset pagination; this recipe does not promise a consistent
snapshot.

Save the following as `memories_to_sqlite.py`:

```python
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_SQLITE_MAGIC = b"SQLite format 3\x00"

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    category TEXT,
    visibility TEXT,
    reviewed INTEGER,
    created_at TEXT,
    updated_at TEXT,
    raw_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS memories_category ON memories (category);
CREATE INDEX IF NOT EXISTS memories_created_at ON memories (created_at);
CREATE INDEX IF NOT EXISTS memories_visibility ON memories (visibility);
"""


def validate_db_path(db_path: str) -> None:
    """Raise ValueError if *db_path* is unsafe or points at a non-SQLite file.

    Rules enforced:
    - The path must not contain '..' components (prevents directory traversal).
    - If the file already exists it must be a valid SQLite database (magic-byte
      check), so we never silently corrupt an unrelated file.
    """
    p = Path(db_path)
    if ".." in p.parts:
        raise ValueError(
            f"Output path {db_path!r} contains '..'; refusing to write outside the intended directory."
        )
    if p.exists():
        try:
            with p.open("rb") as fh:
                header = fh.read(len(_SQLITE_MAGIC))
        except OSError as exc:
            raise ValueError(f"Cannot read existing file {db_path!r}") from exc
        if header != _SQLITE_MAGIC:
            raise ValueError(
                f"{db_path!r} already exists but is not a SQLite database; refusing to overwrite it."
            )


def strip_surrogates(value: str) -> str:
    """Drop unpaired surrogate code points that cannot be encoded as UTF-8."""
    return value.encode("utf-8", "ignore").decode("utf-8")


def text(value):
    """Store loosely typed API fields as text; anything non-null is coerced, not rejected."""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    elif not isinstance(value, str):
        value = str(value)
    return strip_surrogates(value)


def utc_stamp(value):
    """Normalise an ISO-8601 timestamp to UTC 'YYYY-MM-DD HH:MM:SS' so SQLite date functions work."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


TRUE_WORDS = {"true", "1", "yes", "reviewed"}


def reviewed_to_int(value):
    """Normalize the reviewed flag to integer 0 or 1 for SQLite; None stays NULL."""
    if value is None:
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 1 if value else 0
    if isinstance(value, str):
        return 1 if value.strip().lower() in TRUE_WORDS else 0
    return 0


def rows_from(source):
    if source == "-":
        content = sys.stdin.read()
    else:
        content = Path(source).read_bytes().decode("utf-8-sig")
    items = json.loads(content)
    if isinstance(items, dict):
        # An empty list is falsy, so an `or` chain would mistake
        # {"memories": []} for an absent key and treat the wrapper
        # itself as a memory. Match the first key that actually
        # holds a list, in documented wrapper precedence order.
        for key in ("memories", "items", "data", "results"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]
    if not isinstance(items, list):
        raise ValueError(f"{source}: expected a JSON array or object containing memories")
    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source}: each memory must be an object")
        item_id = item.get("id")
        if item_id is None or str(item_id).strip() == "":
            raise ValueError(f"{source}: memory is missing an id")
        content = item.get("content") or item.get("text") or item.get("memory") or ""
        rows.append((
            strip_surrogates(str(item_id)),
            text(content),
            text(item.get("category")),
            text(item.get("visibility")),
            reviewed_to_int(item.get("reviewed")),
            utc_stamp(item.get("created_at")),
            utc_stamp(item.get("updated_at")),
            strip_surrogates(json.dumps(item, ensure_ascii=False))
        ))
    return rows


def load(database, sources):
    """Load memories from one or more JSON exports into a SQLite database."""
    validate_db_path(database)
    # Parse every file before opening the database, so a bad export changes nothing.
    rows = [row for source in sources for row in rows_from(source)]
    connection = sqlite3.connect(database)
    try:
        connection.executescript(SCHEMA)
        before = connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        with connection:  # one transaction: all rows land, or none do
            connection.executemany(
                "INSERT OR REPLACE INTO memories VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        after = connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    finally:
        connection.close()
    return len(rows), after - before, after


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: python memories_to_sqlite.py DATABASE.sqlite INPUT.json [INPUT.json ...] (use - for stdin)")
    try:
        loaded, added, total = load(sys.argv[1], sys.argv[2:])
    except (OSError, ValueError, sqlite3.Error) as exc:
        sys.exit(f"SQLite load failed: {exc}")
    print(f"{loaded} row(s) loaded, {added} new, {loaded - added} updated, {total} memor(y/ies) in database")
```

Load the exported pages (repeat with new exports at any time), or pipe a fresh
export straight from the CLI using `-`:

```sh
python memories_to_sqlite.py memories.sqlite memories_0.json memories_200.json
# or stream directly:
omi --json memory list --limit 200 | python memories_to_sqlite.py memories.sqlite -
```

Query the database. Count memories by category:

```sh
python -m sqlite3 memories.sqlite "SELECT category, COUNT(*) AS count FROM memories GROUP BY category ORDER BY count DESC"
```

Find memories, newest first:

```sh
python -m sqlite3 memories.sqlite "SELECT id, content, created_at FROM memories ORDER BY created_at DESC"
```

Search memories by keyword:

```sh
python -m sqlite3 memories.sqlite "SELECT content, category FROM memories WHERE content LIKE '%prefer%' ORDER BY created_at DESC"
```

`created_at` and `updated_at` are stored as UTC `YYYY-MM-DD HH:MM:SS` text, so
they sort chronologically and work with SQLite's `date()`, `datetime()`, and
`strftime()`. `reviewed` is stored as `0` or `1` (NULL when the source field is
absent) with an index on `category` and `visibility` for fast filtering. Every
original object is preserved verbatim in `raw_json` for `json_extract`. The
output path must not contain `..` (preventing directory traversal), and an
existing non-SQLite file is never overwritten. The loader validates every input
file before writing, applies each run as a single transaction, and replaces rows
that share an `id`, so loading the same page twice leaves exactly one row per
memory. A recognised wrapper (`memories`, `items`, `data`, or `results`) holding
an empty list imports zero rows, so empty export pages import cleanly alongside
populated ones. Passing `-` as an input reads the export from stdin, which makes
the `omi --json … | python …` pipeline work without a temporary file.
