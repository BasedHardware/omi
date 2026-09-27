#!/usr/bin/env python3
"""
Convert Omi conversations JSON export to a clean TSV (Tab-Separated Values) format.

Usage:
    python conversations_to_tsv.py conversations.json -o conversations.tsv
    omi --json conversation list --limit 100 | python conversations_to_tsv.py - -o conversations.tsv

Extracts conversations, start/finish timestamps, summary overview, and flattened
transcript text into single-line TSV records for fast terminal querying.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

COLUMNS: Sequence[str] = [
    "id",
    "started_at",
    "finished_at",
    "status",
    "transcript_summary",
    "transcript_segments_count",
    "transcript_text",
]


def escape_tsv_field(val: Any) -> str:
    """Sanitize and escape internal newlines and tabs to preserve 1-line-per-record TSV."""
    if val is None:
        return ""
    text = str(val).strip()
    return text.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n").replace("\t", " ")


def parse_conversations_payload(data: Any) -> List[Dict[str, Any]]:
    """Extract list of conversation items from bare array or envelope dict."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("conversations", "items", "data", "results"):
            candidate = data.get(key)
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, dict)]
    return []


def format_conversation_tsv_row(item: Dict[str, Any]) -> Dict[str, str]:
    """Format and normalize a conversation record for TSV output."""
    convo_id = str(item.get("id", "")).strip()
    started_at = str(item.get("started_at", "") or item.get("created_at", "") or "").strip()
    finished_at = str(item.get("finished_at", "") or item.get("completed_at", "") or "").strip()
    status = str(item.get("status", "") or "completed").strip()

    # Extract summary
    summary = ""
    if isinstance(item.get("structured"), dict):
        summary = str(item["structured"].get("overview", "") or item["structured"].get("title", "") or "").strip()
    elif item.get("summary"):
        summary = str(item.get("summary", "")).strip()

    # Extract transcript text
    transcript_segments = item.get("transcript_segments") or item.get("segments") or []
    seg_texts: List[str] = []
    if isinstance(transcript_segments, list):
        for seg in transcript_segments:
            if isinstance(seg, dict) and seg.get("text"):
                seg_texts.append(str(seg["text"]).strip())
            elif isinstance(seg, str):
                seg_texts.append(seg.strip())

    joined_text = " ".join(seg_texts) if seg_texts else str(item.get("transcript", "") or "").strip()

    return {
        "id": convo_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "status": status,
        "transcript_summary": escape_tsv_field(summary),
        "transcript_segments_count": str(len(seg_texts)),
        "transcript_text": escape_tsv_field(joined_text),
    }


def convert_conversations_to_tsv(raw_json_str: str, output_path: Optional[Path] = None) -> str:
    """Convert raw conversations JSON string to TSV text with atomic write safety."""
    if output_path is not None:
        parts = output_path.parts
        if ".." in parts:
            raise ValueError(f"Output path cannot contain directory traversal '..': {output_path}")

    try:
        data = json.loads(raw_json_str)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON payload: {exc}") from exc

    convos = parse_conversations_payload(data)
    rows = [format_conversation_tsv_row(c) for c in convos]

    import io
    output_stream = io.StringIO()
    writer = csv.DictWriter(output_stream, fieldnames=COLUMNS, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)

    tsv_content = output_stream.getvalue()

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        partial_path = output_path.with_suffix(".tsv.partial")
        try:
            with open(partial_path, "w", encoding="utf-8", newline="") as f:
                f.write(tsv_content)
            os.replace(partial_path, output_path)
        except Exception:
            if partial_path.exists():
                partial_path.unlink()
            raise

    return tsv_content


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Convert Omi conversations JSON to TSV.")
    parser.add_argument("input", help="Path to conversations JSON export, or '-' to read from stdin.")
    parser.add_argument("-o", "--output", help="Path for generated TSV file. Defaults to stdout.")

    args = parser.parse_args(argv)

    try:
        if args.input == "-":
            raw_data = sys.stdin.read()
        else:
            in_path = Path(args.input)
            if not in_path.is_file():
                sys.stderr.write(f"Error: Input file not found: {in_path}\n")
                return 1
            raw_data = in_path.read_text(encoding="utf-8")

        out_path = Path(args.output) if args.output else None
        tsv_result = convert_conversations_to_tsv(raw_data, out_path)

        if out_path is None:
            sys.stdout.write(tsv_result)
        else:
            sys.stderr.write(f"Successfully converted conversations to {out_path}\n")

        return 0
    except Exception as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
