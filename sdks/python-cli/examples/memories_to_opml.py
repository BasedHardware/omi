"""
Convert Omi memories JSON exports to clean OPML 2.0 outlines for Workflowy, Logseq, OmniFocus, or Dynalist.

Usage:
    # Pipe directly from omi CLI
    omi --json memory list | python memories_to_opml.py - memories.opml

    # Export a saved JSON export
    python memories_to_opml.py memories.json memories.opml

    # Flat export without grouping by category
    python memories_to_opml.py memories.json memories.opml --flat

    # Filter specific categories
    python memories_to_opml.py memories.json memories.opml --category work,skills
"""

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


def parse_args():
    parser = argparse.ArgumentParser(description="Convert Omi Memories JSON to OPML 2.0")
    parser.add_argument("input", help="Input JSON file (or '-' for stdin)")
    parser.add_argument("output", help="Output OPML file")
    parser.add_argument(
        "--category",
        "-c",
        type=str,
        default=None,
        help="Filter by category (comma-separated list, e.g. 'work,skills').",
    )
    parser.add_argument(
        "--flat",
        action="store_true",
        help="Export outlines flat without grouping into category parents.",
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


def extract_memories(data: Any) -> List[Dict[str, Any]]:
    """Unwrap memory records from bare arrays or wrapped envelopes."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("memories", "items", "data"):
            val = data.get(key)
            if isinstance(val, list):
                return [item for item in val if isinstance(item, dict)]
        if any(key in data for key in ("content", "category", "id", "created_at")):
            return [data]
        return []
    return []


def filter_memories(items: List[Dict[str, Any]], category_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Filter memory items by category."""
    if not category_filter:
        return items
    target_cats = {c.strip().lower() for c in category_filter.split(",") if c.strip()}
    return [
        it for it in items
        if str(safe_get(it, ["category"], "")).strip().lower() in target_cats
    ]


def create_memory_outline(item: Dict[str, Any]) -> Dict[str, str]:
    """Builds XML outline attributes for a single memory record."""
    raw_content = safe_get(item, ["content", "text", "description", "title"], "Untitled memory")
    content = strip_surrogates(str(raw_content)).strip().replace("\r\n", " ").replace("\n", " ")
    if not content:
        content = "Untitled memory"

    attribs: Dict[str, str] = {
        "text": content,
    }

    created = safe_get(item, ["created_at", "created"], "")
    if created:
        attribs["created"] = strip_surrogates(str(created))

    category = safe_get(item, ["category"], "")
    if category:
        attribs["category"] = strip_surrogates(str(category))

    tags = safe_get(item, ["tags"], None)
    if isinstance(tags, list) and tags:
        clean_tags = [re.sub(r"[^\w-]", "", strip_surrogates(str(t))).strip() for t in tags if t]
        clean_tags = [t for t in clean_tags if t]
        if clean_tags:
            attribs["_tags"] = " ".join(f"#{t}" for t in clean_tags)

    visibility = safe_get(item, ["visibility"], "")
    if visibility:
        attribs["_visibility"] = strip_surrogates(str(visibility)).strip().lower()

    mem_id = safe_get(item, ["id"], "")
    if mem_id:
        attribs["_id"] = strip_surrogates(str(mem_id))

    return attribs


def create_opml(memories: List[Dict[str, Any]], flat: bool = False, title: str = "Omi Memories") -> ET.Element:
    """Create an OPML 2.0 XML tree from a list of memory dictionaries."""
    opml = ET.Element("opml", version="2.0")

    # Header
    head = ET.SubElement(opml, "head")
    ET.SubElement(head, "title").text = strip_surrogates(title)
    ET.SubElement(head, "dateCreated").text = datetime.now(timezone.utc).isoformat()

    body = ET.SubElement(opml, "body")

    if not memories:
        return opml

    if flat:
        for item in memories:
            attribs = create_memory_outline(item)
            ET.SubElement(body, "outline", attribs)
    else:
        # Group by category
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for item in memories:
            cat = str(safe_get(item, ["category"], "")).strip().lower()
            key = cat.title() if cat else "Uncategorized"
            grouped.setdefault(key, []).append(item)

        for cat_name in sorted(grouped.keys()):
            cat_outline = ET.SubElement(body, "outline", {"text": cat_name})
            for item in grouped[cat_name]:
                attribs = create_memory_outline(item)
                ET.SubElement(cat_outline, "outline", attribs)

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

    items = extract_memories(payload)
    filtered = filter_memories(items, args.category)

    opml_tree = create_opml(filtered, flat=args.flat)
    opml_str = get_opml_string(opml_tree)
    atomic_write(args.output, opml_str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
