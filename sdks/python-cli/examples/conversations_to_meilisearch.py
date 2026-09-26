#!/usr/bin/env python3
"""Convert Omi conversation JSON exports to a Meilisearch document batch.

Reads conversations exported from Omi (file or stdin), flattens transcripts,
extracts speaker lists, sanitizes primary keys to meet Meilisearch ID
specifications, and prepares a JSON document payload ready for batch indexing
via the Meilisearch Documents API (`POST /indexes/{index_uid}/documents`).

Features:
- Pure Python standard library (no external dependencies)
- Automatic fallback for `structured` metadata (title, category, overview)
- Timestamp fallback to `started_at` when `created_at` is omitted
- Auto-calculation of `duration_seconds` from `started_at` and `finished_at`
- Meilisearch-compliant document ID sanitization (regex: ^[a-zA-Z0-9-_]+$)
- Category, min-date, and min-duration client-side filtering
- Deduplication across multiple export batches
- Overwrite protection (--force to replace existing destination)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


def sanitize_meili_id(raw_id: Any) -> str:
    """Sanitize a raw conversation ID into a valid Meilisearch document primary key.

    Meilisearch requires document IDs to match: ^[a-zA-Z0-9-_]+$
    Replaces any invalid characters with hyphens, collapses consecutive hyphens,
    and strips leading/trailing punctuation.
    """
    if raw_id is None:
        return "unknown_doc"

    text = str(raw_id).strip()
    if not text:
        return "unknown_doc"

    # Replace any character other than alphanumeric, underscore, or hyphen
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", text)
    # Collapse multiple consecutive hyphens
    cleaned = re.sub(r"-+", "-", cleaned)
    # Strip leading/trailing hyphens or underscores
    cleaned = cleaned.strip("-_")

    return cleaned or "doc"


def parse_iso_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """Parse an ISO 8601 datetime string into a timezone-aware UTC datetime."""
    if not dt_str or not isinstance(dt_str, str):
        return None

    clean_str = dt_str.strip()
    # Normalize trailing Z to UTC offset
    if clean_str.endswith("Z"):
        clean_str = clean_str[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(clean_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def extract_transcript_text(conv: Dict[str, Any]) -> str:
    """Extract and flatten conversation transcript into searchable text."""
    # 1. Direct transcript string
    if "transcript" in conv and isinstance(conv["transcript"], str) and conv["transcript"].strip():
        return conv["transcript"].strip()

    # 2. Structured segments / turns
    lines: List[str] = []
    segments = conv.get("transcript_segments") or conv.get("segments") or []
    if isinstance(segments, list):
        for seg in segments:
            if isinstance(seg, dict):
                speaker = seg.get("speaker") or seg.get("speaker_name") or "Unknown"
                text = seg.get("text") or seg.get("content") or ""
                text = str(text).strip()
                if text:
                    lines.append(f"{speaker}: {text}")
            elif isinstance(seg, str) and seg.strip():
                lines.append(seg.strip())

    return "\n".join(lines)


def extract_speakers(conv: Dict[str, Any]) -> List[str]:
    """Collect distinct list of speakers in the conversation."""
    speakers: List[str] = []
    seen = set()

    # Check explicit speaker list
    if "speakers" in conv and isinstance(conv["speakers"], list):
        for s in conv["speakers"]:
            name = str(s).strip()
            if name and name not in seen:
                seen.add(name)
                speakers.append(name)
        if speakers:
            return speakers

    # Fallback to segments
    segments = conv.get("transcript_segments") or conv.get("segments") or []
    if isinstance(segments, list):
        for seg in segments:
            if isinstance(seg, dict):
                s = seg.get("speaker") or seg.get("speaker_name")
                if s:
                    name = str(s).strip()
                    if name and name not in seen:
                        seen.add(name)
                        speakers.append(name)

    return speakers


def extract_conversations(data: Any) -> List[Dict[str, Any]]:
    """Extract list of conversation dictionaries from JSON string, dict, or list."""
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON data: {exc}") from exc
    else:
        parsed = data

    if isinstance(parsed, dict):
        if "conversations" in parsed and isinstance(parsed["conversations"], list):
            items = parsed["conversations"]
        elif "items" in parsed and isinstance(parsed["items"], list):
            items = parsed["items"]
        elif "data" in parsed and isinstance(parsed["data"], list):
            items = parsed["data"]
        elif "result" in parsed and isinstance(parsed["result"], list):
            items = parsed["result"]
        elif "id" in parsed or "title" in parsed or "structured" in parsed:
            items = [parsed]
        else:
            raise ValueError("Expected a JSON array or object containing 'conversations'")
    elif isinstance(parsed, list):
        items = parsed
    else:
        raise ValueError(f"Unexpected JSON root type: {type(parsed).__name__}")

    result: List[Dict[str, Any]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"Item at index {idx} is not a valid JSON object")
        result.append(item)

    return result


def transform_to_meilisearch(
    conversations: Sequence[Dict[str, Any]],
    category_filter: Optional[str] = None,
    min_date: Optional[str] = None,
    min_duration: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Transform conversations into Meilisearch documents list."""
    min_dt = parse_iso_datetime(min_date) if min_date else None
    cat_lower = category_filter.strip().lower() if category_filter else None

    seen_ids = set()
    documents: List[Dict[str, Any]] = []

    for item in conversations:
        raw_id = item.get("id")
        dedup_key = str(raw_id) if raw_id is not None else str(item.get("title") or "")
        if dedup_key in seen_ids:
            continue
        seen_ids.add(dedup_key)

        structured = item.get("structured") or {}
        if not isinstance(structured, dict):
            structured = {}

        # Resolve title, category, and overview with fallback to structured
        title = str(item.get("title") or structured.get("title") or "Untitled Conversation").strip()
        item_cat = str(item.get("category") or structured.get("category") or "general").strip()
        summary = str(item.get("summary") or item.get("overview") or structured.get("overview") or "").strip()

        # Apply category filter
        if cat_lower and item_cat.lower() != cat_lower:
            continue

        # Apply date filter with started_at fallback
        date_str = item.get("created_at") or item.get("started_at")
        if min_dt:
            item_dt = parse_iso_datetime(date_str)
            if item_dt and item_dt < min_dt:
                continue

        # Apply duration filter with started_at -> finished_at fallback
        duration = item.get("duration") or item.get("duration_seconds")
        if duration is None and item.get("started_at") and item.get("finished_at"):
            st = parse_iso_datetime(item.get("started_at"))
            fn = parse_iso_datetime(item.get("finished_at"))
            if st and fn:
                duration = int(max(0, (fn - st).total_seconds()))

        try:
            duration_int = int(duration or 0)
        except (ValueError, TypeError):
            duration_int = 0

        if min_duration is not None and duration_int < min_duration:
            continue

        doc_id = sanitize_meili_id(raw_id)
        transcript = extract_transcript_text(item)
        speakers = extract_speakers(item)

        doc: Dict[str, Any] = {
            "id": doc_id,
            "title": title,
            "category": item_cat,
            "duration_seconds": duration_int,
        }

        if raw_id is not None and str(raw_id) != doc_id:
            doc["original_id"] = str(raw_id)

        if item.get("created_at"):
            doc["created_at"] = str(item["created_at"])
        elif item.get("started_at"):
            doc["created_at"] = str(item["started_at"])

        if item.get("started_at"):
            doc["started_at"] = str(item["started_at"])

        if item.get("finished_at"):
            doc["finished_at"] = str(item["finished_at"])

        if summary:
            doc["summary"] = summary

        if transcript:
            doc["transcript"] = transcript

        if speakers:
            doc["speakers"] = speakers

        if item.get("source"):
            doc["source"] = str(item["source"]).strip()

        if item.get("language"):
            doc["language"] = str(item["language"]).strip()

        documents.append(doc)

    return documents


def convert_conversations_to_meilisearch(
    inputs: Sequence[str],
    category_filter: Optional[str] = None,
    min_date: Optional[str] = None,
    min_duration: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Load inputs, extract, filter, and transform to Meilisearch documents."""
    all_raw: List[Dict[str, Any]] = []

    for inp in inputs:
        if inp == "-":
            raw_text = sys.stdin.read()
        else:
            p = Path(inp)
            if not p.is_file():
                raise FileNotFoundError(f"File not found: {inp}")
            raw_text = p.read_bytes().decode("utf-8-sig")

        all_raw.extend(extract_conversations(raw_text))

    docs = transform_to_meilisearch(
        all_raw,
        category_filter=category_filter,
        min_date=min_date,
        min_duration=min_duration,
    )

    stats = {
        "total_read": len(all_raw),
        "total_documents": len(docs),
    }

    return docs, stats


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi conversation JSON exports to a Meilisearch document batch.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  omi --json conversation list --include-transcript --limit 100 | python conversations_to_meilisearch.py - -o meili_docs.json
  python conversations_to_meilisearch.py convos.json -o meili_docs.json --category work
  python conversations_to_meilisearch.py part1.json part2.json -o combined_docs.json --force
""",
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        metavar="INPUT",
        help="One or more JSON files exported from 'omi conversation list', or '-' for stdin.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        metavar="FILE",
        help="Destination JSON file for Meilisearch documents (default: write to stdout).",
    )
    parser.add_argument(
        "--category",
        default=None,
        metavar="CAT",
        help="Filter conversations matching a specific category (case-insensitive).",
    )
    parser.add_argument(
        "--min-date",
        default=None,
        metavar="ISO_DATE",
        help="Filter conversations created/started on or after this ISO date (e.g. 2026-09-01).",
    )
    parser.add_argument(
        "--min-duration",
        type=int,
        default=None,
        metavar="SECS",
        help="Filter conversations with duration in seconds >= this value.",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite destination file if it already exists.",
    )

    args = parser.parse_args(argv)

    out_path = Path(args.output) if args.output else None
    if out_path and out_path.exists() and not args.force:
        print(f"Error: Output file '{args.output}' already exists. Use --force to overwrite.", file=sys.stderr)
        return 1

    try:
        docs, stats = convert_conversations_to_meilisearch(
            args.inputs,
            category_filter=args.category,
            min_date=args.min_date,
            min_duration=args.min_duration,
        )
    except (FileNotFoundError, ValueError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    formatted_json = json.dumps(docs, indent=2, ensure_ascii=False)
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(formatted_json, encoding="utf-8")
        print(f"Read {stats['total_read']} conversations, exported {stats['total_documents']} Meilisearch document(s) to '{args.output}'.")
    else:
        sys.stdout.write(formatted_json + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
