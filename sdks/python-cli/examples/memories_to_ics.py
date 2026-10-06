"""Convert an omi-cli memory export into an iCalendar (.ics) timeline.

Reads JSON produced by `omi --json memory list --limit 200` (or piped via stdin),
and generates an RFC 5545 compliant .ics file importable into Google Calendar,
Apple Calendar, Outlook, and Thunderbird.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

EVENT_LENGTH = timedelta(minutes=15)


def validate_path(path_str: str) -> Path:
    """Validate that path does not attempt path traversal."""
    p = Path(path_str)
    if ".." in p.parts:
        raise ValueError(f"Path traversal detected in path: {path_str}")
    return p


def ics_text(value: Any) -> str:
    """Escape text for an iCalendar property value (RFC 5545 §3.3.11).

    Escapes backslashes, semicolons, commas, and newlines. Anything non-null
    is coerced to string rather than rejected so unexpected fields don't abort export.
    """
    if value is None:
        return ""
    if isinstance(value, list):
        value = ", ".join(str(x) for x in value)
    elif isinstance(value, dict):
        value = json.dumps(value, ensure_ascii=False)
    else:
        value = str(value)

    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def ics_datetime(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp into a timezone-aware UTC datetime, or None if invalid."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def stamp(dt: datetime) -> str:
    """Format datetime as iCalendar UTC timestamp."""
    return dt.strftime("%Y%m%dT%H%M%SZ")


def fold(line: str) -> list[str]:
    """Fold a content line at 75 octets (RFC 5545 §3.1), never splitting UTF-8 characters."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return [line]
    parts: list[str] = []
    chunk = b""
    limit = 75
    for ch in line:
        b = ch.encode("utf-8")
        if len(chunk) + len(b) > limit:
            parts.append(chunk.decode("utf-8"))
            chunk = b" " + b
            limit = 75
        else:
            chunk += b
    if chunk:
        parts.append(chunk.decode("utf-8"))
    return parts


def convert(
    source: str | Path,
    destination: str | Path,
    overwrite: bool = False,
) -> tuple[int, int]:
    """Convert memory export JSON to an iCalendar (.ics) timeline.

    Returns a tuple of (exported_count, skipped_count).
    """
    if str(source) == "-":
        raw = sys.stdin.buffer.read()
    else:
        src_path = validate_path(str(source))
        raw = src_path.read_bytes()

    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]

    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"Invalid JSON input: {exc}") from exc

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("memories", "items", "data", "results"):
            if key in data and isinstance(data[key], list):
                items = data[key]
                break
        else:
            raise ValueError("Expected a JSON array or envelope object containing 'memories'")
    else:
        raise ValueError("Expected a JSON array or dictionary object")

    now = stamp(datetime.now(timezone.utc))
    raw_lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//omi-cli examples//memories_to_ics//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Omi Memories",
    ]

    exported = 0
    skipped = 0

    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each memory item must be an object")

        created = ics_datetime(item.get("created_at"))
        if created is None:
            skipped += 1
            continue

        item_id = ics_text(item.get("id")) or "unknown"
        content = item.get("content") or ""
        escaped_content = ics_text(content) or "(empty memory)"

        # Summary is the first line of content (shortened if very long)
        first_line = content.splitlines()[0] if content else "(empty memory)"
        summary_text = ics_text(first_line[:80])

        category = ics_text(item.get("category"))
        tags = item.get("tags")
        visibility = ics_text(item.get("visibility"))

        description_lines = [f"Memory: {escaped_content}"]
        if category:
            description_lines.append(f"Category: {category}")
        if tags and isinstance(tags, list):
            description_lines.append(f"Tags: {ics_text(tags)}")
        if visibility:
            description_lines.append(f"Visibility: {visibility}")
        description_lines.append(f"ID: {item_id}")

        event_lines = [
            "BEGIN:VEVENT",
            f"UID:omi-memory-{item_id}@omi-cli",
            f"DTSTAMP:{now}",
            f"DTSTART:{stamp(created)}",
            f"DTEND:{stamp(created + EVENT_LENGTH)}",
            f"SUMMARY:{summary_text}",
            "DESCRIPTION:" + "\\n".join(description_lines),
        ]
        if category:
            event_lines.append(f"CATEGORIES:{category}")

        event_lines.append("END:VEVENT")
        raw_lines.extend(event_lines)
        exported += 1

    raw_lines.append("END:VCALENDAR")

    output_path = validate_path(str(destination))
    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"Output file '{output_path}' already exists. Use --overwrite to replace it."
        )

    # Fold lines to 75 octets and join with CRLF per RFC 5545
    folded_lines: list[str] = []
    for line in raw_lines:
        folded_lines.extend(fold(line))

    ics_content = "\r\n".join(folded_lines) + "\r\n"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial = output_path.with_name(f"{output_path.name}.partial")
    try:
        partial.write_bytes(ics_content.encode("utf-8"))
        os.replace(partial, output_path)
    except Exception:
        if partial.exists():
            partial.unlink(missing_ok=True)
        raise

    return exported, skipped


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert an omi-cli memory export into an RFC 5545 iCalendar (.ics) timeline."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="-",
        help="Input JSON file path or '-' for stdin (default: -)",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output iCalendar file path (.ics)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output file if present",
    )

    args = parser.parse_args()

    try:
        exported, skipped = convert(args.input, args.output, overwrite=args.overwrite)
        msg = f"Exported {exported} memory event(s) to {args.output}"
        if skipped > 0:
            msg += f" ({skipped} item(s) skipped due to missing created_at timestamp)"
        print(msg)
    except (OSError, ValueError) as exc:
        sys.exit(f"iCalendar export failed: {exc}")


if __name__ == "__main__":
    main()
