#!/usr/bin/env python3
"""
Convert Omi memory-list JSON exports to a SQLite database with FTS5 full-text search.

Usage:
    # From saved JSON files
    python memories_to_sqlite.py memories.sqlite memories_0.json [memories_1.json ...]

    # From stdin pipeline
    omi --json memory list --limit 200 | python memories_to_sqlite.py memories.sqlite -

Each run is idempotent: re-importing the same page updates existing rows
(INSERT OR REPLACE keyed on id) and keeps the FTS5 search index synchronized.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id          TEXT PRIMARY KEY,
    content     TEXT NOT NULL,
    category    TEXT,
    created_at  TEXT,
    updated_at  TEXT,
    raw_json    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories (category);
CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories (created_at);

CREATE TABLE IF NOT EXISTS memory_tags (
    memory_id   TEXT NOT NULL,
    tag         TEXT NOT NULL,
    PRIMARY KEY (memory_id, tag),
    FOREIGN KEY (memory_id) REFERENCES memories (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_memory_tags_tag ON memory_tags (tag);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    id UNINDEXED,
    content,
    category,
    tags
);
"""


def text(value: Any) -> Optional[str]:
    """Store loosely typed API fields as text; anything non-null is coerced, not rejected."""
    if value is None:
        return None
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def utc_stamp(value: Any) -> Optional[str]:
    """Normalise an ISO-8601 timestamp to UTC 'YYYY-MM-DD HH:MM:SS' text.

    Returns None for None/empty so SQLite NULL is used instead of a string,
    keeping date functions (strftime, julianday) working without coercion.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def rows_from(
    source: str,
) -> Tuple[List[Tuple[str, str, Optional[str], Optional[str], Optional[str], str]], List[Tuple[str, str]], List[Tuple[str, str, str, str]]]:
    """Parse one input source (file path or '-' for stdin).

    Returns:
        (memory_rows, tag_rows, fts_rows)
    """
    if source == "-":
        content = sys.stdin.read()
        display_name = "<stdin>"
    else:
        p = Path(source)
        if not p.is_file():
            raise FileNotFoundError(f"Input file not found: {source}")
        content = p.read_bytes().decode("utf-8-sig")
        display_name = source

    try:
        items = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{display_name}: invalid JSON ({exc})") from exc

    if isinstance(items, dict):
        items = (
            items.get("memories")
            or items.get("items")
            or items.get("data")
            or [items]
        )

    if not isinstance(items, list):
        raise ValueError(f"{display_name}: expected a JSON array or object containing memories")

    memory_rows = []
    tag_rows = []
    fts_rows = []

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"{display_name}[{idx}]: each memory must be a JSON object")
        item_id = item.get("id")
        if item_id is None or str(item_id).strip() == "":
            raise ValueError(f"{display_name}[{idx}]: memory is missing an id")

        m_id = str(item_id).strip()
        body = text(item.get("content") or item.get("text") or item.get("memory") or "(empty memory)") or ""
        cat = text(item.get("category") or "general")
        created_at = utc_stamp(item.get("created_at"))
        updated_at = utc_stamp(item.get("updated_at"))
        raw_json = json.dumps(item, ensure_ascii=False)

        memory_rows.append((m_id, body, cat, created_at, updated_at, raw_json))

        # Tags extraction
        raw_tags = item.get("tags") or []
        tag_list: List[str] = []
        if isinstance(raw_tags, list):
            for t in raw_tags:
                clean_tag = text(t)
                if clean_tag:
                    clean_tag = clean_tag.lstrip("#")
                    tag_list.append(clean_tag)
                    tag_rows.append((m_id, clean_tag))

        tags_joined = " ".join(tag_list)
        fts_rows.append((m_id, body, cat or "", tags_joined))

    return memory_rows, tag_rows, fts_rows


def load(database: str, sources: List[str]) -> Tuple[int, int, int]:
    """Load memories from one or more JSON exports into a SQLite database with FTS5 search.

    Deduplicates entries across the given sources by memory ID, keeping the
    most recent entry when identical IDs are encountered.

    Returns:
        (loaded_count, added_count, total_count)
    """
    latest_memories: Dict[str, Tuple[str, str, Optional[str], Optional[str], Optional[str], str]] = {}
    latest_tags: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    latest_fts: Dict[str, Tuple[str, str, str, str]] = {}

    total_parsed = 0

    # Parse every file before touching the database
    for src in sources:
        m_rows, t_rows, f_rows = rows_from(src)
        total_parsed += len(m_rows)

        src_seen_ids = set()
        for r in m_rows:
            mid = r[0]
            latest_memories[mid] = r
            src_seen_ids.add(mid)
            # Reset tags for this ID so earlier source tags are overwritten
            latest_tags[mid] = []

        for mid, tag in t_rows:
            latest_tags[mid].append((mid, tag))

        for r in f_rows:
            latest_fts[r[0]] = r

    final_memories = list(latest_memories.values())
    final_tags = [t for tags_for_id in latest_tags.values() for t in tags_for_id]
    final_fts = list(latest_fts.values())
    affected_ids = list(latest_memories.keys())

    conn = sqlite3.connect(database)
    try:
        conn.executescript(SCHEMA)
        before = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

        with conn:
            # 1. Insert or replace memory records
            conn.executemany(
                "INSERT OR REPLACE INTO memories VALUES (?, ?, ?, ?, ?, ?)",
                final_memories,
            )

            # 2. Synchronize tags table
            for mem_id in affected_ids:
                conn.execute("DELETE FROM memory_tags WHERE memory_id = ?", (mem_id,))
            conn.executemany(
                "INSERT OR REPLACE INTO memory_tags VALUES (?, ?)",
                final_tags,
            )

            # 3. Synchronize FTS5 virtual table
            for mem_id in affected_ids:
                conn.execute("DELETE FROM memories_fts WHERE id = ?", (mem_id,))
            conn.executemany(
                "INSERT INTO memories_fts VALUES (?, ?, ?, ?)",
                final_fts,
            )

        after = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    finally:
        conn.close()

    return total_parsed, after - before, after


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit("Usage: python memories_to_sqlite.py DATABASE.sqlite INPUT.json [INPUT.json ...]")

    db_path = sys.argv[1]
    sources = sys.argv[2:]

    try:
        loaded, added, total = load(db_path, sources)
    except (OSError, ValueError, sqlite3.Error) as exc:
        sys.exit(f"SQLite load failed: {exc}")

    print(f"{loaded} memory row(s) loaded, {added} new, {loaded - added} updated, {total} total in database")


if __name__ == "__main__":
    main()
