#!/usr/bin/env python3
"""Convert Omi memories JSON exports into an idempotent PostgreSQL SQL script.

Generates table DDL, full-text search (tsvector + GIN index), JSONB metadata support,
and ON CONFLICT DO UPDATE upsert statements for import via psql or database migration.

Features:
- Pure Python standard library (zero external dependencies).
- Strict SQL injection mitigation via literal quote escaping.
- Full-text search indexing via PostgreSQL tsvector.
- Safe atomic file writes with accidental overwrite prevention.
- Path traversal guards preventing directory escape.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_DDL = """-- Omi Memories PostgreSQL Schema (Idempotent)
CREATE TABLE IF NOT EXISTS memories (
    id VARCHAR(255) PRIMARY KEY,
    content TEXT NOT NULL,
    category VARCHAR(100),
    tags TEXT,
    visibility VARCHAR(50) DEFAULT 'private',
    source VARCHAR(100),
    conversation_id VARCHAR(255),
    created_at TIMESTAMP WITHOUT TIME ZONE,
    updated_at TIMESTAMP WITHOUT TIME ZONE,
    raw_json JSONB NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(content, '') || ' ' || coalesce(category, '') || ' ' || coalesce(tags, ''))
    ) STORED
);

CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories (category);
CREATE INDEX IF NOT EXISTS idx_memories_search ON memories USING gin (search_vector);
CREATE INDEX IF NOT EXISTS idx_memories_raw_json ON memories USING gin (raw_json);
"""


def strip_surrogates(text: Optional[str]) -> Optional[str]:
    """Remove lone surrogates which trigger encoding failures."""
    if text is None:
        return None
    return text.encode("utf-8", "ignore").decode("utf-8")


def escape_sql_string(val: Optional[str]) -> str:
    """Safely escape a string literal for PostgreSQL by doubling single quotes."""
    if val is None:
        return "NULL"
    cleaned = strip_surrogates(str(val))
    if cleaned is None:
        return "NULL"
    escaped = cleaned.replace("'", "''")
    return f"'{escaped}'"


def escape_sql_jsonb(val: Any) -> str:
    """Serialize and escape a Python dictionary/list as a PostgreSQL JSONB literal."""
    if val is None:
        return "'{}'::jsonb"
    raw_json = json.dumps(val, ensure_ascii=False)
    cleaned = strip_surrogates(raw_json) or "{}"
    escaped = cleaned.replace("'", "''")
    return f"'{escaped}'::jsonb"


def normalize_utc_timestamp(val: Any) -> Optional[str]:
    """Parse ISO-8601 timestamp and normalize to UTC naive 'YYYY-MM-DD HH:MM:SS' string."""
    if not val or not isinstance(val, str):
        return None
    cleaned = val.strip()
    if not cleaned:
        return None
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def serialize_tags(tags: Any) -> Optional[str]:
    """Serialize tags array or string into comma-separated text."""
    if tags is None:
        return None
    if isinstance(tags, list):
        cleaned = [strip_surrogates(str(t).strip()) for t in tags if str(t).strip()]
        return ", ".join(cleaned) if cleaned else None
    s = strip_surrogates(str(tags).strip())
    return s if s else None


def validate_path(path_str: str) -> Path:
    """Validate path safety, refusing relative traversal with '..' components."""
    p = Path(path_str)
    if ".." in p.parts:
        raise ValueError(f"Path {path_str!r} contains '..'; refusing relative directory traversal.")
    return p


def format_memory_upsert_sql(item: Dict[str, Any]) -> str:
    """Format a single memory dictionary into an idempotent PostgreSQL UPSERT statement."""
    mem_id = strip_surrogates(str(item.get("id") or "").strip())
    if not mem_id:
        raise ValueError("Memory record missing required identifier 'id'")

    content = strip_surrogates(str(item.get("content") or "").strip())
    category = strip_surrogates(item.get("category"))
    if category is not None:
        category = str(category).strip().lower()

    tags = serialize_tags(item.get("tags"))
    visibility = strip_surrogates(item.get("visibility") or "private")
    source = strip_surrogates(item.get("source"))
    conversation_id = strip_surrogates(item.get("conversation_id"))
    created_at = normalize_utc_timestamp(item.get("created_at"))
    updated_at = normalize_utc_timestamp(item.get("updated_at")) or created_at

    id_lit = escape_sql_string(mem_id)
    content_lit = escape_sql_string(content)
    category_lit = escape_sql_string(category)
    tags_lit = escape_sql_string(tags)
    visibility_lit = escape_sql_string(visibility)
    source_lit = escape_sql_string(source)
    conversation_id_lit = escape_sql_string(conversation_id)
    created_at_lit = escape_sql_string(created_at)
    updated_at_lit = escape_sql_string(updated_at)
    raw_json_lit = escape_sql_jsonb(item)

    sql = (
        f"INSERT INTO memories (\n"
        f"    id, content, category, tags, visibility, source,\n"
        f"    conversation_id, created_at, updated_at, raw_json\n"
        f") VALUES (\n"
        f"    {id_lit}, {content_lit}, {category_lit}, {tags_lit}, {visibility_lit}, {source_lit},\n"
        f"    {conversation_id_lit}, {created_at_lit}, {updated_at_lit}, {raw_json_lit}\n"
        f")\n"
        f"ON CONFLICT (id) DO UPDATE SET\n"
        f"    content = EXCLUDED.content,\n"
        f"    category = EXCLUDED.category,\n"
        f"    tags = EXCLUDED.tags,\n"
        f"    visibility = EXCLUDED.visibility,\n"
        f"    source = EXCLUDED.source,\n"
        f"    conversation_id = EXCLUDED.conversation_id,\n"
        f"    created_at = EXCLUDED.created_at,\n"
        f"    updated_at = EXCLUDED.updated_at,\n"
        f"    raw_json = EXCLUDED.raw_json;"
    )
    return sql


def convert_memories_to_postgresql(
    items: List[Dict[str, Any]],
    with_schema: bool = True,
) -> Tuple[str, int]:
    """Convert a list of memory items into a PostgreSQL SQL script wrapped in a transaction."""
    statements: List[str] = [
        "-- Generated by omi-cli memories_to_postgresql converter",
        "BEGIN;",
    ]

    if with_schema:
        statements.append("")
        statements.append(SCHEMA_DDL.strip())

    transformed = 0
    statements.append("")
    statements.append("-- Memory records")

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        try:
            upsert_sql = format_memory_upsert_sql(item)
            statements.append(upsert_sql)
            transformed += 1
        except ValueError as err:
            statements.append(f"-- Skipped item index {idx}: {err}")

    statements.append("")
    statements.append("COMMIT;")
    statements.append(f"-- Successfully processed {transformed} memory records.")
    return "\n".join(statements) + "\n", transformed


def load_input_json(source: Optional[str]) -> List[Dict[str, Any]]:
    """Load JSON from standard input or a local file path."""
    if source is None or source == "-":
        raw = sys.stdin.read()
    else:
        path = validate_path(source)
        if not path.is_file():
            raise FileNotFoundError(f"Input file not found: {source}")
        raw = path.read_text(encoding="utf-8-sig")

    data = json.loads(raw)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("memories", "data", "items"):
            if key in data and isinstance(data[key], list):
                return data[key]
        return [data]
    raise ValueError("Input JSON must be an array or object containing memories.")


def write_output_sql(content: str, output_path: Optional[str], overwrite: bool = False) -> None:
    """Write generated SQL script to stdout or safely to an output file."""
    if not output_path or output_path == "-":
        sys.stdout.write(content)
        sys.stdout.flush()
        return

    dest = validate_path(output_path)
    if dest.parent and not dest.parent.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)

    partial = dest.with_name(f"{dest.name}.partial.{os.getpid()}")
    try:
        partial.write_text(content, encoding="utf-8")
        if overwrite:
            os.replace(partial, dest)
        else:
            try:
                os.link(partial, dest)
                partial.unlink()
            except FileExistsError:
                raise FileExistsError(f"Refusing to overwrite existing {dest} (use --overwrite)")
            except OSError:
                if dest.exists():
                    raise FileExistsError(f"Refusing to overwrite existing {dest} (use --overwrite)")
                os.replace(partial, dest)
    except Exception:
        if partial.exists():
            try:
                partial.unlink()
            except OSError:
                pass
        raise


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi memories JSON export into an idempotent PostgreSQL SQL script.",
    )
    parser.add_argument(
        "-i",
        "--input",
        dest="input_opt",
        default=None,
        help="Path to JSON file (or '-' for stdin)",
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=None,
        help="Path to JSON file (or '-' / omit for stdin)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Target SQL file (default: stdout)",
    )
    parser.add_argument(
        "--no-schema",
        action="store_true",
        help="Omit DDL schema generation (only generate INSERT statements)",
    )
    parser.add_argument(
        "-f",
        "--overwrite",
        action="store_true",
        help="Overwrite target output file if it already exists",
    )

    args = parser.parse_args(argv)

    try:
        source = args.input_opt or args.input or "-"
        items = load_input_json(source)
        sql_content, count = convert_memories_to_postgresql(
            items=items,
            with_schema=not args.no_schema,
        )
        write_output_sql(sql_content, args.output, overwrite=args.overwrite)
        if args.output and args.output != "-":
            sys.stderr.write(f"Successfully converted {count} memories to {args.output}\n")
        return 0
    except Exception as err:
        sys.stderr.write(f"Error: {err}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
