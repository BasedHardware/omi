#!/usr/bin/env python3
"""memories_to_jsonl.py — Export Omi memories to JSON Lines datasets.

Two output schemas are supported:

  --format chat        Conversational SFT format (OpenAI/Anthropic/HuggingFace
                       messages schema).  Each memory becomes a single-turn
                       assistant message inside a {"messages": [...]} record.

  --format knowledge   Structured extraction format with full metadata:
                       {"id", "content", "category", "created_at", "source"}.

Usage
-----
  # Fetch from live API and write chat-format JSONL:
  omi --json memory list | python examples/memories_to_jsonl.py - -o out.jsonl

  # Multiple input files, deduplicated by id, knowledge format:
  python examples/memories_to_jsonl.py \\
      memories_2024.json memories_2025.json \\
      -o dataset.jsonl --format knowledge

  # Stream straight to stdout for further processing:
  omi --json memory list | python examples/memories_to_jsonl.py - -o /dev/stdout

Inputs
------
Each positional INPUT can be:
  -        read from stdin (JSON array or newline-delimited JSON objects)
  <file>   a file containing a JSON array or NDJSON

The script is stdlib-only (Python >= 3.8).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional

# ---------------------------------------------------------------------------
# Record loading
# ---------------------------------------------------------------------------


def _iter_records(text: str) -> Iterator[dict]:
    """Yield dicts from a JSON array or newline-delimited JSON blob."""
    text = text.strip()
    if not text:
        return
    if text.startswith("["):
        try:
            items = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON array: {exc}") from exc
        if not isinstance(items, list):
            raise ValueError("Top-level JSON value must be an array")
        for item in items:
            if isinstance(item, dict):
                yield item
        return
    # Newline-delimited JSON
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            print(
                f"[warn] line {lineno}: skipping malformed record ({exc})",
                file=sys.stderr,
            )
            continue
        if isinstance(obj, dict):
            yield obj


def load_inputs(paths: List[str]) -> List[dict]:
    """Load and deduplicate records from all inputs (by 'id' field)."""
    seen: Dict[str, bool] = {}
    records: List[dict] = []
    for path in paths:
        if path == "-":
            text = sys.stdin.read()
        else:
            text = Path(path).read_text(encoding="utf-8")
        for rec in _iter_records(text):
            rec_id = rec.get("id")
            if rec_id is None:
                records.append(rec)
            elif rec_id not in seen:
                seen[rec_id] = True
                records.append(rec)
    return records


# ---------------------------------------------------------------------------
# Schema formatters
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a helpful assistant with knowledge about the user's experiences, "
    "facts, and learnings captured by Omi."
)


def to_chat_record(memory: dict) -> Optional[dict]:
    """Convert a memory dict to the messages SFT schema.

    Returns None if the record has no usable content.
    """
    content = (
        memory.get("content")
        or (memory.get("structured") or {}).get("title")
        or memory.get("text")
        or ""
    ).strip()
    if not content:
        return None
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "What do you know about this?"},
            {"role": "assistant", "content": content},
        ]
    }


def to_knowledge_record(memory: dict) -> Optional[dict]:
    """Convert a memory dict to the structured knowledge extraction schema.

    Returns None if the record has no usable content.
    """
    content = (
        memory.get("content")
        or (memory.get("structured") or {}).get("title")
        or memory.get("text")
        or ""
    ).strip()
    if not content:
        return None

    raw_ts = memory.get("created_at")
    if isinstance(raw_ts, (int, float)):
        created_at = datetime.fromtimestamp(raw_ts, tz=timezone.utc).isoformat()
    elif isinstance(raw_ts, str):
        created_at = raw_ts
    else:
        created_at = None

    return {
        "id": memory.get("id"),
        "content": content,
        "category": memory.get("category") or memory.get("type"),
        "created_at": created_at,
        "source": memory.get("source") or memory.get("plugin_id"),
    }


FORMATTERS = {
    "chat": to_chat_record,
    "knowledge": to_knowledge_record,
}


# ---------------------------------------------------------------------------
# JSONL writer
# ---------------------------------------------------------------------------


def write_jsonl(records: List[dict], output: str, fmt: str) -> int:
    """Format *records* and write to *output* path (atomic via temp-and-replace).

    Returns the number of records written.
    """
    formatter = FORMATTERS[fmt]
    lines: List[bytes] = []
    skipped = 0
    for rec in records:
        out = formatter(rec)
        if out is None:
            skipped += 1
            continue
        lines.append(json.dumps(out, ensure_ascii=False).encode("utf-8"))

    if skipped:
        print(
            f"[info] skipped {skipped} records with no usable content",
            file=sys.stderr,
        )

    payload = b"\n".join(lines)
    if lines:
        payload += b"\n"

    if output in ("-", "/dev/stdout"):
        sys.stdout.buffer.write(payload)
    else:
        dest = Path(output)
        tmp = dest.with_suffix(".jsonl.tmp")
        tmp.unlink(missing_ok=True)
        try:
            with tmp.open("xb") as fh:
                fh.write(payload)
            tmp.replace(dest)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

    return len(lines)


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Convert Omi memories JSON to JSON Lines datasets for fine-tuning "
            "or structured knowledge extraction."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  omi --json memory list | python memories_to_jsonl.py - -o out.jsonl\n"
            "  python memories_to_jsonl.py memories.json -o dataset.jsonl "
            "--format knowledge\n"
            "  omi --json memory list | python memories_to_jsonl.py - -o /dev/stdout\n"
        ),
    )
    p.add_argument(
        "inputs",
        metavar="INPUT",
        nargs="+",
        help=(
            "One or more JSON input files (JSON array or NDJSON). "
            "Use '-' to read from stdin."
        ),
    )
    p.add_argument(
        "--output",
        "-o",
        required=True,
        metavar="OUTPUT",
        help="Destination .jsonl file, or '-' / '/dev/stdout' for stdout.",
    )
    p.add_argument(
        "--format",
        choices=list(FORMATTERS),
        default="chat",
        help="Output schema: 'chat' (SFT messages) or 'knowledge' (metadata). "
             "Default: chat.",
    )
    return p


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if "-" in args.inputs and args.output == "-":
        parser.error("Cannot use '-' (stdin) as input when output is also '-'")

    records = load_inputs(args.inputs)
    written = write_jsonl(records, args.output, args.format)
    print(
        f"[info] wrote {written} records ({args.format} format) -> {args.output}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
