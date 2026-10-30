#!/usr/bin/env python3
"""
Convert Omi conversation JSON exports to clean, line-delimited JSON (JSONL).

Designed for vector-store ingestion, pandas/Spark processing, jq pipelines,
and LLM fine-tuning datasets.

Usage:
    python conversations_to_jsonl.py input.json -o output.jsonl
    python conversations_to_jsonl.py input.json --include-transcript -o output.jsonl
    python conversations_to_jsonl.py input.json --category work,meeting -o output.jsonl
    cat input.json | python conversations_to_jsonl.py - > output.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

DONE_WORDS: Set[str] = {"true", "yes", "1", "done", "completed"}


def strip_surrogates(value: str) -> str:
    """Drop unpaired surrogate code points that cannot be encoded as UTF-8."""
    return value.encode("utf-8", "ignore").decode("utf-8")


def parse_json_safely(raw_text: str) -> Any:
    """Parse JSON string safely, stripping leading UTF-8 BOM if present."""
    if not raw_text:
        return None
    clean = raw_text.lstrip("\ufeff")
    return json.loads(clean)


def is_completed(value: Any) -> bool:
    """Normalize completion status for loosely typed API and LLM exports."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in DONE_WORDS
    return False


def normalize_iso_utc(value: Any) -> Optional[str]:
    """Normalize a timestamp to an ISO-8601 UTC string (YYYY-MM-DDTHH:MM:SSZ).

    If the timestamp cannot be parsed or causes an overflow boundary error
    (e.g. year > 9999), returns its original string representation without
    aborting the export. Returns None for None or empty strings.
    """
    if value is None or value == "":
        return None
    val_str = str(value).strip()
    if not val_str:
        return None

    try:
        # Replace terminal Z with explicit +00:00 for fromisoformat
        clean_str = val_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, OverflowError, TypeError):
        return strip_surrogates(val_str)


def normalize_action_item(item: Any) -> Dict[str, Any]:
    """Normalize an action item to a stable {description, completed} dict."""
    if isinstance(item, dict):
        desc = item.get("description") or item.get("text") or item.get("content") or ""
        completed = is_completed(item.get("completed"))
        return {
            "description": strip_surrogates(str(desc)),
            "completed": completed,
        }
    if isinstance(item, str):
        return {
            "description": strip_surrogates(item),
            "completed": False,
        }
    return {
        "description": strip_surrogates(str(item)) if item is not None else "",
        "completed": False,
    }


def normalize_transcript_segment(seg: Any) -> Dict[str, Any]:
    """Normalize a transcript segment to {speaker, start, end, text}."""
    if not isinstance(seg, dict):
        return {
            "speaker": "",
            "start": 0.0,
            "end": 0.0,
            "text": strip_surrogates(str(seg)) if seg is not None else "",
        }

    speaker = seg.get("speaker") or seg.get("speaker_id") or ""
    text = seg.get("text") or ""
    start = seg.get("start")
    end = seg.get("end")

    try:
        start_val = float(start) if start is not None else 0.0
    except (ValueError, TypeError):
        start_val = 0.0

    try:
        end_val = float(end) if end is not None else 0.0
    except (ValueError, TypeError):
        end_val = 0.0

    return {
        "speaker": strip_surrogates(str(speaker)),
        "start": start_val,
        "end": end_val,
        "text": strip_surrogates(str(text)),
    }


def extract_conversations(data: Any) -> List[Dict[str, Any]]:
    """Unwrap conversations from list, wrapped dictionaries, or single object.

    Handles envelopes:
      - Bare list: [ {...}, {...} ]
      - Envelopes: {"conversations": [...]}, {"items": [...]}, {"data": [...]}, {"results": [...]}
      - Single conversation: {"id": "...", ...}
    API error responses (such as {"detail": "..."} or {"error": "..."}) are
    rejected to prevent phantom records.
    """
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    if isinstance(data, dict):
        # 1. Check wrapped envelopes
        for key in ("conversations", "items", "data", "results"):
            val = data.get(key)
            if isinstance(val, list):
                return [item for item in val if isinstance(item, dict)]

        # 2. Check if this is an API error payload
        if ("detail" in data or "error" in data) and not any(
            k in data for k in ("id", "transcript_segments", "structured", "started_at")
        ):
            return []

        # 3. Check if this dict itself is a single conversation
        if any(key in data for key in ("id", "transcript_segments", "structured", "started_at", "created_at")):
            return [data]

    return []


def conversation_to_jsonl_record(conv: Dict[str, Any], include_transcript: bool = False) -> Dict[str, Any]:
    """Transform an Omi conversation dictionary into a stable JSONL schema record."""
    conv_id = conv.get("id") or ""
    source = conv.get("source") or "omi"

    structured = conv.get("structured")
    if not isinstance(structured, dict):
        structured = {}

    title = structured.get("title") or conv.get("title") or ""
    category = structured.get("category") or conv.get("category") or "general"
    overview = structured.get("overview") or conv.get("overview") or ""

    started_at = normalize_iso_utc(conv.get("started_at"))
    finished_at = normalize_iso_utc(conv.get("finished_at") or conv.get("ended_at"))

    # Action items normalization
    raw_action_items = structured.get("action_items") or conv.get("action_items") or []
    if isinstance(raw_action_items, list):
        action_items = [normalize_action_item(item) for item in raw_action_items]
    else:
        action_items = [normalize_action_item(raw_action_items)]

    record: Dict[str, Any] = {
        "id": strip_surrogates(str(conv_id)),
        "title": strip_surrogates(str(title)),
        "category": strip_surrogates(str(category)),
        "started_at": started_at,
        "finished_at": finished_at,
        "source": strip_surrogates(str(source)),
        "overview": strip_surrogates(str(overview)),
        "action_items": action_items,
    }

    if include_transcript:
        raw_segments = conv.get("transcript_segments") or []
        if isinstance(raw_segments, list):
            record["transcript_segments"] = [normalize_transcript_segment(s) for s in raw_segments]
        else:
            record["transcript_segments"] = []

    return record


def filter_by_category(conversations: List[Dict[str, Any]], categories: Optional[Set[str]]) -> List[Dict[str, Any]]:
    """Filter conversations by category (case-insensitive).

    If a record has a non-dict or missing structure, it passes untouched so
    one irregular record does not abort or drop valid data.
    """
    if not categories:
        return conversations

    filtered: List[Dict[str, Any]] = []
    for conv in conversations:
        structured = conv.get("structured")
        cat = ""
        if isinstance(structured, dict):
            cat = str(structured.get("category") or "")
        if not cat:
            cat = str(conv.get("category") or "")

        cat_clean = cat.strip().lower()
        if not cat_clean or cat_clean in categories:
            filtered.append(conv)

    return filtered


def convert_conversations_to_jsonl(
    data: Any,
    include_transcript: bool = False,
    categories: Optional[Set[str]] = None,
) -> List[str]:
    """Convert input conversation payload into serialized JSONL strings."""
    conversations = extract_conversations(data)
    if categories:
        conversations = filter_by_category(conversations, categories)

    lines: List[str] = []
    for conv in conversations:
        record = conversation_to_jsonl_record(conv, include_transcript=include_transcript)
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        lines.append(line)

    return lines


def write_jsonl_exclusive(output_path: Path, lines: Sequence[str]) -> None:
    """Write lines atomically and exclusively to output_path.

    Raises FileExistsError if output_path already exists.
    If an I/O error occurs mid-write, any partial file is cleaned up.
    """
    if output_path.exists():
        raise FileExistsError(f"Output file already exists: {output_path}")

    parent = output_path.parent
    if parent and not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)

    temp_path = output_path.with_name(f".{output_path.name}.tmp.{os.getpid()}")
    try:
        # Open with exclusive creation flag
        with open(temp_path, "x", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")
        # Note: output_path.exists() is an advisory pre-check against accidental overwrite;
        # os.replace() replaces unconditionally on POSIX and modern Windows.
        os.replace(temp_path, output_path)
    except Exception:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise


def parse_category_arg(cat_str: Optional[str]) -> Optional[Set[str]]:
    """Parse comma-separated category string into a lowercase set."""
    if not cat_str:
        return None
    cats = {c.strip().lower() for c in cat_str.split(",") if c.strip()}
    return cats if cats else None


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi conversation JSON exports to clean, line-delimited JSON (JSONL)."
    )
    parser.add_argument(
        "input",
        help="Path to JSON file (or '-' for stdin).",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Target output .jsonl file. If omitted or '-', writes to stdout.",
        default=None,
    )
    parser.add_argument(
        "--include-transcript",
        action="store_true",
        help="Include full transcript segments in each conversation line.",
    )
    parser.add_argument(
        "--category",
        help="Comma-separated category filter (e.g. 'work,meeting'). Case-insensitive.",
        default=None,
    )

    args = parser.parse_args(argv)

    # 1. Read input
    raw_content = ""
    if args.input == "-":
        raw_content = sys.stdin.read()
    else:
        input_file = Path(args.input)
        if not input_file.exists():
            sys.stderr.write(f"Error: Input file does not exist: {input_file}\n")
            return 1
        try:
            raw_content = input_file.read_text(encoding="utf-8-sig")
        except Exception as e:
            sys.stderr.write(f"Error: Failed to read input file: {e}\n")
            return 1

    if not raw_content.strip():
        # Empty input results in zero output
        lines: List[str] = []
    else:
        try:
            parsed_data = parse_json_safely(raw_content)
        except json.JSONDecodeError as e:
            sys.stderr.write(f"Error: Invalid JSON input: {e}\n")
            return 1

        categories = parse_category_arg(args.category)
        lines = convert_conversations_to_jsonl(
            parsed_data,
            include_transcript=args.include_transcript,
            categories=categories,
        )

    # 2. Write output
    if not args.output or args.output == "-":
        for line in lines:
            sys.stdout.write(line + "\n")
        sys.stdout.flush()
    else:
        out_path = Path(args.output)
        try:
            write_jsonl_exclusive(out_path, lines)
        except FileExistsError as e:
            sys.stderr.write(f"Error: {e}\n")
            return 1
        except Exception as e:
            sys.stderr.write(f"Error: Failed to write output: {e}\n")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
