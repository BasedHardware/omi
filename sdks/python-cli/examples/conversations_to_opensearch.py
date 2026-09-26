#!/usr/bin/env python3
"""Convert Omi conversation JSON exports into OpenSearch / Elasticsearch bulk ndjson format.

Usage:
    # Basic export from saved conversations JSON:
    python conversations_to_opensearch.py conversations.json -o bulk.ndjson

    # Piped directly from omi-cli:
    omi --json conversation list --limit 100 | python conversations_to_opensearch.py - -o bulk.ndjson

    # Custom target index name:
    python conversations_to_opensearch.py conversations.json -o bulk.ndjson --index-name omi_my_conversations

    # Multi-file deduplication with overwrite protection:
    python conversations_to_opensearch.py day1.json day2.json -o bulk.ndjson --force

Format:
    Outputs standard OpenSearch / Elasticsearch bulk format (newline-delimited JSON):
    {"index": {"_index": "omi_conversations", "_id": "<conv_id>"}}
    {"conversation_id": "<conv_id>", "title": "...", "summary": "...", ...}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


def parse_conversations_data(data: Any) -> List[Dict[str, Any]]:
    """Parse raw JSON input into a list of conversation dictionaries."""
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON data: {exc}") from exc
    else:
        parsed = data

    if isinstance(parsed, dict):
        items = (
            parsed.get("conversations")
            or parsed.get("items")
            or parsed.get("data")
            or parsed.get("result")
            or [parsed]
        )
    elif isinstance(parsed, list):
        items = parsed
    else:
        raise ValueError("Expected a JSON object or array of conversations")

    if not isinstance(items, list):
        raise ValueError("Conversations must resolve to a list")

    records: List[Dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            records.append(item)
    return records


def format_conversation_for_opensearch(item: Dict[str, Any]) -> Dict[str, Any]:
    """Format and normalize conversation fields into an OpenSearch document body."""
    raw_id = str(item.get("id") or item.get("uid") or "").strip()
    if not raw_id:
        raise ValueError("Conversation record missing required 'id' field")

    # Title fallback
    structured = item.get("structured") or {}
    title = str(
        structured.get("title")
        or item.get("title")
        or item.get("name")
        or ""
    ).strip()

    overview = str(
        structured.get("overview")
        or item.get("overview")
        or item.get("summary")
        or ""
    ).strip()

    category = str(
        structured.get("category")
        or item.get("category")
        or "conversation"
    ).strip()

    action_items_raw = structured.get("action_items") or item.get("action_items") or []
    action_items: List[str] = []
    if isinstance(action_items_raw, list):
        for ai in action_items_raw:
            if isinstance(ai, dict):
                desc = ai.get("description") or ai.get("text") or ""
                if desc:
                    action_items.append(str(desc).strip())
            elif isinstance(ai, str) and ai.strip():
                action_items.append(ai.strip())

    segments_raw = item.get("transcript_segments") or item.get("segments") or []
    transcript_text_parts: List[str] = []
    if isinstance(segments_raw, list):
        for seg in segments_raw:
            if isinstance(seg, dict):
                t = str(seg.get("text") or "").strip()
                speaker = str(seg.get("speaker") or "").strip()
                if t:
                    if speaker:
                        transcript_text_parts.append(f"{speaker}: {t}")
                    else:
                        transcript_text_parts.append(t)

    full_transcript = " ".join(transcript_text_parts)

    doc: Dict[str, Any] = {
        "conversation_id": raw_id,
        "title": title,
        "overview": overview,
        "category": category,
        "action_items": action_items,
        "transcript": full_transcript,
        "created_at": item.get("created_at"),
        "started_at": item.get("started_at"),
        "finished_at": item.get("finished_at"),
    }
    return doc


def generate_bulk_ndjson(
    inputs: Sequence[str],
    index_name: str = "omi_conversations",
) -> Tuple[str, int]:
    """Load, deduplicate by ID, and generate OpenSearch _bulk ndjson payload string."""
    dedup: Dict[str, Dict[str, Any]] = {}

    for inp in inputs:
        if inp == "-":
            raw_content = sys.stdin.read()
        else:
            p = Path(inp)
            if not p.is_file():
                raise FileNotFoundError(f"Input file not found: {inp}")
            raw_content = p.read_bytes().decode("utf-8-sig")

        convs = parse_conversations_data(raw_content)
        for c in convs:
            cid = str(c.get("id") or c.get("uid") or "").strip()
            if cid:
                dedup[cid] = c

    lines: List[str] = []
    for conv in dedup.values():
        doc = format_conversation_for_opensearch(conv)
        cid = doc["conversation_id"]
        action_header = json.dumps({"index": {"_index": index_name, "_id": cid}}, ensure_ascii=False)
        doc_body = json.dumps(doc, ensure_ascii=False)
        lines.append(action_header)
        lines.append(doc_body)

    # OpenSearch bulk API expects trailing newline
    ndjson_content = "\n".join(lines) + ("\n" if lines else "")
    return ndjson_content, len(dedup)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi conversation JSON exports to OpenSearch / Elasticsearch bulk ndjson.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  omi --json conversation list --limit 100 | python conversations_to_opensearch.py - -o bulk.ndjson
  python conversations_to_opensearch.py conversations.json -o bulk.ndjson --index-name my_index
  python conversations_to_opensearch.py c1.json c2.json -o bulk.ndjson --force
""",
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        metavar="INPUT",
        help="One or more conversation JSON files exported from 'omi --json conversation list', or '-' for stdin.",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        metavar="FILE",
        help="Output .ndjson file path.",
    )
    parser.add_argument(
        "--index-name",
        default="omi_conversations",
        metavar="INDEX",
        help="Target OpenSearch / Elasticsearch index name (default: 'omi_conversations').",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite output file if it already exists.",
    )

    args = parser.parse_args()

    out_path = Path(args.output)
    if out_path.exists() and not args.force:
        print(f"Error: Destination file '{args.output}' already exists. Use --force to overwrite.", file=sys.stderr)
        sys.exit(1)

    try:
        content, count = generate_bulk_ndjson(args.inputs, index_name=args.index_name)
    except (FileNotFoundError, ValueError) as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    print(f"Exported {count} conversation(s) to '{args.output}' ({len(content.splitlines())} lines).")


if __name__ == "__main__":
    main()
