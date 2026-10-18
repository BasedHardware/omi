#!/usr/bin/env python3
"""Convert an Omi memory JSON export to an RFC 5545 iCalendar (.ics) timeline
importable into Google Calendar, Apple Calendar, and Outlook.

See memories_ics.md for the full recipe. Stdlib only.

Usage:
    omi --json memory list > memories.json
    python memories_to_ics.py memories.json -o memories.ics

Each memory's ``created_at`` becomes a 15-minute VEVENT on the timeline —
SUMMARY carries the memory text, DESCRIPTION carries its category /
visibility / id. RFC 5545 §3.1 line folding at 75 octets (UTF-8-safe) and
§3.3.11 escaping are honored; the output path is created exclusively.
"""

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

EVENT_LENGTH = timedelta(minutes=15)
ENVELOPE_KEYS = ("memories", "items", "data")


def ics_datetime(value: Any) -> Optional[datetime]:
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


def ics_text(value: Any) -> str:
    """Render a loosely typed field as text; coerced, not rejected."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return value


def escape(value: Any) -> str:
    """RFC 5545 §3.3.11 escaping for TEXT properties."""
    return (
        ics_text(value)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def stamp(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%SZ")


def fold(line: str) -> List[str]:
    """Fold a content line at 75 octets (RFC 5545 §3.1), never splitting a UTF-8 character."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return [line]
    parts, chunk, limit = [], b"", 75
    for ch in line:
        b = ch.encode("utf-8")
        if len(chunk) + len(b) > limit:
            parts.append(chunk.decode("utf-8"))
            chunk, limit = b" " + b, 75
        else:
            chunk += b
    parts.append(chunk.decode("utf-8"))
    return parts


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


def strip_surrogates(value: str) -> str:
    """Drop unpaired surrogate code points that cannot be encoded as UTF-8."""
    return value.encode("utf-8", "ignore").decode("utf-8")


def convert(sources: List[str], destination: str) -> int:
    """Write the .ics file; return the event count."""
    items: List[Dict[str, Any]] = []
    seen = set()
    for src in sources:
        raw = json.loads(Path(src).read_bytes().decode("utf-8-sig"))
        for item in extract_memories(raw):
            if not isinstance(item, dict):
                continue
            mid = str(item.get("id") or item.get("memory_id") or "")
            if mid and mid in seen:
                continue
            if mid:
                seen.add(mid)
            items.append(item)

    now = stamp(datetime.now(timezone.utc))
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//omi-cli examples//memories_to_ics//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Omi memories",
    ]
    written = 0
    for item in items:
        created = ics_datetime(item.get("created_at"))
        if created is None:
            continue  # a memory with no timeline anchor can't become an event
        mid = ics_text(item.get("id") or item.get("memory_id")) or f"unknown-{written}"
        summary = ics_text(item.get("content") or item.get("text") or item.get("title")) or "(no content)"
        notes = [f"Omi memory {mid}"]
        for key, label in (("category", "Category"), ("visibility", "Visibility")):
            v = ics_text(item.get(key))
            if v:
                notes.append(f"{label}: {v}")
        lines += [
            "BEGIN:VEVENT",
            f"UID:omi-memory-{mid}@omi-cli",
            f"DTSTAMP:{now}",
            f"DTSTART:{stamp(created)}",
            f"DTEND:{stamp(created + EVENT_LENGTH)}",
            f"SUMMARY:{escape(summary)}",
            "DESCRIPTION:" + "\\n".join(escape(n) for n in notes),
            "STATUS:CONFIRMED",
            "CATEGORIES:Omi",
            "END:VEVENT",
        ]
        written += 1
    lines.append("END:VCALENDAR")
    folded = [part for line in lines for part in fold(strip_surrogates(line))]
    payload = ("\r\n".join(folded) + "\r\n").encode("utf-8")

    output_path = Path(destination)
    if ".." in output_path.parts:
        raise ValueError(f"Refusing '..' in output path {destination}")
    # Exclusive creation protects an existing export; a failed write leaves no partial file.
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
    return written


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Convert an Omi memory JSON export to .ics.")
    ap.add_argument("inputs", nargs="+", help="One or more JSON export files")
    ap.add_argument("-o", "--output", required=True, help="Destination .ics path")
    args = ap.parse_args(argv)
    try:
        n = convert(args.inputs, args.output)
    except (ValueError, FileExistsError, OSError, json.JSONDecodeError) as e:
        print(f"memories_to_ics: {e}", file=sys.stderr)
        return 2
    print(f"memories_to_ics: wrote {n} event(s) to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
