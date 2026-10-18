#!/usr/bin/env python3
"""Convert Omi memory JSON exports to LanceDB-ready records — either a
zero-dependency JSON payload you feed to ``lancedb.connect().create_table``,
or direct ingestion when ``lancedb`` is installed.

See memories_lancedb.md for the full recipe.

Usage:
    # Zero-dep payload (JSON records LanceDB add() accepts)
    omi --json memory list > memories.json
    python memories_to_lancedb.py memories.json -o memories_records.json

    # Direct ingest (requires `pip install lancedb`)
    python memories_to_lancedb.py memories.json --ingest ./lancedb_data \
        --table memories --embedding-model all-MiniLM-L6-v2
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ENVELOPE_KEYS = ("memories", "items", "data")


def to_text(value: Any) -> Optional[str]:
    """Loosely typed field → str; None → None."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)


def to_tags(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(t) for t in value if t is not None]
    return [str(value)]


def to_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    low = str(value).strip().lower()
    if low in ("true", "yes", "1", "t"):
        return True
    if low in ("false", "no", "0", "f"):
        return False
    return None


def normalize(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """One memory → a LanceDB record (``text`` for the vectorizer + metadata)."""
    mid = to_text(item.get("id") or item.get("memory_id"))
    if not mid:
        return None
    text = to_text(item.get("content") or item.get("text") or item.get("title"))
    return {
        "id": mid,
        "text": text or "",  # what the embedder vectorizes
        "category": to_text(item.get("category")) or "",
        "tags": to_tags(item.get("tags")),
        "visibility": to_text(item.get("visibility")) or "",
        "manually_added": to_bool(item.get("manually_added")),
        "reviewed": to_bool(item.get("reviewed")),
        "app_id": to_text(item.get("app_id") or item.get("source_app")) or "",
        "created_at": to_text(item.get("created_at")),
        "updated_at": to_text(item.get("updated_at")),
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
            if row is not None:
                out.append(row)
    return out


def emit_payload(sources: List[str]) -> str:
    """Zero-dep JSON records, one LanceDB-ready dict per line."""
    rs = rows(sources)
    return "\n".join(json.dumps(r, ensure_ascii=False) for r in rs) + ("\n" if rs else "")


def ingest(sources: List[str], db_path: str, table_name: str, model: str) -> int:
    """Direct LanceDB ingest — embeds ``text`` so semantic search works.

    Uses LanceDB's embedding registry to declare ``text`` as the source
    field of a generated ``vector`` column — without it the table is a
    plain record store and ``tbl.search(query)`` can't do the semantic
    search the recipe documents. Requires ``lancedb`` +
    ``sentence-transformers``."""
    try:
        import lancedb as ldb
    except ImportError:
        raise ValueError(
            "direct ingest needs `pip install lancedb` — "
            "or use the payload mode (default) and feed it to lancedb yourself"
        )
    try:
        from lancedb.embeddings import get_registry
        from lancedb.pydantic import LanceModel, Vector

        emb = get_registry().get("sentence-transformers").create(name=model)
    except Exception as e:
        raise ValueError(
            "semantic ingest needs the embedding stack — "
            "`pip install lancedb sentence-transformers` "
            f"({e})"
        )

    rs = rows(sources)
    if not rs:
        return 0

    class Memory(LanceModel):
        id: str
        text: str = emb.SourceField()
        vector: Vector(emb.ndims()) = emb.VectorField()
        category: str = ""
        tags: List[str] = []
        visibility: str = ""
        manually_added: Optional[bool] = None
        reviewed: Optional[bool] = None
        app_id: str = ""
        created_at: Optional[str] = None
        updated_at: Optional[str] = None

    db = ldb.connect(db_path)
    tbl = db.create_table(table_name, schema=Memory, mode="overwrite")
    tbl.add(rs)
    return tbl.count_rows()


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Convert Omi memory exports to LanceDB records (payload or direct ingest)."
    )
    ap.add_argument("inputs", nargs="+", help="JSON export files")
    ap.add_argument("-o", "--output", help="Destination payload path (exclusive create)")
    ap.add_argument(
        "--ingest", metavar="DB_PATH", help="Ingest directly into a LanceDB at this path"
    )
    ap.add_argument("--table", default="memories", help="LanceDB table name for --ingest")
    ap.add_argument(
        "--embedding-model", default="all-MiniLM-L6-v2", help="Embedding model name (metadata)"
    )
    args = ap.parse_args(argv)

    try:
        if args.ingest:
            n = ingest(args.inputs, args.ingest, args.table, args.embedding_model)
            print(
                f"memories_to_lancedb: ingested {n} row(s) into {args.ingest}/{args.table}",
                file=sys.stderr,
            )
            return 0
        out_text = emit_payload(args.inputs)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"memories_to_lancedb: {e}", file=sys.stderr)
        return 2

    if not args.output:
        sys.stdout.write(out_text)
        return 0
    out = Path(args.output)
    if ".." in out.parts:
        print("memories_to_lancedb: refusing '..' in output path", file=sys.stderr)
        return 2
    try:
        fd = out.open("x", encoding="utf-8")
    except FileExistsError:
        print(f"memories_to_lancedb: refusing to overwrite existing {out}", file=sys.stderr)
        return 2
    with fd:
        fd.write(out_text)
    print(f"memories_to_lancedb: wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
