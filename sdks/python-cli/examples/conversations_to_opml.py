"""
Convert Omi conversation JSON exports to clean OPML 2.0 outlines for Workflowy, Logseq, OmniFocus, or Dynalist.

Usage:
    # Pipe directly from omi CLI
    omi --json conversation list --include-transcript | python conversations_to_opml.py - conversations.opml

    # Export a saved JSON export
    python conversations_to_opml.py conversations.json conversations.opml

    # Filter specific categories
    python conversations_to_opml.py conversations.json conversations.opml --category work,general

    # Flat export without nested transcripts/details
    python conversations_to_opml.py conversations.json conversations.opml --flat
"""

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def parse_args():
    parser = argparse.ArgumentParser(description="Convert Omi Conversations JSON to OPML 2.0")
    parser.add_argument("input", help="Input JSON file (or '-' for stdin)")
    parser.add_argument("output", help="Output OPML file")
    parser.add_argument(
        "--category",
        "-c",
        type=str,
        default=None,
        help="Filter by category (comma-separated list, e.g. 'work,general').",
    )
    parser.add_argument(
        "--flat",
        action="store_true",
        help="Export high-level conversation outlines only without nested sections.",
    )
    return parser.parse_args()


def strip_surrogates(value: str) -> str:
    """Drop unpaired surrogate code points that cannot be encoded as UTF-8 / XML."""
    if not isinstance(value, str):
        return str(value)
    return value.encode("utf-8", "ignore").decode("utf-8")


def safe_get(item: Dict[str, Any], keys: List[str], default: Any = "") -> Any:
    """Safely retrieves the first non-null key from a dictionary."""
    if not isinstance(item, dict):
        return default
    for k in keys:
        if k in item and item[k] is not None:
            return item[k]
    return default


def format_timestamp(seconds: Any) -> str:
    """Format seconds into MM:SS or HH:MM:SS format."""
    if seconds is None:
        return "00:00"
    try:
        total_seconds = int(float(seconds))
    except (ValueError, TypeError):
        return "00:00"
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def extract_conversations(data: Any) -> List[Dict[str, Any]]:
    """Unwrap conversation records from bare arrays or wrapped envelopes."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("conversations", "items", "data"):
            val = data.get(key)
            if isinstance(val, list):
                return [item for item in val if isinstance(item, dict)]
        if any(key in data for key in ("id", "started_at", "structured", "transcript_segments")):
            return [data]
        return []
    return []


def filter_conversations(items: List[Dict[str, Any]], category_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Filter conversation items by category."""
    if not category_filter:
        return items
    target_cats = {c.strip().lower() for c in category_filter.split(",") if c.strip()}
    filtered: List[Dict[str, Any]] = []
    for it in items:
        structured = it.get("structured") or {}
        cat = str(safe_get(structured, ["category"], "")).strip().lower()
        if cat in target_cats:
            filtered.append(it)
    return filtered


def build_conversation_outline(conv: Dict[str, Any], flat: bool = False) -> ET.Element:
    """Builds a hierarchical outline node for an Omi conversation."""
    structured = conv.get("structured") or {}
    if not isinstance(structured, dict):
        structured = {}

    title = strip_surrogates(str(structured.get("title") or "Untitled Conversation")).strip()
    category = strip_surrogates(str(structured.get("category") or "")).strip()
    started_at = strip_surrogates(str(conv.get("started_at") or "")).strip()
    conv_id = strip_surrogates(str(conv.get("id") or "")).strip()

    attribs: Dict[str, str] = {"text": title}
    if started_at:
        attribs["created"] = started_at
    if category:
        attribs["category"] = category
    if conv_id:
        attribs["_id"] = conv_id

    conv_outline = ET.Element("outline", attribs)

    if flat:
        return conv_outline

    # 1. Overview Section
    overview = strip_surrogates(str(structured.get("overview") or "")).strip()
    if overview:
        clean_overview = overview.replace("\r\n", " ").replace("\n", " ")
        ET.SubElement(conv_outline, "outline", {"text": f"Overview: {clean_overview}"})

    # 2. Action Items Section
    action_items = structured.get("action_items") or []
    if isinstance(action_items, list) and action_items:
        ai_parent = ET.SubElement(conv_outline, "outline", {"text": "Action Items"})
        for item in action_items:
            desc = strip_surrogates(str(safe_get(item, ["description", "text", "title"], "Untitled Task"))).strip()
            is_comp = safe_get(item, ["completed", "is_completed"], False)
            if isinstance(is_comp, str):
                is_comp = is_comp.lower() in ("true", "yes", "1", "done", "completed")
            status = "completed" if is_comp else "open"

            ai_attribs = {"text": desc, "_status": status}
            due = safe_get(item, ["due_at", "due_date", "due"], "")
            if due:
                ai_attribs["due"] = strip_surrogates(str(due))
            ET.SubElement(ai_parent, "outline", ai_attribs)

    # 3. Transcript Segments Section
    segments = conv.get("transcript_segments") or []
    if isinstance(segments, list) and segments:
        transcript_parent = ET.SubElement(conv_outline, "outline", {"text": "Transcript"})
        for seg in segments:
            speaker = strip_surrogates(str(safe_get(seg, ["speaker"], "Speaker"))).strip()
            text = strip_surrogates(str(safe_get(seg, ["text"], ""))).strip().replace("\r\n", " ").replace("\n", " ")
            start = format_timestamp(safe_get(seg, ["start"], None))
            if text:
                line = f"[{start}] {speaker}: {text}"
                ET.SubElement(transcript_parent, "outline", {"text": line})

    return conv_outline


def create_opml(conversations: List[Dict[str, Any]], flat: bool = False, title: str = "Omi Conversations") -> ET.Element:
    """Create an OPML 2.0 XML tree from a list of conversation dictionaries."""
    opml = ET.Element("opml", version="2.0")

    # Head
    head = ET.SubElement(opml, "head")
    ET.SubElement(head, "title").text = strip_surrogates(title)
    ET.SubElement(head, "dateCreated").text = datetime.now(timezone.utc).isoformat()

    body = ET.SubElement(opml, "body")

    for conv in conversations:
        conv_elem = build_conversation_outline(conv, flat=flat)
        body.append(conv_elem)

    return opml


def get_opml_string(elem: ET.Element) -> str:
    """Serializes XML Element to indented UTF-8 OPML string with XML declaration."""
    if hasattr(ET, "indent"):
        ET.indent(elem, space="  ", level=0)
    xml_bytes = ET.tostring(elem, encoding="UTF-8", xml_declaration=True)
    return xml_bytes.decode("utf-8")


def atomic_write(filepath: str, content: str) -> None:
    """Safely writes content to target filepath using atomic replace."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = path.with_suffix(path.suffix + ".partial")
    try:
        with open(partial_path, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(partial_path, path)
    except Exception:
        if partial_path.exists():
            try:
                os.remove(partial_path)
            except OSError:
                pass
        raise


def main() -> int:
    args = parse_args()

    # Read input payload
    try:
        if args.input == "-":
            raw_data = sys.stdin.read()
        else:
            with open(args.input, "r", encoding="utf-8") as f:
                raw_data = f.read()

        if not raw_data.strip():
            sys.stderr.write("Error: Input payload is empty.\n")
            return 1

        payload = json.loads(raw_data)
    except Exception as exc:
        sys.stderr.write(f"Error reading JSON input: {exc}\n")
        return 1

    items = extract_conversations(payload)
    filtered = filter_conversations(items, args.category)

    opml_tree = create_opml(filtered, flat=args.flat)
    opml_str = get_opml_string(opml_tree)
    atomic_write(args.output, opml_str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
