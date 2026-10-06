"""Convert one or more local omi-cli memory exports to an Atom 1.0 feed."""

from __future__ import annotations

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

ATOM_NS = "http://www.w3.org/2005/Atom"
ET.register_namespace("", ATOM_NS)

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _is_xml10_char(codepoint: int) -> bool:
    """Return whether a Unicode code point is allowed by this export's XML policy."""
    valid = (
        codepoint in (0x09, 0x0A, 0x0D)
        or 0x20 <= codepoint <= 0xD7FF
        or 0xE000 <= codepoint <= 0xFFFD
        or 0x10000 <= codepoint <= 0x10FFFF
    )
    noncharacter = 0xFDD0 <= codepoint <= 0xFDEF or codepoint & 0xFFFF in (0xFFFE, 0xFFFF)
    return valid and not noncharacter


def text(value: Any) -> str:
    """Coerce a loose API value to a single line of XML 1.0-safe text."""
    if value is None:
        return ""
    if isinstance(value, str):
        rendered = value
    elif isinstance(value, (dict, list)):
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        rendered = str(value)

    cleaned = "".join(character for character in rendered if _is_xml10_char(ord(character)))
    return " ".join(cleaned.split())


def parse_time(value: Any) -> datetime | None:
    """Parse an ISO 8601 timestamp, treating a timezone-free value as UTC."""
    if not isinstance(value, str) or not value.strip():
        return None

    timestamp = value.strip()
    if timestamp.endswith("Z"):
        timestamp = timestamp[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(timestamp)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def rfc3339(moment: datetime) -> str:
    """Render an aware datetime in UTC using the Atom/RFC 3339 form."""
    timestamp = moment.astimezone(timezone.utc).isoformat(timespec="microseconds").removesuffix("+00:00")
    whole_seconds, fraction = timestamp.split(".", 1)
    fraction = fraction.rstrip("0")
    return f"{whole_seconds}.{fraction}Z" if fraction else f"{whole_seconds}Z"


def load_memories(sources: list[str]) -> list[dict[str, Any]]:
    """Load JSON-array exports, merging duplicate IDs with the later input winning."""
    memories: dict[str, dict[str, Any]] = {}
    for source in sources:
        if source == "-":
            raw = sys.stdin.read()
            label = "stdin"
        else:
            path = Path(source)
            raw = path.read_text(encoding="utf-8-sig")
            label = str(path)

        try:
            items = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label}: invalid JSON: {exc.msg}") from exc
        if not isinstance(items, list):
            raise ValueError(f"{label}: expected the JSON array from omi --json memory list")

        for item in items:
            if not isinstance(item, dict):
                continue
            memory_id = text(item.get("id"))
            if memory_id:
                memories[memory_id] = item
    return list(memories.values())


def entries(memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build Atom entry data newest first, using created_at for both timestamps."""
    rows = []
    for memory in memories:
        created_at = parse_time(memory.get("created_at")) or EPOCH
        category = text(memory.get("category"))
        visibility = text(memory.get("visibility"))
        tags_value = memory.get("tags")
        if isinstance(tags_value, list):
            tags = ", ".join(filter(None, (text(tag) for tag in tags_value)))
        else:
            tags = text(tags_value)

        details = []
        for label, value in (("Category", category), ("Visibility", visibility), ("Tags", tags)):
            if value:
                details.append(f"{label}: {value}")
        details.append(f"Created: {rfc3339(created_at)}")

        rows.append(
            {
                "id": text(memory.get("id")),
                "title": text(memory.get("content")) or "(untitled memory)",
                "category": category,
                "published": created_at,
                "updated": created_at,
                "summary": " - ".join(details),
            }
        )

    rows.sort(key=lambda row: (row["published"], row["id"]), reverse=True)
    return rows


def _element(parent: ET.Element, name: str, value: str) -> ET.Element:
    child = ET.SubElement(parent, f"{{{ATOM_NS}}}{name}")
    child.text = value
    return child


def build_feed(rows: list[dict[str, Any]]) -> ET.Element:
    """Create an Atom 1.0 document tree from prepared memory rows."""
    feed = ET.Element(f"{{{ATOM_NS}}}feed")
    _element(feed, "title", "Omi memories")
    _element(feed, "id", "urn:omi:memories")
    newest = max((row["updated"] for row in rows), default=EPOCH)
    _element(feed, "updated", rfc3339(newest))
    author = ET.SubElement(feed, f"{{{ATOM_NS}}}author")
    _element(author, "name", "Omi")

    for row in rows:
        entry = ET.SubElement(feed, f"{{{ATOM_NS}}}entry")
        _element(entry, "title", row["title"])
        _element(entry, "id", f"urn:omi:memory:{quote(row['id'], safe='')}")
        _element(entry, "published", rfc3339(row["published"]))
        _element(entry, "updated", rfc3339(row["updated"]))
        if row["category"]:
            ET.SubElement(entry, f"{{{ATOM_NS}}}category", {"term": row["category"]})
        summary = _element(entry, "summary", row["summary"])
        summary.set("type", "text")

    return feed


def convert(sources: list[str], destination: str) -> int:
    """Write a feed without replacing an existing file; return its entry count."""
    rows = entries(load_memories(sources))
    payload = ET.tostring(build_feed(rows), encoding="utf-8", xml_declaration=True) + b"\n"
    output_path = Path(destination)
    created = False
    try:
        descriptor = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {output_path}") from None
    except OSError:
        if created:
            output_path.unlink(missing_ok=True)
        raise
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert local omi-cli memory JSON exports into a private Atom 1.0 feed."
    )
    parser.add_argument("output", help="new XML file to create")
    parser.add_argument("inputs", nargs="+", help="memory JSON exports; use '-' for stdin")
    args = parser.parse_args(argv)

    if args.inputs.count("-") > 1:
        parser.error("stdin ('-') can be used only once")
    try:
        count = convert(args.inputs, args.output)
    except (OSError, ValueError) as exc:
        print(f"Atom export failed: {exc}", file=sys.stderr)
        return 1

    print(f"{count} entr{'y' if count == 1 else 'ies'} written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
