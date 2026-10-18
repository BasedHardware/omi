#!/usr/bin/env python3
"""
Convert an Omi memory JSON export to CSV for spreadsheets, pandas, and bulk
imports — the memory-domain counterpart to the conversations -> CSV recipe.

Usage:
  omi memory list --json | python memories_to_csv.py -o memories.csv
  python memories_to_csv.py memories.json --category work,learnings --visibility public -o memories.csv

Fixed columns: id, content, category, tags, visibility, created_at,
updated_at, app_id (with ``source_app`` fallback). Tags are joined with
``|``; timestamps normalize to ISO-8601 UTC. Output defaults to stdout;
``-o`` writes exclusively (never overwrites).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

FIELDS = ("id", "content", "category", "tags", "visibility", "created_at", "updated_at", "app_id")
ENVELOPE_KEYS = ("memories", "items", "data")


def strip_surrogates(value: str) -> str:
    """Drop unpaired surrogate code points that cannot be encoded as UTF-8.

    ``json.loads`` accepts lone surrogates from a malformed export, but the
    csv writer raises UnicodeEncodeError on them. Dropping them keeps the
    remaining text and lets the row export.
    """
    return value.encode("utf-8", "ignore").decode("utf-8")


def spreadsheet_text(value: Any) -> str:
    """Render one exported field as spreadsheet-safe text.

    The dev API is loosely typed, so a field can arrive as a non-string even
    though the CLI models it as Optional[str]. One odd row must not destroy a
    whole export, so anything non-null is coerced rather than rejected.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    value = strip_surrogates(value)
    # Avoid treating common formula prefixes as formulas on spreadsheet import.
    # The apostrophe is intentional and may be visible in some importers.
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def iso_utc(value: Any) -> str:
    """Normalize a timestamp to ISO-8601 UTC (``...Z``).

    None/empty stays empty so missing timestamps round-trip honestly.
    Unparseable or boundary-overflow values keep their raw text instead of
    aborting the export.
    """
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, AttributeError, OverflowError):
        return s


def normalize_tags(value: Any) -> str:
    """Join a tags array with ``|``; scalar values coerce to one tag."""
    if isinstance(value, list):
        return "|".join(spreadsheet_text(t) for t in value if t is not None)
    return spreadsheet_text(value)


def normalize_row(item: Any) -> Optional[List[str]]:
    """Project a raw memory dict onto the fixed column set.

    Non-dict rows yield None and are dropped by the caller — one odd record
    must not crash the export, filtered or not.
    """
    if not isinstance(item, dict):
        return None
    app_id = item.get("app_id") or item.get("source_app")
    return [
        spreadsheet_text(item.get("id") or item.get("memory_id")),
        spreadsheet_text(item.get("content") or item.get("text") or item.get("title")),
        spreadsheet_text(item.get("category")),
        normalize_tags(item.get("tags")),
        spreadsheet_text(item.get("visibility")),
        iso_utc(item.get("created_at")),
        iso_utc(item.get("updated_at")),
        spreadsheet_text(app_id),
    ]


def unwrap(payload: Any) -> List[Any]:
    """Extract the memory list from a CLI export envelope.

    Handles ``{"memories": [...]}``/``items``/``data`` envelopes, bare lists,
    and single objects. Error payloads yield an empty list instead of a
    phantom row.
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


def parse_filter(spec: Optional[str]) -> Optional[set]:
    """Parse a comma-separated filter spec; empty → no filtering."""
    if not spec:
        return None
    vals = {v.strip().lower() for v in spec.split(",") if v.strip()}
    return vals or None


def convert(payload: Any, categories: Optional[set], visibilities: Optional[set]) -> List[Dict[str, Any]]:
    """Normalize every memory row, applying the optional filters.

    Both filters compare case-insensitively; a row whose field is absent
    simply doesn't match and is skipped under an active filter.
    """
    rows = []
    for raw in unwrap(payload):
        if not isinstance(raw, dict):
            continue
        cat = str(raw.get("category") or "").strip().lower()
        vis = str(raw.get("visibility") or "").strip().lower()
        if categories is not None and cat not in categories:
            continue
        if visibilities is not None and vis not in visibilities:
            continue
        row = normalize_row(raw)
        if row is not None:
            rows.append(row)
    return rows


def emit_csv(rows: List[List[str]]) -> bytes:
    """Render rows as UTF-8-BOM CSV bytes (Excel/Sheets open it natively).

    The whole export is formatted before the filesystem is touched, so a
    conversion failure cannot leave a truncated CSV behind.
    """
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(FIELDS)
    w.writerows(rows)
    return b'\xef\xbb\xbf' + buf.getvalue().encode("utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Convert an Omi memory JSON export to CSV.")
    ap.add_argument("input", nargs="?", default="-", help="Input JSON file (default: stdin)")
    ap.add_argument("-o", "--output", help="Write CSV to this path (exclusive create; stdout if omitted)")
    ap.add_argument("--category", help="Comma-separated case-insensitive category filter")
    ap.add_argument("--visibility", help="Comma-separated case-insensitive visibility filter")
    args = ap.parse_args(argv)

    try:
        if args.input == "-":
            raw = sys.stdin.buffer.read()
        else:
            raw = Path(args.input).read_bytes()
    except OSError as e:
        print(f"memories_to_csv: cannot read input: {e}", file=sys.stderr)
        return 2
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"memories_to_csv: invalid JSON input: {e}", file=sys.stderr)
        return 2

    rows = convert(payload, parse_filter(args.category), parse_filter(args.visibility))
    blob = emit_csv(rows)

    if not args.output:
        sys.stdout.buffer.write(blob)
        return 0
    out_path = Path(args.output)
    try:
        fd = out_path.open("xb")
    except FileExistsError:
        print(f"memories_to_csv: refusing to overwrite existing file: {out_path}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"memories_to_csv: cannot create output: {e}", file=sys.stderr)
        return 2
    try:
        with fd:
            fd.write(blob)
    except OSError as e:
        try:
            out_path.unlink(missing_ok=True)
        except OSError:
            pass
        print(f"memories_to_csv: write failed: {e}", file=sys.stderr)
        return 2
    print(f"memories_to_csv: wrote {len(rows)} row(s) to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
