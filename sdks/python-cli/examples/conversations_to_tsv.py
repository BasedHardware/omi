#!/usr/bin/env python3
"""
Convert Omi conversation JSON exports to Tab-Separated Values (TSV) for
command-line text processing — ``grep``, ``awk``, ``cut``, ``sed``.

Usage:
  omi conversation list --json | python conversations_to_tsv.py -o conversations.tsv
  python conversations_to_tsv.py export.json > conversations.tsv

Exactly one line per record is guaranteed: embedded newlines, tabs, and
carriage returns are escaped as ``\\n``, ``\\t``, ``\\r`` so downstream
line-oriented tools never see a record straddle two lines.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

FIELDS = ("id", "title", "category", "started_at", "finished_at", "source", "overview", "action_items_count")
ENVELOPE_KEYS = ("conversations", "items", "data", "results")


def strip_surrogates(value: str) -> str:
    """Drop unpaired surrogate code points that cannot be encoded as UTF-8.

    ``json.loads`` accepts lone surrogates from a malformed export, but
    writing them to TSV raises UnicodeEncodeError. Dropping them keeps the
    remaining text and lets the row export.
    """
    return value.encode("utf-8", "ignore").decode("utf-8")


def tsv_cell(value: Any) -> str:
    """Escape one cell so a record can never straddle a line or column.

    Newlines/carriage returns/tabs become ``\\n``/``\\r``/``\\t`` literals —
    ``awk``/``cut``/``grep`` see exactly one field per column position.
    Non-string values coerce rather than reject: one odd row must not
    destroy the whole export.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    s = strip_surrogates(value)
    return s.replace("\\", "\\\\").replace("\t", "\\t").replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\r")


def action_items_count(item: Dict[str, Any]) -> str:
    """Count of action_items as a cell-safe number."""
    items = item.get("action_items")
    return str(len(items)) if isinstance(items, list) else ""


def unwrap(payload: Any) -> List[Any]:
    """Extract the conversation list from a CLI export envelope.

    Handles ``{"conversations": [...]}``/``items``/``data``/``results``,
    bare lists, and single objects. Error payloads yield an empty list.
    """
    if isinstance(payload, dict):
        if "error" in payload:
            return []
        for key in ENVELOPE_KEYS:
            if isinstance(payload.get(key), list):
                return payload[key]
        return [payload]
    if isinstance(payload, list):
        return payload
    return []


def normalize_row(item: Any) -> Optional[List[str]]:
    """Project a raw conversation onto the fixed column set."""
    if not isinstance(item, dict):
        return None
    structured = item.get("structured") if isinstance(item.get("structured"), dict) else {}
    return [
        tsv_cell(item.get("id") or item.get("conversation_id")),
        tsv_cell(item.get("title") or structured.get("title")),
        tsv_cell(item.get("category") or structured.get("category")),
        tsv_cell(item.get("started_at")),
        tsv_cell(item.get("finished_at")),
        tsv_cell(item.get("source") or "omi"),
        tsv_cell(item.get("overview") or structured.get("overview")),
        action_items_count(item),
    ]


def convert(payload: Any) -> List[List[str]]:
    """Normalize every conversation row; odd records are dropped."""
    rows = []
    for raw in unwrap(payload):
        row = normalize_row(raw)
        if row is not None:
            rows.append(row)
    return rows


def emit_tsv(rows: List[List[str]]) -> str:
    """Render header + rows, one record per line, tab-separated."""
    buf = io.StringIO()
    buf.write("\t".join(FIELDS) + "\n")
    for r in rows:
        buf.write("\t".join(r) + "\n")
    return buf.getvalue()


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Convert an Omi conversation JSON export to TSV.")
    ap.add_argument("input", nargs="?", default="-", help="Input JSON file (default: stdin)")
    ap.add_argument("-o", "--output", help="Write TSV to this path (stdout if omitted)")
    args = ap.parse_args(argv)

    if args.output and ".." in Path(args.output).parts:
        print("conversations_to_tsv: refusing '..' in output path", file=sys.stderr)
        return 2
    try:
        raw = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8-sig")
    except OSError as e:
        print(f"conversations_to_tsv: cannot read input: {e}", file=sys.stderr)
        return 2
    try:
        payload = json.loads(raw.lstrip("﻿"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"conversations_to_tsv: invalid JSON input: {e}", file=sys.stderr)
        return 2

    rows = convert(payload)
    output = emit_tsv(rows)

    if not args.output:
        sys.stdout.write(output)
        return 0
    try:
        Path(args.output).write_text(output, encoding="utf-8")
    except OSError as e:
        print(f"conversations_to_tsv: write failed: {e}", file=sys.stderr)
        return 2
    print(f"conversations_to_tsv: wrote {len(rows)} record(s) to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
