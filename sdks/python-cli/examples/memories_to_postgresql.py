#!/usr/bin/env python3
"""Convert Omi memory JSON exports to PostgreSQL-ready SQL — schema DDL +
idempotent INSERTs — for `psql` pipelines and pgvector RAG work.

See memories_postgresql.md for the full recipe. Stdlib only.

Usage:
    omi --json memory list > memories.json
    python memories_to_postgresql.py memories.json -o memories.sql
    psql -d omi -f memories.sql

    # Emit the DDL only
    python memories_to_postgresql.py --schema-only -o schema.sql

    # Emit pgvector-capable schema (embedding column + ivfflat index)
    python memories_to_postgresql.py --schema-only --with-pgvector -o schema.sql

The script emits *SQL*, never connects — pipe it to `psql -f`. Inserts use
``ON CONFLICT (id) DO UPDATE`` so re-importing a page never duplicates rows.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ENVELOPE_KEYS = ("memories", "items", "data")


def schema_ddl(with_pgvector: bool = False) -> str:
    """Idempotent DDL: table + indexes; optional vector extension."""
    lines = [
        "CREATE TABLE IF NOT EXISTS memories (",
        "    id              TEXT PRIMARY KEY,",
        "    content         TEXT,",
        "    category        TEXT,",
        "    tags            TEXT[],",
        "    visibility      TEXT,",
        "    manually_added  BOOLEAN,",
        "    reviewed        BOOLEAN,",
        "    app_id          TEXT,",
        "    created_at      TIMESTAMPTZ,",
        "    updated_at      TIMESTAMPTZ,",
        "    search_vector   tsvector GENERATED ALWAYS AS (",
        "        to_tsvector('english', coalesce(content, '') || ' ' || coalesce(category, ''))",
        "    ) STORED",
    ]
    if with_pgvector:
        lines.append("    , embedding     vector(1536)")
    lines.append(");")
    lines += [
        "CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);",
        "CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at);",
        "CREATE INDEX IF NOT EXISTS idx_memories_manually_added ON memories(manually_added);",
        "CREATE INDEX IF NOT EXISTS idx_memories_search ON memories USING GIN(search_vector);",
    ]
    if with_pgvector:
        lines += [
            "",
            "-- Requires: CREATE EXTENSION IF NOT EXISTS vector;",
            "CREATE INDEX IF NOT EXISTS idx_memories_embedding",
            "    ON memories USING ivfflat(embedding vector_cosine_ops) WITH (lists = 100);",
        ]
    return "\n".join(lines) + "\n"


def sql_literal(value: Any) -> str:
    """Render a Python value as a PostgreSQL literal."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        inner = ", ".join(sql_literal(v) for v in value)
        return f"ARRAY[{inner}]::text[]"
    s = str(value).replace("'", "''")
    return f"'{s}'"


def ts_literal(value: Any) -> str:
    """ISO-8601 timestamp → TIMESTAMPTZ literal; non-string → NULL."""
    if not isinstance(value, str) or not value.strip():
        return "NULL"
    return sql_literal(value.strip())


def tags_array(value: Any) -> str:
    """tags → text[] literal; scalar → single-element array; None → NULL."""
    if value is None:
        return "NULL"
    if isinstance(value, list):
        return sql_literal(value)
    return sql_literal([value])


def bool_lit(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return "TRUE" if value else "FALSE"
    low = str(value).strip().lower()
    return "TRUE" if low in ("true", "yes", "1", "t") else "FALSE"


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


def row_sql(item: Dict[str, Any]) -> str:
    """One memory → an ON CONFLICT upsert statement."""
    cols = (
        sql_literal(item.get("id") or item.get("memory_id")),
        sql_literal(item.get("content") or item.get("text") or item.get("title")),
        sql_literal(item.get("category")),
        tags_array(item.get("tags")),
        sql_literal(item.get("visibility")),
        bool_lit(item.get("manually_added")),
        bool_lit(item.get("reviewed")),
        sql_literal(item.get("app_id") or item.get("source_app")),
        ts_literal(item.get("created_at")),
        ts_literal(item.get("updated_at")),
    )
    return (
        "INSERT INTO memories "
        "(id, content, category, tags, visibility, manually_added, reviewed, app_id, created_at, updated_at)\n"
        f"VALUES ({', '.join(cols)})\n"
        "ON CONFLICT (id) DO UPDATE SET\n"
        "    content = EXCLUDED.content, category = EXCLUDED.category, tags = EXCLUDED.tags,\n"
        "    visibility = EXCLUDED.visibility, manually_added = EXCLUDED.manually_added,\n"
        "    reviewed = EXCLUDED.reviewed, app_id = EXCLUDED.app_id,\n"
        "    created_at = EXCLUDED.created_at, updated_at = EXCLUDED.updated_at;"
    )


def generate(sources: List[str], with_pgvector: bool = False) -> str:
    """DDL + upserts for all input pages."""
    seen = set()
    stmts = ["-- Generated by memories_to_postgresql.py\n", schema_ddl(with_pgvector), ""]
    for src in sources:
        raw = json.loads(Path(src).read_bytes().decode("utf-8-sig"))
        for item in extract_memories(raw):
            if not isinstance(item, dict):
                continue
            mid = str(item.get("id") or item.get("memory_id") or "")
            if not mid or mid in seen:
                continue
            seen.add(mid)
            stmts.append(row_sql(item))
            stmts.append("")
    return "\n".join(stmts)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Emit PostgreSQL DDL + upserts for Omi memory exports.")
    ap.add_argument("inputs", nargs="*", help="JSON export files")
    ap.add_argument("-o", "--output", help="Destination .sql path (exclusive create)")
    ap.add_argument("--schema-only", action="store_true", help="Emit only the DDL")
    ap.add_argument("--with-pgvector", action="store_true", help="Add the embedding column + ivfflat index")
    args = ap.parse_args(argv)

    if not args.schema_only and not args.inputs:
        ap.error("inputs are required unless --schema-only")
    try:
        if args.schema_only:
            sql = schema_ddl(args.with_pgvector)
        else:
            sql = generate(args.inputs, args.with_pgvector)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"memories_to_postgresql: {e}", file=sys.stderr)
        return 2

    if not args.output:
        sys.stdout.write(sql)
        return 0
    out = Path(args.output)
    if ".." in out.parts:
        print("memories_to_postgresql: refusing '..' in output path", file=sys.stderr)
        return 2
    try:
        fd = out.open("x", encoding="utf-8")
    except FileExistsError:
        print(f"memories_to_postgresql: refusing to overwrite existing {out}", file=sys.stderr)
        return 2
    with fd:
        fd.write(sql)
    print(f"memories_to_postgresql: wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
