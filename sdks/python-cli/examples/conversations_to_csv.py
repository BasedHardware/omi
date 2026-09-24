#!/usr/bin/env python3
"""Convert Omi conversation-list JSON exports to CSV spreadsheet format.

Usage:
    python conversations_to_csv.py conversations.json -o conversations.csv
    omi --json conversation list --include-transcript | python conversations_to_csv.py - -o conversations.csv
    python conversations_to_csv.py page1.json page2.json -o merged.csv

Outputs a spreadsheet-ready UTF-8 CSV with formula injection safeguards and
UTC-normalized timestamps compatible with Excel, Google Sheets, and LibreOffice.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

FIELDS: Sequence[str] = (
    "id",
    "title",
    "category",
    "overview",
    "source",
    "action_items_count",
    "turns_count",
    "started_at",
    "created_at",
    "updated_at",
    "transcript",
)


def spreadsheet_text(value: Any) -> str:
    """Render one exported field as spreadsheet-safe text.

    Coerces non-null values safely to strings and escapes common formula
    prefixes (=, +, -, @) to prevent CSV formula injection vulnerabilities.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def utc_stamp(value: Optional[str]) -> str:
    """Normalise an ISO-8601 timestamp to UTC 'YYYY-MM-DD HH:MM:SS' text.

    Returns empty string for None/empty to keep CSV output clean.
    """
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        return str(value)


def extract_conversations(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON content and extract a list of conversation dictionaries."""
    raw = content.lstrip("\ufeff")
    items = json.loads(raw)

    if isinstance(items, dict):
        for key in ("conversations", "items", "data"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError(f"{source_label}: expected a JSON array or wrapped conversation object")

    results: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source_label}: each conversation must be a JSON object")
        if not item.get("id") or str(item.get("id")).strip() == "":
            raise ValueError(f"{source_label}: conversation missing required 'id' field")
        results.append(item)

    return results


def conversation_to_row(item: Dict[str, Any]) -> List[str]:
    """Convert a single conversation object into a formatted CSV row."""
    conv_id = str(item.get("id"))
    structured: Dict[str, Any] = item.get("structured") or {}
    if not isinstance(structured, dict):
        structured = {}

    title = structured.get("title") or item.get("title") or ""
    category = structured.get("category") or item.get("category") or ""
    overview = structured.get("overview") or item.get("overview") or ""
    source = item.get("source") or ""

    # Action items count
    action_items = structured.get("action_items") or item.get("action_items") or []
    action_items_count = str(len(action_items)) if isinstance(action_items, list) else "0"

    # Transcript segments count and full transcript text
    segments = item.get("transcript_segments") or []
    turns_count = str(len(segments)) if isinstance(segments, list) else "0"

    transcript = item.get("transcript") or ""
    if not transcript and isinstance(segments, list) and segments:
        text_parts = []
        for seg in segments:
            if isinstance(seg, dict):
                speaker = seg.get("speaker") or f"Speaker {seg.get('speaker_id', '?')}"
                seg_text = seg.get("text") or ""
                text_parts.append(f"{speaker}: {seg_text}")
        transcript = "\n".join(text_parts)

    started_at = utc_stamp(item.get("started_at"))
    created_at = utc_stamp(item.get("created_at"))
    updated_at = utc_stamp(item.get("updated_at"))

    return [
        spreadsheet_text(conv_id),
        spreadsheet_text(title),
        spreadsheet_text(category),
        spreadsheet_text(overview),
        spreadsheet_text(source),
        spreadsheet_text(action_items_count),
        spreadsheet_text(turns_count),
        spreadsheet_text(started_at),
        spreadsheet_text(created_at),
        spreadsheet_text(updated_at),
        spreadsheet_text(transcript),
    ]


def convert_paths_to_csv(sources: Sequence[str | Path], output_dest: Optional[str | Path] = None) -> int:
    """Convert one or more JSON files (or stdin) to CSV format.

    Returns the number of conversations converted.
    """
    all_conversations: List[Dict[str, Any]] = []

    for src in sources:
        if str(src) == "-":
            content = sys.stdin.read()
            all_conversations.extend(extract_conversations(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_conversations.extend(extract_conversations(content, str(p)))

    rows = [list(FIELDS)]
    for conv in all_conversations:
        rows.append(conversation_to_row(conv))

    if output_dest and str(output_dest) != "-":
        out_path = Path(output_dest)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerows(rows)
    else:
        out_buf = io.StringIO()
        writer = csv.writer(out_buf)
        writer.writerows(rows)
        sys.stdout.write(out_buf.getvalue())

    return len(all_conversations)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi conversation JSON exports to a CSV spreadsheet."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Input JSON files or '-' for standard input",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Destination CSV file (defaults to stdout)",
    )
    args = parser.parse_args()

    try:
        count = convert_paths_to_csv(args.inputs, args.output)
        if args.output != "-":
            print(f"Exported {count} conversation(s) to {args.output}", file=sys.stderr)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
