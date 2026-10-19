"""Import Omi memories JSON exports into a SQLite database for SQL queries.

Usage:
    # Basic import from saved JSON export
    python memories_to_sqlite.py memories.sqlite memories.json

    # Import multiple pages or files
    python memories_to_sqlite.py memories.sqlite page1.json page2.json

    # Import pipeline stream from omi CLI
    omi --json memory list --limit 200 | python memories_to_sqlite.py memories.sqlite -
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

_SQLITE_MAGIC = b"SQLite format 3\x00"

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    category TEXT,
    tags TEXT,
    visibility TEXT,
    created_at TEXT,
    updated_at TEXT,
    app_id TEXT,
    raw_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS memories_category ON memories (category);
CREATE INDEX IF NOT EXISTS memories_created_at ON memories (created_at);
CREATE INDEX IF NOT EXISTS memories_visibility ON memories (visibility);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    id UNINDEXED,
    content,
    tags,
    category
);

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    DELETE FROM memories_fts WHERE id = new.id;
    INSERT INTO memories_fts(id, content, tags, category)
    VALUES (new.id, new.content, new.tags, new.category);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    DELETE FROM memories_fts WHERE id = old.id;
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    DELETE FROM memories_fts WHERE id = old.id;
    INSERT INTO memories_fts(id, content, tags, category)
    VALUES (new.id, new.content, new.tags, new.category);
END;
"""


def validate_db_path(db_path: str) -> None:
    """Raise ValueError if *db_path* is unsafe or points at a non-SQLite file.

    Rules enforced:
    - The path must not contain '..' components (prevents directory traversal).
    - If the file already exists it must be a valid SQLite database (magic-byte check).
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


def text(value: Any) -> Optional[str]:
    """Store loosely typed API fields as text; anything non-null is coerced, not rejected."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)


def tags_text(value: Any) -> Optional[str]:
    """Convert a tags list or value to a comma-separated string."""
    if value is None:
        return None
    if isinstance(value, list):
        clean_tags = [str(t).strip() for t in value if t is not None and str(t).strip()]
        return ",".join(clean_tags) if clean_tags else None
    if isinstance(value, str):
        return value.strip() if value.strip() else None
    return str(value)


def utc_stamp(value: Any) -> Optional[str]:
    """Normalise an ISO-8601 timestamp to UTC 'YYYY-MM-DD HH:MM:SS' text.

    Returns None for None/empty so SQLite NULL is used instead of a string,
    keeping date functions (strftime, julianday) working without coercion.
    Naive datetimes are assumed to be in UTC.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OverflowError):
        return None


def rows_from(source: str) -> List[Tuple[Any, ...]]:
    """Parse one file or stdin into rows ready for database insertion."""
    if source == "-":
        content = sys.stdin.buffer.read()
        source_label = "stdin"
    else:
        source_label = source
        content = Path(source).read_bytes()

    if not content.strip():
        return []

    raw = json.loads(content.decode("utf-8-sig"))
    if isinstance(raw, dict):
        for key in ("memories", "items", "data", "results"):
            if isinstance(raw.get(key), list):
                items = raw[key]
                break
        else:
            items = [raw]
    elif isinstance(raw, list):
        items = raw
    else:
        raise ValueError(f"{source_label}: expected a JSON array or object containing memories")

    rows = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"{source_label} item {idx}: each memory must be an object")

        item_id = item.get("id")
        if item_id is None or not str(item_id).strip():
            raise ValueError(f"{source_label} item {idx}: memory is missing a non-empty 'id'")
        clean_id = str(item_id).strip()

        content_text = item.get("content") or ""
        app_id = item.get("app_id") or item.get("source_app")

        rows.append((
            clean_id,
            str(content_text),
            text(item.get("category")),
            tags_text(item.get("tags")),
            text(item.get("visibility")),
            utc_stamp(item.get("created_at")),
            utc_stamp(item.get("updated_at")),
            text(app_id),
            json.dumps(item, ensure_ascii=False),
        ))
    return rows


def load(database: str, sources: Sequence[str]) -> Tuple[int, int, int]:
    """Load memories from one or more JSON exports into a SQLite database.

    Returns:
        (total_rows_processed, new_rows_added, total_rows_in_table)
    """
    validate_db_path(database)
    # Parse every source before opening the database so bad exports make no changes
    rows = [row for source in sources for row in rows_from(source)]

    dest_path = Path(database)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database)
    try:
        connection.executescript(SCHEMA)
        before = connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        with connection:
            connection.executemany(
                "INSERT OR REPLACE INTO memories VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        after = connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    finally:
        connection.close()

    return len(rows), after - before, after


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if len(argv) < 2:
        print("Usage: python memories_to_sqlite.py DATABASE.sqlite INPUT.json [INPUT.json ...]", file=sys.stderr)
        return 1

    database = argv[0]
    sources = argv[1:]

    try:
        loaded, added, total = load(database, sources)
        print(f"{loaded} row(s) loaded, {added} new, {loaded - added} updated, {total} memory item(s) in database")
        return 0
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"SQLite load failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
