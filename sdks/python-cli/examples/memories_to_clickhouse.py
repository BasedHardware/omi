#!/usr/bin/env python3
"""Convert Omi memory JSON exports to ClickHouse payloads — a
``ReplacingMergeTree`` schema plus either SQL INSERTs or streaming
``JSONEachRow`` rows — for temporal analytics and large columnar queries.

See memories_clickhouse.md for the full recipe. Stdlib only.

Usage:
    omi --json memory list > memories.json

    # Emit DDL + SQL INSERTs, then load via clickhouse-client
    python memories_to_clickhouse.py memories.json -o memories.sql
    clickhouse-client --multiquery < memories.sql

    # Emit JSONEachRow and stream over HTTP
    python memories_to_clickhouse.py memories.json --format jsoneachrow -o memories.jsonl
    curl -sS 'http://localhost:8123/?query=INSERT%20INTO%20memories%20FORMAT%20JSONEachRow' \
        --data-binary @memories.jsonl
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ENVELOPE_KEYS = ("memories", "items", "data")


def schema_ddl() -> str:
    """ReplacingMergeTree DDL: monthly partition, dictionary-encoded lows."""
    return """CREATE TABLE IF NOT EXISTS memories (
    id              String,
    content         String,
    category        LowCardinality(String),
    tags            Array(String),
    visibility      LowCardinality(String),
    manually_added  UInt8,
    reviewed        UInt8,
    app_id          LowCardinality(String),
    created_at      DateTime64(3, 'UTC'),
    updated_at      DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY toYYYYMM(created_at)
ORDER BY id;
"""


def ch_datetime(value: Any) -> Optional[str]:
    """ISO-8601 → 'YYYY-MM-DD HH:MM:SS.mmm' UTC for DateTime64."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def ch_str(value: Any) -> str:
    """ClickHouse SQL string literal — backslash-escapes + quotes."""
    if value is None:
        return "''"
    s = str(value)
    s = s.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{s}'"


def ch_bool(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(bool(value))
    return int(str(value).strip().lower() in ("true", "yes", "1", "t"))


def normalize(item: Dict[str, Any]) -> Dict[str, Any]:
    """Project a raw memory onto the ClickHouse row shape."""
    return {
        "id": str(item.get("id") or item.get("memory_id") or ""),
        "content": str(item.get("content") or item.get("text") or item.get("title") or ""),
        "category": str(item.get("category") or ""),
        "tags": (
            item.get("tags")
            if isinstance(item.get("tags"), list)
            else ([item["tags"]] if item.get("tags") is not None else [])
        ),
        "visibility": str(item.get("visibility") or ""),
        "manually_added": ch_bool(item.get("manually_added")),
        "reviewed": ch_bool(item.get("reviewed")),
        "app_id": str(item.get("app_id") or item.get("source_app") or ""),
        "created_at": ch_datetime(item.get("created_at")),
        "updated_at": ch_datetime(item.get("updated_at")) or ch_datetime(item.get("created_at")),
    }


def extract_memories(data: Any) -> List[Any]:
    """Unwrap memories from bare lists or wrapped envelope dictionaries."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ENVELOPE_KEYS:
            if isinstance(data.get(key), list):
                return data[key]
        return [data]
    return []


def rows(sources: List[str]) -> List[Dict[str, Any]]:
    """Load all pages, dedupe by id (first wins)."""
    seen = set()
    out = []
    for src in sources:
        raw = json.loads(Path(src).read_bytes().decode("utf-8-sig"))
        for item in extract_memories(raw):
            if not isinstance(item, dict):
                continue
            mid = str(item.get("id") or item.get("memory_id") or "")
            if mid and mid in seen:
                continue
            if mid:
                seen.add(mid)
            row = normalize(item)
            if row["id"]:
                out.append(row)
    return out


def to_insert(row: Dict[str, Any]) -> str:
    tags = "[" + ", ".join(ch_str(t) for t in row["tags"]) + "]"
    return (
        "INSERT INTO memories "
        "(id, content, category, tags, visibility, manually_added, reviewed, app_id, created_at, updated_at) VALUES ("
        f"{ch_str(row['id'])}, {ch_str(row['content'])}, {ch_str(row['category'])}, {tags}, "
        f"{ch_str(row['visibility'])}, {row['manually_added']}, {row['reviewed']}, {ch_str(row['app_id'])}, "
        f"{ch_str(row['created_at'])}, {ch_str(row['updated_at'])});"
    )


def to_jsonrow(row: Dict[str, Any]) -> str:
    """One JSONEachRow line for HTTP streaming."""
    return json.dumps(
        {
            "id": row["id"],
            "content": row["content"],
            "category": row["category"],
            "tags": [str(t) for t in row["tags"]],
            "visibility": row["visibility"],
            "manually_added": row["manually_added"],
            "reviewed": row["reviewed"],
            "app_id": row["app_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        },
        ensure_ascii=False,
    )


def generate(sources: List[str], fmt: str) -> str:
    """DDL + INSERTs, or pure JSONEachRow lines, depending on *fmt*."""
    rs = rows(sources)
    if fmt == "jsoneachrow":
        return "\n".join(to_jsonrow(r) for r in rs) + ("\n" if rs else "")
    parts = ["-- Generated by memories_to_clickhouse.py", schema_ddl(), ""]
    parts += [to_insert(r) for r in rs]
    return "\n".join(parts) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Emit ClickHouse DDL + payloads for Omi memory exports.")
    ap.add_argument("inputs", nargs="*", help="JSON export files")
    ap.add_argument("-o", "--output", help="Destination path (exclusive create)")
    ap.add_argument("--format", choices=("sql", "jsoneachrow"), default="sql")
    ap.add_argument("--schema-only", action="store_true", help="Emit only the DDL")
    args = ap.parse_args(argv)

    if not args.schema_only and not args.inputs:
        ap.error("inputs are required unless --schema-only")
    try:
        out_text = schema_ddl() if args.schema_only else generate(args.inputs, args.format)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"memories_to_clickhouse: {e}", file=sys.stderr)
        return 2

    if not args.output:
        sys.stdout.write(out_text)
        return 0
    out = Path(args.output)
    if ".." in out.parts:
        print("memories_to_clickhouse: refusing '..' in output path", file=sys.stderr)
        return 2
    try:
        fd = out.open("x", encoding="utf-8")
    except FileExistsError:
        print(f"memories_to_clickhouse: refusing to overwrite existing {out}", file=sys.stderr)
        return 2
    with fd:
        fd.write(out_text)
    print(f"memories_to_clickhouse: wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
