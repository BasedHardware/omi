#!/usr/bin/env python3
"""Convert Omi conversations into Notion API block payloads.

Usage:
    python conversations_to_notion.py conversation.json -o notion_page.json
    omi --json conversation get <id> | python conversations_to_notion.py - --parent-id <db_id>
    python conversations_to_notion.py conversations.json --output-dir ./notion_pages/

Outputs valid Notion API JSON payloads (POST /v1/pages) with structured blocks
(heading_2, callout, bulleted_list_item, paragraph) ready for direct submission
or Notion API automation scripts.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def text_to_rich_text(content: str, bold: bool = False) -> List[Dict[str, Any]]:
    """Convert a string into a Notion rich_text array, chunking at 2000 characters."""
    if not content:
        return []
    chunks = []
    # Notion has a 2000 character limit per text block
    for i in range(0, len(content), 2000):
        chunk = content[i : i + 2000]
        obj: Dict[str, Any] = {
            "type": "text",
            "text": {"content": chunk},
        }
        if bold:
            obj["annotations"] = {"bold": True}
        chunks.append(obj)
    return chunks


def make_block(block_type: str, rich_text: List[Dict[str, Any]], extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Construct a standard Notion block object."""
    data: Dict[str, Any] = {"rich_text": rich_text}
    if extra:
        data.update(extra)
    return {
        "object": "block",
        "type": block_type,
        block_type: data,
    }


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
        raise ValueError(f"{source_label}: expected a JSON array or wrapped conversations object")

    results: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source_label}: each conversation must be a JSON object")
        if not item.get("id") or str(item.get("id")).strip() == "":
            raise ValueError(f"{source_label}: conversation missing required 'id' field")
        results.append(item)

    return results


def conversation_to_notion_payload(conv: Dict[str, Any], parent_id: Optional[str] = None) -> Dict[str, Any]:
    """Convert a single conversation into a full Notion page creation payload."""
    cid = str(conv.get("id"))
    structured = conv.get("structured") or {}
    title = str(structured.get("title") or conv.get("title") or f"Conversation {cid[:8]}").strip()
    category = str(structured.get("category") or conv.get("category") or "General").strip()
    overview = str(structured.get("overview") or conv.get("overview") or "").strip()

    children: List[Dict[str, Any]] = []

    # Callout overview block
    callout_text = f"Category: {category}"
    if overview:
        callout_text += f"\n\nOverview:\n{overview}"
    children.append(
        make_block("callout", text_to_rich_text(callout_text), {"icon": {"type": "emoji", "emoji": "🎙️"}})
    )

    # Transcript segments
    segments = conv.get("transcript_segments") or []
    if isinstance(segments, list) and segments:
        children.append(make_block("heading_2", text_to_rich_text("Transcript")))
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            text = str(seg.get("text") or "").strip()
            if not text:
                continue
            speaker = str(seg.get("speaker") or seg.get("speaker_id") or "").strip()
            rich_elements: List[Dict[str, Any]] = []
            if speaker:
                rich_elements.extend(text_to_rich_text(f"{speaker}: ", bold=True))
            rich_elements.extend(text_to_rich_text(text))
            children.append(make_block("bulleted_list_item", rich_elements))
    else:
        transcript = str(conv.get("transcript") or "").strip()
        if transcript:
            children.append(make_block("heading_2", text_to_rich_text("Transcript")))
            children.append(make_block("paragraph", text_to_rich_text(transcript)))

    payload: Dict[str, Any] = {
        "properties": {
            "Title": {
                "title": text_to_rich_text(title)
            }
        },
        "children": children,
    }

    if parent_id:
        payload["parent"] = {"database_id": parent_id}

    return payload


def convert_conversations_to_notion(
    sources: Sequence[str | Path],
    output_dest: Optional[str | Path] = None,
    output_dir: Optional[str | Path] = None,
    parent_id: Optional[str] = None,
) -> int:
    """Convert conversations to Notion block payloads."""
    all_conversations: List[Dict[str, Any]] = []

    for src in sources:
        if str(src) == "-":
            content = sys.stdin.read()
            all_conversations.extend(extract_conversations(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_conversations.extend(extract_conversations(content, str(p)))

    if output_dir:
        out_dir_path = Path(output_dir)
        out_dir_path.mkdir(parents=True, exist_ok=True)
        count = 0
        for conv in all_conversations:
            cid = str(conv.get("id"))
            safe_cid = re.sub(r"[^\w-]", "_", cid)
            payload = conversation_to_notion_payload(conv, parent_id=parent_id)
            file_path = out_dir_path / f"{safe_cid}_notion.json"
            file_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            count += 1
        return count

    payloads = [conversation_to_notion_payload(c, parent_id=parent_id) for c in all_conversations]
    final_output = json.dumps(payloads[0] if len(payloads) == 1 else payloads, indent=2, ensure_ascii=False)

    if output_dest and str(output_dest) != "-":
        out_path = Path(output_dest)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(final_output, encoding="utf-8")
    else:
        sys.stdout.write(final_output + "\n")

    return len(all_conversations)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi conversations into Notion API block payloads."
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
        help="Destination JSON file (defaults to stdout)",
    )
    parser.add_argument(
        "--output-dir",
        "-d",
        default=None,
        help="Directory to save individual Notion JSON payloads",
    )
    parser.add_argument(
        "--parent-id",
        default=None,
        help="Optional Notion database_id or page_id for the parent property",
    )
    args = parser.parse_args()

    try:
        count = convert_conversations_to_notion(args.inputs, args.output, args.output_dir, args.parent_id)
        if args.output != "-" or args.output_dir:
            dest = args.output_dir if args.output_dir else args.output
            print(f"Exported {count} conversation payload(s) for Notion to {dest}", file=sys.stderr)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
