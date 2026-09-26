"""Convert an Omi memories JSON export into ClickHouse SQL or JSONEachRow.

See memories_clickhouse.md for the full recipe.

Usage:
    omi --json memory list --limit 200 | python memories_to_clickhouse.py -
    python memories_to_clickhouse.py memories.json --format jsonl
    python memories_to_clickhouse.py --schema-only
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, List, Optional

TABLE_NAME = "omi_memories"
DEFAULT_CATEGORY = "uncategorized"
DEFAULT_VISIBILITY = "private"
DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d{1,3})?$")


SCHEMA_SQL = f"""\
CREATE TABLE IF NOT EXISTS {TABLE_NAME}
(
    id String,
    content String,
    category LowCardinality(String),
    visibility LowCardinality(String),
    created_at DateTime64(3, 'UTC'),
    updated_at DateTime64(3, 'UTC'),
    manually_added UInt8,
    tags Array(String),
    metadata_json String
) ENGINE = ReplacingMergeTree(updated_at)
PRIMARY KEY (id)
ORDER BY (id, category)
PARTITION BY toYYYYMM(created_at);
"""


def parse_datetime(value: Any) -> str:
    """Normalize an ISO-8601 timestamp to ClickHouse DateTime64 text in UTC."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            dt = None
        if dt is None:
            return "1970-01-01 00:00:00.000"
    else:
        return "1970-01-01 00:00:00.000"

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:23]


def escape_string(value: Any) -> str:
    """Escape a scalar for a ClickHouse single-quoted string literal."""
    if value is None:
        text = ""
    elif isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
    return text.replace("\\", "\\\\").replace("'", "\\'")


def escape_array(values: Any) -> str:
    """Escape a list of tags as a ClickHouse Array(String) literal."""
    if not isinstance(values, list):
        values = [] if values is None else [values]
    parts = []
    for item in values:
        if item is None:
            continue
        if isinstance(item, (dict, list)):
            text = json.dumps(item, ensure_ascii=False)
        else:
            text = str(item)
        if text != "":
            parts.append(f"'{escape_string(text)}'")
    return "[" + ", ".join(parts) + "]"


def normalize_memory(item: dict) -> dict:
    """Map one omi memory object onto the ClickHouse row shape."""
    if not isinstance(item, dict):
        raise ValueError("Each memory must be a JSON object")

    memory_id = item.get("id")
    if memory_id is None or str(memory_id).strip() == "":
        raise ValueError("Each memory requires a non-empty 'id'")

    content = item.get("content")
    if content is None:
        content = ""
    elif not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)

    category = item.get("category")
    category = DEFAULT_CATEGORY if category is None or str(category).strip() == "" else str(category)

    visibility = item.get("visibility")
    visibility = (
        DEFAULT_VISIBILITY if visibility is None or str(visibility).strip() == "" else str(visibility)
    )

    tags = item.get("tags")
    if not isinstance(tags, list):
        tags = [] if tags is None else [tags]
    cleaned_tags = [str(tag) for tag in tags if tag is not None and str(tag) != ""]

    created_at = parse_datetime(item.get("created_at"))
    updated_raw = item.get("updated_at")
    updated_at = parse_datetime(updated_raw) if updated_raw not in (None, "") else created_at

    manually_added = item.get("manually_added")
    if isinstance(manually_added, bool):
        manual_flag = 1 if manually_added else 0
    elif isinstance(manually_added, (int, float)):
        manual_flag = 1 if manually_added else 0
    elif isinstance(manually_added, str) and manually_added.strip().lower() in {"1", "true", "yes"}:
        manual_flag = 1
    else:
        manual_flag = 0

    metadata = item.get("metadata") or item.get("metadata_json") or {}
    if isinstance(metadata, str):
        metadata_json = metadata
    else:
        metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True)

    return {
        "id": str(memory_id),
        "content": content,
        "category": category,
        "visibility": visibility,
        "created_at": created_at,
        "updated_at": updated_at,
        "manually_added": manual_flag,
        "tags": cleaned_tags,
        "metadata_json": metadata_json,
    }


def format_sql_insert(record: dict) -> str:
    """Render one normalized record as a single INSERT statement."""
    values = ", ".join(
        [
            f"'{escape_string(record['id'])}'",
            f"'{escape_string(record['content'])}'",
            f"'{escape_string(record['category'])}'",
            f"'{escape_string(record['visibility'])}'",
            f"'{escape_string(record['created_at'])}'",
            f"'{escape_string(record['updated_at'])}'",
            str(int(record["manually_added"])),
            escape_array(record["tags"]),
            f"'{escape_string(record['metadata_json'])}'",
        ]
    )
    columns = (
        "id, content, category, visibility, created_at, updated_at, "
        "manually_added, tags, metadata_json"
    )
    return f"INSERT INTO {TABLE_NAME} ({columns}) VALUES ({values});"


def format_json_each_row(record: dict) -> str:
    """Render one normalized record as a JSONEachRow line."""
    payload = {
        "id": record["id"],
        "content": record["content"],
        "category": record["category"],
        "visibility": record["visibility"],
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "manually_added": int(record["manually_added"]),
        "tags": record["tags"],
        "metadata_json": record["metadata_json"],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def load_memories(source: str) -> List[dict]:
    """Read the omi --json memory list array from a file path or stdin ('-')."""
    if source == "-":
        raw = sys.stdin.buffer.read()
    else:
        raw = Path(source).read_bytes()

    text = raw.decode("utf-8-sig")
    if text.strip() == "":
        return []
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("Expected the JSON array from omi --json memory list")
    return data


def convert(
    items: Iterable[Any],
    *,
    output_format: str = "sql",
    include_schema: bool = True,
) -> str:
    """Convert memory objects into a ClickHouse SQL script or JSONEachRow stream."""
    records = [normalize_memory(item) for item in items]
    lines: List[str] = []

    if output_format == "sql":
        if include_schema:
            lines.append(SCHEMA_SQL.rstrip("\n"))
            lines.append("")
        for record in records:
            lines.append(format_sql_insert(record))
    elif output_format == "jsonl":
        for record in records:
            lines.append(format_json_each_row(record))
    else:
        raise ValueError(f"Unsupported format: {output_format}")

    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert an omi memories JSON export into ClickHouse SQL or JSONEachRow."
    )
    parser.add_argument(
        "source",
        nargs="?",
        default="-",
        help="JSON from omi --json memory list, or '-' for stdin (default: '-')",
    )
    parser.add_argument(
        "--format",
        choices=("sql", "jsonl"),
        default="sql",
        help="Output format: SQL INSERT statements or JSONEachRow lines (default: sql)",
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Print the CREATE TABLE statement and exit",
    )
    parser.add_argument(
        "--no-schema",
        action="store_true",
        help="Omit CREATE TABLE from SQL output",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Write output to this path instead of stdout",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.schema_only:
            payload = SCHEMA_SQL
        else:
            items = load_memories(args.source)
            payload = convert(
                items,
                output_format=args.format,
                include_schema=(args.format == "sql" and not args.no_schema),
            )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"ClickHouse export failed: {exc}\n")
        return 1

    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
