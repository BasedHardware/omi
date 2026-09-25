#!/usr/bin/env python3
"""Convert OMI memory exports to PostgreSQL DDL and idempotent UPSERT SQL.

Supports standard relational querying, native PostgreSQL full-text search (tsvector/GIN),
and optional vector embeddings via pgvector. Zero external dependencies.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Sequence


def escape_sql_string(val: Optional[str]) -> str:
    """Escape a string value for safe insertion as a SQL literal."""
    if val is None:
        return "NULL"
    # Replace single quotes with doubled single quotes
    escaped = val.replace("'", "''")
    return f"'{escaped}'"


def escape_sql_json(val: Any) -> str:
    """Serialize and escape an object as a JSONB SQL literal."""
    if val is None:
        return "NULL"
    serialized = json.dumps(val, ensure_ascii=False)
    escaped = serialized.replace("'", "''")
    return f"'{escaped}'::jsonb"


def parse_iso_datetime(dt_str: Optional[str]) -> Optional[str]:
    """Normalize ISO-8601 string to standard PostgreSQL timestamptz literal format."""
    if not dt_str:
        return None
    try:
        # Standardize 'Z' to UTC offset
        cleaned = dt_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S%z")
    except Exception:
        return None


def generate_schema_sql(with_pgvector: bool = False, vector_dim: int = 1536) -> str:
    """Generate DDL statements for table, extensions, and indices."""
    lines = [
        "-- OMI Memories PostgreSQL Schema",
        "CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";",
    ]
    if with_pgvector:
        lines.append("CREATE EXTENSION IF NOT EXISTS \"vector\";")

    lines.append("")
    lines.append("CREATE TABLE IF NOT EXISTS omi_memories (")
    lines.append("    id TEXT PRIMARY KEY,")
    lines.append("    content TEXT NOT NULL,")
    lines.append("    category TEXT,")
    lines.append("    created_at TIMESTAMPTZ,")
    lines.append("    updated_at TIMESTAMPTZ,")
    lines.append("    manually_added BOOLEAN DEFAULT FALSE,")
    lines.append("    deleted BOOLEAN DEFAULT FALSE,")
    lines.append("    score INTEGER DEFAULT 0,")
    lines.append("    metadata JSONB,")
    if with_pgvector:
        lines.append(f"    embedding vector({vector_dim}),")
    lines.append(
        "    search_vector tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED"
    )
    lines.append(");")
    lines.append("")
    lines.append("CREATE INDEX IF NOT EXISTS idx_omi_memories_created_at ON omi_memories (created_at DESC);")
    lines.append("CREATE INDEX IF NOT EXISTS idx_omi_memories_category ON omi_memories (category);")
    lines.append("CREATE INDEX IF NOT EXISTS idx_omi_memories_search ON omi_memories USING GIN (search_vector);")

    if with_pgvector:
        lines.append(
            "CREATE INDEX IF NOT EXISTS idx_omi_memories_embedding ON omi_memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);"
        )

    lines.append("")
    return "\n".join(lines)


def format_memory_sql_row(memory: Dict[str, Any], with_pgvector: bool = False) -> str:
    """Format a single memory dictionary into an idempotent PostgreSQL UPSERT statement."""
    mem_id = memory.get("id") or memory.get("uid") or ""
    if not mem_id:
        raise ValueError("Memory record missing required identifier 'id'")

    content = memory.get("content") or memory.get("text") or ""
    category = memory.get("category")
    created_at = parse_iso_datetime(memory.get("created_at"))
    updated_at = parse_iso_datetime(memory.get("updated_at")) or created_at
    manually_added = bool(memory.get("manually_added", False))
    deleted = bool(memory.get("deleted", False))
    score = memory.get("score")
    if not isinstance(score, int) or isinstance(score, bool):
        score = 0

    metadata = memory.get("metadata")
    if metadata is None:
        # Check structured or other metadata fields
        for field in ("structured", "source", "user_facts", "plugin_data"):
            if field in memory:
                if metadata is None:
                    metadata = {}
                metadata[field] = memory[field]

    id_lit = escape_sql_string(str(mem_id))
    content_lit = escape_sql_string(str(content))
    cat_lit = escape_sql_string(str(category)) if category is not None else "NULL"
    created_lit = escape_sql_string(created_at) if created_at else "CURRENT_TIMESTAMP"
    updated_lit = escape_sql_string(updated_at) if updated_at else "CURRENT_TIMESTAMP"
    manual_lit = "TRUE" if manually_added else "FALSE"
    deleted_lit = "TRUE" if deleted else "FALSE"
    score_lit = str(score)
    metadata_lit = escape_sql_json(metadata)

    if with_pgvector:
        embedding = memory.get("embedding")
        if isinstance(embedding, list) and all(isinstance(x, (int, float)) for x in embedding):
            emb_str = "[" + ",".join(str(float(x)) for x in embedding) + "]"
            emb_lit = f"'{emb_str}'::vector"
        else:
            emb_lit = "NULL"

        return f"""INSERT INTO omi_memories (
    id, content, category, created_at, updated_at, manually_added, deleted, score, metadata, embedding
) VALUES (
    {id_lit}, {content_lit}, {cat_lit}, {created_lit}, {updated_lit}, {manual_lit}, {deleted_lit}, {score_lit}, {metadata_lit}, {emb_lit}
) ON CONFLICT (id) DO UPDATE SET
    content = EXCLUDED.content,
    category = EXCLUDED.category,
    updated_at = EXCLUDED.updated_at,
    manually_added = EXCLUDED.manually_added,
    deleted = EXCLUDED.deleted,
    score = EXCLUDED.score,
    metadata = EXCLUDED.metadata,
    embedding = coalesce(EXCLUDED.embedding, omi_memories.embedding);"""

    return f"""INSERT INTO omi_memories (
    id, content, category, created_at, updated_at, manually_added, deleted, score, metadata
) VALUES (
    {id_lit}, {content_lit}, {cat_lit}, {created_lit}, {updated_lit}, {manual_lit}, {deleted_lit}, {score_lit}, {metadata_lit}
) ON CONFLICT (id) DO UPDATE SET
    content = EXCLUDED.content,
    category = EXCLUDED.category,
    updated_at = EXCLUDED.updated_at,
    manually_added = EXCLUDED.manually_added,
    deleted = EXCLUDED.deleted,
    score = EXCLUDED.score,
    metadata = EXCLUDED.metadata;"""


def convert_memories_to_postgresql(
    raw_data: Any, with_schema: bool = True, with_pgvector: bool = False, vector_dim: int = 1536
) -> str:
    """Convert JSON memories list or object to a complete PostgreSQL SQL script."""
    if isinstance(raw_data, dict):
        if "items" in raw_data and isinstance(raw_data["items"], list):
            memories = raw_data["items"]
        elif "memories" in raw_data and isinstance(raw_data["memories"], list):
            memories = raw_data["memories"]
        else:
            memories = [raw_data]
    elif isinstance(raw_data, list):
        memories = raw_data
    else:
        raise ValueError(f"Expected JSON list or object with 'items' key, got {type(raw_data).__name__}")

    output_blocks: List[str] = []
    if with_schema:
        output_blocks.append(generate_schema_sql(with_pgvector=with_pgvector, vector_dim=vector_dim))

    output_blocks.append("BEGIN;")
    valid_count = 0
    for mem in memories:
        if not isinstance(mem, dict):
            continue
        try:
            row_sql = format_memory_sql_row(mem, with_pgvector=with_pgvector)
            output_blocks.append(row_sql)
            valid_count += 1
        except Exception as e:
            # Skip invalid memory entries and continue
            output_blocks.append(f"-- Skipped invalid record: {e}")

    output_blocks.append("COMMIT;")
    output_blocks.append(f"-- Transformed {valid_count} memories successfully.")
    return "\n".join(output_blocks) + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert OMI memory exports to PostgreSQL schema and UPSERT statements."
    )
    parser.add_argument(
        "-i", "--input", type=Path, help="Input JSON file containing OMI memories (default: read from stdin)"
    )
    parser.add_argument("-o", "--output", type=Path, help="Output SQL script file path (default: write to stdout)")
    parser.add_argument("--no-schema", action="store_true", help="Omit table creation and index DDL statements")
    parser.add_argument(
        "--with-pgvector",
        action="store_true",
        help="Include pgvector extension, embedding column, and HNSW/IVFFlat index",
    )
    parser.add_argument("--vector-dim", type=int, default=1536, help="Vector dimension for embeddings (default: 1536)")

    args = parser.parse_args(argv)

    if args.input:
        if not args.input.exists():
            sys.stderr.write(f"Error: input file {args.input} not found\n")
            return 1
        content_text = args.input.read_text(encoding="utf-8")
    else:
        if sys.stdin.isatty():
            sys.stderr.write("Reading OMI memories JSON from stdin (pipe input or specify -i)...\n")
        content_text = sys.stdin.read()

    if not content_text.strip():
        sys.stderr.write("Error: empty input data\n")
        return 1

    try:
        data = json.loads(content_text)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"Error: invalid JSON input: {exc}\n")
        return 1

    try:
        sql = convert_memories_to_postgresql(
            data,
            with_schema=not args.no_schema,
            with_pgvector=args.with_pgvector,
            vector_dim=args.vector_dim,
        )
    except Exception as exc:
        sys.stderr.write(f"Error converting memories: {exc}\n")
        return 1

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(sql, encoding="utf-8")
        sys.stderr.write(f"Wrote PostgreSQL script to {args.output}\n")
    else:
        sys.stdout.write(sql)

    return 0


if __name__ == "__main__":
    sys.exit(main())
