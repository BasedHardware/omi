#!/usr/bin/env python3
"""Convert OMI memory exports to LanceDB serverless vector database tables and ingestion payloads.

Supports both direct LanceDB table generation (when lancedb is installed) and zero-dependency
PyArrow/LanceDB-compatible JSONL / batch payloads for local semantic search and RAG retrieval.
Zero external dependencies required for core conversion.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


def generate_deterministic_vector(text: str, dim: int = 384) -> List[float]:
    """Generate a deterministic, unit-normalized float vector from text using hash projections.

    Provides reproducible pseudo-embeddings for development, offline testing, and schemas
    when an external embedding API (OpenAI, Voyage, Ollama) is not configured.
    """
    if not text:
        text = "empty"
    raw_vals: List[float] = []
    # Seed with SHA-256 rounds
    h = hashlib.sha256(text.encode("utf-8")).digest()
    state = int.from_bytes(h, "big")
    for i in range(dim):
        state = (state * 1664525 + 1013904223) & 0xFFFFFFFFFFFFFFFF
        val = ((state >> 32) & 0xFFFF) / 32768.0 - 1.0
        raw_vals.append(val)

    # Unit L2 normalization
    norm = math.sqrt(sum(x * x for x in raw_vals))
    if norm < 1e-12:
        norm = 1.0
    return [round(x / norm, 6) for x in raw_vals]


def extract_text_content(record: Dict[str, Any]) -> str:
    """Extract full searchable text content from a memory record."""
    parts: List[str] = []
    if record.get("content"):
        parts.append(str(record["content"]))
    if record.get("title"):
        parts.append(str(record["title"]))
    if record.get("structured"):
        structured = record["structured"]
        if isinstance(structured, dict):
            for k in ("title", "overview", "summary", "category"):
                if structured.get(k):
                    parts.append(str(structured[k]))
    return " ".join(parts).strip()


def normalize_iso_timestamp(ts_raw: Any) -> str:
    """Normalize any timestamp input to ISO 8601 UTC string."""
    if not ts_raw:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(ts_raw, (int, float)):
        # Support millisecond or second epoch
        sec = ts_raw / 1000.0 if ts_raw > 1e11 else float(ts_raw)
        return datetime.fromtimestamp(sec, timezone.utc).isoformat()
    if isinstance(ts_raw, str):
        try:
            dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            return dt.isoformat()
        except ValueError:
            return ts_raw
    return str(ts_raw)


def normalize_memory_record(
    record: Dict[str, Any], vector_dim: int = 384
) -> Dict[str, Any]:
    """Convert an OMI memory object to a LanceDB-compliant schema record."""
    memory_id = str(
        record.get("id")
        or record.get("memory_id")
        or hashlib.md5(str(record).encode()).hexdigest()[:16]
    )
    content = extract_text_content(record)

    # Vector embedding extraction or deterministic generation
    vector: List[float] = []
    if (
        "vector" in record
        and isinstance(record["vector"], list)
        and len(record["vector"]) > 0
    ):
        vector = [float(x) for x in record["vector"]]
    elif (
        "embedding" in record
        and isinstance(record["embedding"], list)
        and len(record["embedding"]) > 0
    ):
        vector = [float(x) for x in record["embedding"]]
    else:
        vector = generate_deterministic_vector(content, dim=vector_dim)

    # Extract metadata attributes
    category = "general"
    if record.get("category"):
        category = str(record["category"])
    elif isinstance(record.get("structured"), dict) and record["structured"].get(
        "category"
    ):
        category = str(record["structured"]["category"])

    metadata: Dict[str, Any] = {
        "user_id": str(record.get("user_id") or record.get("uid") or ""),
        "source": str(record.get("source") or "omi"),
        "discarded": bool(record.get("discarded", False)),
        "manually_added": bool(record.get("manually_added", False)),
    }
    if "tags" in record and isinstance(record["tags"], list):
        metadata["tags"] = [str(t) for t in record["tags"]]

    created_at = normalize_iso_timestamp(record.get("created_at"))

    return {
        "id": memory_id,
        "content": content,
        "category": category,
        "vector": vector,
        "created_at": created_at,
        "metadata": json.dumps(metadata, ensure_ascii=False),
    }


def parse_omi_memories(input_data: Any) -> List[Dict[str, Any]]:
    """Parse OMI memory items from either a list, dict envelope, or string."""
    if isinstance(input_data, list):
        return [r for r in input_data if isinstance(r, dict)]
    if isinstance(input_data, dict):
        if "memories" in input_data and isinstance(input_data["memories"], list):
            return [r for r in input_data["memories"] if isinstance(r, dict)]
        if "items" in input_data and isinstance(input_data["items"], list):
            return [r for r in input_data["items"] if isinstance(r, dict)]
        if "data" in input_data and isinstance(input_data["data"], list):
            return [r for r in input_data["data"] if isinstance(r, dict)]
        # Single memory item
        return [input_data]
    return []


def export_to_lancedb_payload(
    raw_records: Sequence[Dict[str, Any]],
    vector_dim: int = 384,
    deduplicate: bool = True,
) -> List[Dict[str, Any]]:
    """Transform raw OMI memory records into LanceDB table records."""
    normalized_list: List[Dict[str, Any]] = []
    seen_ids = set()

    for item in raw_records:
        norm = normalize_memory_record(item, vector_dim=vector_dim)
        mid = norm["id"]
        if deduplicate and mid in seen_ids:
            continue
        seen_ids.add(mid)
        normalized_list.append(norm)

    return normalized_list


def write_lancedb_jsonl(
    records: Sequence[Dict[str, Any]], output_path: Path, overwrite: bool = False
) -> None:
    """Write records to a JSON Lines (.jsonl) file ready for LanceDB table ingestion."""
    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"Destination '{output_path}' already exists. Use --overwrite to replace it."
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    with temp_path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    temp_path.replace(output_path)


def write_direct_lancedb(
    records: Sequence[Dict[str, Any]],
    db_path: str,
    table_name: str = "memories",
    overwrite: bool = False,
) -> bool:
    """Write records directly to a LanceDB dataset if the lancedb package is installed."""
    try:
        import lancedb
    except ImportError:
        return False

    db = lancedb.connect(db_path)
    mode = "overwrite" if overwrite else "create"
    if table_name in db.table_names():
        if overwrite:
            table = db.create_table(table_name, data=list(records), mode="overwrite")
        else:
            table = db.open_table(table_name)
            table.add(list(records))
    else:
        db.create_table(table_name, data=list(records), mode="create")
    return True


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export OMI memories to LanceDB serverless vector database tables and JSONL ingestion payloads."
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Path to OMI memories JSON / JSONL export file, or '-' for stdin.",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Path to output JSONL file (Mode: payload) or LanceDB directory (Mode: direct).",
    )
    parser.add_argument(
        "-t",
        "--table-name",
        default="memories",
        help="LanceDB table name (default: memories).",
    )
    parser.add_argument(
        "-d",
        "--dim",
        type=int,
        default=384,
        help="Vector embedding dimensions (default: 384).",
    )
    parser.add_argument(
        "-m",
        "--mode",
        choices=["payload", "direct"],
        default="payload",
        help="Export mode: 'payload' (PyArrow/JSONL batch for LanceDB table ingestion) or 'direct' (write to LanceDB DB directly).",
    )
    parser.add_argument(
        "--no-dedup",
        action="store_true",
        help="Disable deduplication by memory id.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite target output if it already exists.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Format JSON summary output to stdout.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    # 1. Read input
    if args.input == "-":
        raw_text = sys.stdin.read()
    else:
        in_path = Path(args.input)
        if not in_path.exists():
            print(f"Error: input file '{args.input}' not found.", file=sys.stderr)
            return 1
        raw_text = in_path.read_text(encoding="utf-8")

    # 2. Parse JSON or JSONL
    raw_records: List[Dict[str, Any]] = []
    stripped = raw_text.strip()
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
            raw_records = parse_omi_memories(parsed)
        except json.JSONDecodeError as err:
            print(f"Error parsing JSON input: {err}", file=sys.stderr)
            return 1
    else:
        # Try JSONL
        for line_no, line in enumerate(stripped.splitlines(), start=1):
            line_str = line.strip()
            if not line_str:
                continue
            try:
                rec = json.loads(line_str)
                if isinstance(rec, dict):
                    raw_records.append(rec)
            except json.JSONDecodeError as err:
                print(
                    f"Warning: skipped invalid JSON line {line_no}: {err}",
                    file=sys.stderr,
                )

    if not raw_records:
        print("Warning: no memory records found in input.", file=sys.stderr)

    # 3. Transform to LanceDB schema
    lancedb_records = export_to_lancedb_payload(
        raw_records,
        vector_dim=args.dim,
        deduplicate=not args.no_dedup,
    )

    # 4. Ingestion / Export
    out_target = Path(args.output)
    if args.mode == "direct":
        success = write_direct_lancedb(
            lancedb_records,
            db_path=str(out_target),
            table_name=args.table_name,
            overwrite=args.overwrite,
        )
        if not success:
            print(
                "Notice: 'lancedb' package not installed in current environment. "
                "Falling back to exporting PyArrow-compatible JSONL payload.",
                file=sys.stderr,
            )
            jsonl_fallback = (
                out_target
                if out_target.suffix
                else out_target / f"{args.table_name}.jsonl"
            )
            write_lancedb_jsonl(
                lancedb_records, jsonl_fallback, overwrite=args.overwrite
            )
            out_target = jsonl_fallback
    else:
        write_lancedb_jsonl(lancedb_records, out_target, overwrite=args.overwrite)

    # Summary
    summary = {
        "status": "success",
        "records_processed": len(raw_records),
        "records_exported": len(lancedb_records),
        "vector_dim": args.dim,
        "table_name": args.table_name,
        "output": str(out_target),
    }
    indent = 2 if args.pretty else None
    print(json.dumps(summary, indent=indent, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
