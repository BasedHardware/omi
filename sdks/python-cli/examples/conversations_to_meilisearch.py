#!/usr/bin/env python3
"""Convert Omi conversations JSON exports into Meilisearch document batches.

Usage:
    # From a saved file to output JSON:
    python conversations_to_meilisearch.py conversations.json -o meili_docs.json

    # Piped directly from omi-cli:
    omi --json conversation list --limit 200 | python conversations_to_meilisearch.py - -o meili_docs.json

    # Ingest directly into Meilisearch index:
    curl -X POST -H "Content-Type: application/json" \\
         -H "Authorization: Bearer $MEILI_MASTER_KEY" \\
         -d @meili_docs.json \\
         http://localhost:7700/indexes/omi_conversations/documents

Converts conversations into Meilisearch-compliant document records:
    [
        {
            "id": "conv_12345",
            "title": "Sprint Planning Meeting",
            "created_at": "2026-09-24T10:00:00Z",
            "duration_seconds": 1800,
            "category": "work",
            "speakers": ["Alice", "Bob"],
            "summary": "Discussed roadmap and assigned milestones.",
            "transcript": "Alice: Welcome everyone. Bob: Ready."
        }
    ]

Key features:
    - Pure Python 3.10+ standard library (zero external dependencies).
    - Primary key sanitization: ensures IDs comply with Meilisearch rules (^[a-zA-Z0-9_-]+$).
    - Structured transcript aggregation: extracts dialogue from transcript segments or turns.
    - Multi-file deduplication by conversation ID.
    - Streaming standard input (-) for UNIX command chaining.
    - Safe overwrite guard (--force required to replace existing files).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def sanitize_meili_id(val: Any) -> str:
    """Sanitize string into a valid Meilisearch document primary key.

    Meilisearch primary keys must only contain alphanumeric characters (a-zA-Z0-9),
    hyphens (-), and underscores (_). Any unsupported characters are converted to hyphens.
    """
    raw_str = str(val).strip() if val is not None else ""
    if not raw_str:
        return "unknown_doc"
    # Replace invalid chars with hyphen
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "-", raw_str)
    # Collapse multiple consecutive hyphens
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned or "doc"


def parse_iso_datetime(val: Any) -> Optional[datetime]:
    """Parse an ISO 8601 string into a UTC datetime, or return None if invalid."""
    if not isinstance(val, str) or not val.strip():
        return None
    cleaned = val.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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
        elif "id" in parsed or "title" in parsed:
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
        dedup_key = str(raw_id) if raw_id is not None else item.get("title", "")
        if dedup_key in seen_ids:
            continue
        seen_ids.add(dedup_key)

        # Apply category filter
        item_cat = str(item.get("category") or "general").strip()
        if cat_lower and item_cat.lower() != cat_lower:
            continue

        # Apply date filter
        created_str = item.get("created_at")
        if min_dt:
            item_dt = parse_iso_datetime(created_str)
            if item_dt and item_dt < min_dt:
                continue

        # Apply duration filter
        duration = item.get("duration") or item.get("duration_seconds") or 0
        try:
            duration_int = int(duration)
        except (ValueError, TypeError):
            duration_int = 0

        if min_duration is not None and duration_int < min_duration:
            continue

        doc_id = sanitize_meili_id(raw_id)
        transcript = extract_transcript_text(item)
        speakers = extract_speakers(item)

        doc: Dict[str, Any] = {
            "id": doc_id,
            "title": str(item.get("title") or "Untitled Conversation").strip(),
            "category": item_cat,
            "duration_seconds": duration_int,
        }

        if raw_id is not None and str(raw_id) != doc_id:
            doc["original_id"] = str(raw_id)

        if created_str:
            doc["created_at"] = str(created_str)

        if "finished_at" in item and item["finished_at"]:
            doc["finished_at"] = str(item["finished_at"])

        if "summary" in item and item["summary"]:
            doc["summary"] = str(item["summary"]).strip()

        if transcript:
            doc["transcript"] = transcript

        if speakers:
            doc["speakers"] = speakers

        if "source" in item and item["source"]:
            doc["source"] = str(item["source"]).strip()

        if "language" in item and item["language"]:
            doc["language"] = str(item["language"]).strip()

        documents.append(doc)

    return documents


def load_input_sources(inputs: Sequence[str]) -> List[Dict[str, Any]]:
    """Load and merge conversations from file paths or stdin."""
    all_convs: List[Dict[str, Any]] = []
    for src in inputs:
        if src == "-":
            raw = sys.stdin.read()
            if raw.strip():
                all_convs.extend(extract_conversations(raw))
        else:
            path = Path(src)
            if not path.is_file():
                raise FileNotFoundError(f"Input file not found: {path}")
            raw = path.read_text(encoding="utf-8")
            if raw.strip():
                all_convs.extend(extract_conversations(raw))
    return all_convs


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Convert Omi conversation JSON exports to Meilisearch search engine documents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        default=["-"],
        help="Input JSON file path(s), or '-' to read from standard input (default: -).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output destination path for the Meilisearch JSON document array (default: stdout).",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing output file if it already exists.",
    )
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="Filter conversations to a specific category (case-insensitive).",
    )
    parser.add_argument(
        "--min-date",
        type=str,
        default=None,
        help="Filter conversations created on or after this ISO-8601 timestamp.",
    )
    parser.add_argument(
        "--min-duration",
        type=int,
        default=None,
        help="Filter conversations with at least this duration in seconds.",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="Number of spaces for JSON indentation (default: 2; set 0 for compact).",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.output and args.output.exists() and not args.force:
        sys.stderr.write(f"Error: Output file '{args.output}' already exists. Use --force to overwrite.\n")
        return 1

    try:
        conversations = load_input_sources(args.inputs)
    except Exception as exc:
        sys.stderr.write(f"Error reading input: {exc}\n")
        return 1

    documents = transform_to_meilisearch(
        conversations=conversations,
        category_filter=args.category,
        min_date=args.min_date,
        min_duration=args.min_duration,
    )

    indent = args.indent if args.indent > 0 else None
    out_json = json.dumps(documents, indent=indent, ensure_ascii=False) + "\n"

    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(out_json, encoding="utf-8")
        except OSError as exc:
            sys.stderr.write(f"Error writing output file: {exc}\n")
            return 1
    else:
        sys.stdout.write(out_json)

    return 0


if __name__ == "__main__":
    sys.exit(main())
