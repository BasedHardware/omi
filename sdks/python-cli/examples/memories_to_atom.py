#!/usr/bin/env python3
"""Convert Omi memory JSON exports to an Atom 1.0 feed a reader can
subscribe to — matching the conversations -> Atom recipe's shape.

See memories_atom.md for the full recipe. Stdlib only.

Usage:
    omi --json memory list > memories.json
    python memories_to_atom.py memories.xml memories.json [memories2.json ...]

One entry per memory, newest first; ``created_at`` drives ``published`` and
``updated`` (normalized to UTC RFC 3339). The entry summary carries
metadata only — category / visibility / tags / creation time — never the
memory's content text, which can hold private material.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote
from xml.sax.saxutils import escape, quoteattr

FEED_TITLE = "Omi memories"
FEED_ID = "urn:omi:memories"
EPOCH = "1970-01-01T00:00:00Z"
ENVELOPE_KEYS = ("memories", "items", "data")
MAX_SUMMARY = 160

# XML 1.0 Char = #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]
_ILLEGAL_XML = re.compile(r"[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")


def clean_text(value: Any) -> str:
    """Render a loosely typed field as XML-legal text.

    Drops control characters, lone surrogates and non-characters so an
    unusual memory still produces a parseable feed; coerces non-strings
    rather than rejecting them.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return _ILLEGAL_XML.sub("", " ".join(value.split()))


def parse_time(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None if unusable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def rfc3339(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def extract_memories(data: Any) -> List[Any]:
    """Unwrap memories from bare lists or wrapped envelope dictionaries."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ENVELOPE_KEYS:
            if isinstance(data.get(key), list):
                return data[key]
        return [data]
    return []


def load(sources: List[str]) -> Dict[str, Dict[str, Any]]:
    """Read every page; dedupe by memory id (first wins), keyed for lookup."""
    seen: Dict[str, Dict[str, Any]] = {}
    for src in sources:
        raw = json.loads(Path(src).read_bytes().decode("utf-8-sig"))
        for item in extract_memories(raw):
            if not isinstance(item, dict):
                continue
            mid = clean_text(item.get("id") or item.get("memory_id"))
            if mid and mid not in seen:
                seen[mid] = item
    return seen


def summary_of(item: Dict[str, Any]) -> str:
    """Metadata-only entry summary — never the memory's content text."""
    details = []
    for label, value in (
        ("Category", clean_text(item.get("category"))),
        ("Visibility", clean_text(item.get("visibility"))),
    ):
        if value:
            details.append(f"{label}: {value}")
    tags = item.get("tags")
    if isinstance(tags, list) and tags:
        details.append("Tags: " + ", ".join(clean_text(t) for t in tags if t is not None))
    created = parse_time(item.get("created_at"))
    if created is not None:
        details.append(f"Captured: {rfc3339(created)}")
    return " - ".join(details)[:MAX_SUMMARY] or "Omi memory"


def entries(memories: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build one entry per memory, newest first."""
    rows = []
    for mid, item in memories.items():
        created = parse_time(item.get("created_at"))
        updated = parse_time(item.get("updated_at")) or created
        rows.append(
            {
                "id": mid,
                "title": clean_text(item.get("content") or item.get("text") or item.get("title")) or "(memory)",
                "category": clean_text(item.get("category")),
                "published": created,
                "updated": updated if updated is not None else created,
                "summary": summary_of(item),
                "sort": created if created is not None else datetime.min.replace(tzinfo=timezone.utc),
            }
        )
    rows.sort(key=lambda row: (row["sort"], row["id"]), reverse=True)
    return rows


def feed(rows: List[Dict[str, Any]]) -> str:
    stamps = [rfc3339(r["updated"]) for r in rows if r["updated"] is not None]
    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom">',
        f"<title>{escape(FEED_TITLE)}</title>",
        f"<id>{FEED_ID}</id>",
        f"<updated>{max(stamps) if stamps else EPOCH}</updated>",
        "<author><name>Omi</name></author>",
    ]
    for row in rows:
        parts += [
            "<entry>",
            f"<title>{escape(row['title'][:80])}</title>",
            f"<id>urn:omi:memory:{quote(row['id'], safe='')}</id>",
            f"<updated>{rfc3339(row['updated']) if row['updated'] is not None else EPOCH}</updated>",
        ]
        if row["published"] is not None:
            parts.append(f"<published>{rfc3339(row['published'])}</published>")
        if row["category"]:
            parts.append(f"<category term={quoteattr(row['category'])}/>")
        parts += [f'<summary type="text">{escape(row["summary"])}</summary>', "</entry>"]
    parts.append("</feed>")
    return "\n".join(parts) + "\n"


def convert(sources: List[str], destination: str) -> int:
    """Write the Atom feed; return the entry count."""
    rows = entries(load(sources))
    payload = feed(rows).encode("utf-8")
    output_path = Path(destination)
    if ".." in output_path.parts:
        raise ValueError(f"Refusing '..' in output path {destination}")
    # Exclusive creation protects an existing feed; a failed write leaves no partial file.
    try:
        output = output_path.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {output_path}") from None
    try:
        with output:
            output.write(payload)
    except OSError:
        output_path.unlink(missing_ok=True)
        raise
    return len(rows)


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Convert Omi memory JSON exports to an Atom feed.")
    ap.add_argument("output", help="Destination .xml path")
    ap.add_argument("inputs", nargs="+", help="One or more JSON export files")
    args = ap.parse_args(argv)
    try:
        n = convert(args.inputs, args.output)
    except (ValueError, FileExistsError, OSError, json.JSONDecodeError) as e:
        print(f"memories_to_atom: {e}", file=sys.stderr)
        return 2
    print(f"memories_to_atom: wrote {n} entries to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
