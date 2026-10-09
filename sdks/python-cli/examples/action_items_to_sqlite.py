import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_SQLITE_MAGIC = b"SQLite format 3\x00"

SCHEMA = """
CREATE TABLE IF NOT EXISTS action_items (
    id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    completed INTEGER NOT NULL,
    due_at TEXT,
    created_at TEXT,
    updated_at TEXT,
    conversation_id TEXT,
    raw_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS action_items_completed ON action_items (completed);
CREATE INDEX IF NOT EXISTS action_items_created_at ON action_items (created_at);
CREATE INDEX IF NOT EXISTS action_items_conversation_id ON action_items (conversation_id);
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
    """Drop unpaired surrogate code points that cannot be encoded as UTF-8.

    json.loads accepts lone surrogates (e.g. "\\ud800") from a malformed export, but
    both sqlite3 and file writes raise UnicodeEncodeError on them. Dropping them keeps
    the remaining text and lets the row import.
    """
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


DONE_WORDS = {"true", "1", "yes", "done", "completed"}


def boolean_to_int(value):
    """Normalize completed status to integer 0 or 1 for SQLite."""
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 1 if value else 0
    if isinstance(value, str):
        return 1 if value.strip().lower() in DONE_WORDS else 0
    return 0


def rows_from(source):
    content = Path(source).read_bytes().decode("utf-8-sig")
    items = json.loads(content)
    if isinstance(items, dict):
        # An empty list is falsy, so an `or` chain would mistake
        # {"action_items": []} for an absent key and treat the wrapper
        # itself as an action item. Match the first key that actually
        # holds a list, in documented wrapper precedence order.
        for key in ("action_items", "items", "data"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]
    if not isinstance(items, list):
        raise ValueError(f"{source}: expected a JSON array or object containing action items")
    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source}: each action item must be an object")
        item_id = item.get("id")
        if item_id is None or str(item_id).strip() == "":
            raise ValueError(f"{source}: action item is missing an id")
        description = item.get("description")
        if description is None:
            description = item.get("title") or ""
        clean_id = strip_surrogates(str(item_id))
        rows.append((
            clean_id,
            text(description),
            boolean_to_int(item.get("completed")),
            utc_stamp(item.get("due_at")),
            utc_stamp(item.get("created_at")),
            utc_stamp(item.get("updated_at")),
            text(item.get("conversation_id")),
            strip_surrogates(json.dumps(item, ensure_ascii=False))
        ))
    return rows


def load(database, sources):
    """Load action items from one or more JSON exports into a SQLite database."""
    validate_db_path(database)
    # Parse every file before opening the database, so a bad export changes nothing.
    rows = [row for source in sources for row in rows_from(source)]
    connection = sqlite3.connect(database)
    try:
        connection.executescript(SCHEMA)
        before = connection.execute("SELECT COUNT(*) FROM action_items").fetchone()[0]
        with connection:  # one transaction: all rows land, or none do
            connection.executemany(
                "INSERT OR REPLACE INTO action_items VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        after = connection.execute("SELECT COUNT(*) FROM action_items").fetchone()[0]
    finally:
        connection.close()
    return len(rows), after - before, after


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: python action_items_to_sqlite.py DATABASE.sqlite INPUT.json [INPUT.json ...]")
    try:
        loaded, added, total = load(sys.argv[1], sys.argv[2:])
    except (OSError, ValueError, sqlite3.Error) as exc:
        sys.exit(f"SQLite load failed: {exc}")
    print(f"{loaded} row(s) loaded, {added} new, {loaded - added} updated, {total} action item(s) in database")
