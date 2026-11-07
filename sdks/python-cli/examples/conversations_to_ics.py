import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_LENGTH = timedelta(minutes=30)


def strip_surrogates(value: str) -> str:
    """Drop unpaired surrogate code points that cannot be encoded as UTF-8."""
    return value.encode("utf-8", "ignore").decode("utf-8")


def ics_text(value):
    """Escape text for an iCalendar property value (RFC 5545 §3.3.11).

    The dev API is loosely typed, so a field can arrive as a non-string; anything
    non-null is coerced rather than rejected, so one odd row cannot break the file.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    value = strip_surrogates(value)
    return (value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def ics_datetime(value):
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


def stamp(dt):
    return dt.strftime("%Y%m%dT%H%M%SZ")


def fold(line):
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


def extract_conversations(data):
    """Unwrap conversations from bare lists or documented envelope dictionaries."""
    if isinstance(data, list):
        return [it for it in data if isinstance(it, dict)]
    if isinstance(data, dict):
        for key in ("conversations", "items", "data"):
            val = data.get(key)
            if isinstance(val, list):
                return [it for it in val if isinstance(it, dict)]
        if data:
            return [data]
    return []


def convert(source, destination):
    if source == "-":
        raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
    else:
        raw = Path(source).read_bytes().decode("utf-8-sig", errors="replace")
    
    raw = raw.strip()
    if not raw:
        items = []
    else:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON input: {exc}") from exc
        items = extract_conversations(data)

    now = stamp(datetime.now(timezone.utc))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//omi-cli examples//conversations_to_ics//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Omi conversations"]
    skipped = 0
    written = 0
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each conversation must be an object")
        structured = item.get("structured")
        if structured is None:
            structured = {}
        if not isinstance(structured, dict):
            raise ValueError("Conversation structured field must be an object or null")
        start = ics_datetime(item.get("started_at"))
        if start is None:
            skipped += 1
            continue
        end = ics_datetime(item.get("finished_at"))
        if end is None or end <= start:
            end = start + DEFAULT_LENGTH
        item_id = ics_text(item.get("id")) or "unknown"
        title = ics_text(structured.get("title")) or "(untitled conversation)"
        notes = [f"Omi conversation {item_id}"]
        if structured.get("category"):
            notes.append(f"Category: {ics_text(structured.get('category'))}")
        if item.get("source"):
            notes.append(f"Source: {ics_text(item.get('source'))}")
        lines += ["BEGIN:VEVENT", f"UID:omi-conversation-{item_id}@omi-cli", f"DTSTAMP:{now}",
                  f"DTSTART:{stamp(start)}", f"DTEND:{stamp(end)}", f"SUMMARY:{title}",
                  "DESCRIPTION:" + "\\n".join(notes), "STATUS:CONFIRMED", "CATEGORIES:Omi", "END:VEVENT"]
        written += 1
    lines.append("END:VCALENDAR")
    folded = [part for line in lines for part in fold(line)]
    payload = ("\r\n".join(folded) + "\r\n").encode("utf-8")
    output_path = Path(destination)
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
    return written, skipped


def main():
    parser = argparse.ArgumentParser(description="Convert an Omi conversation export to an iCalendar (.ics) timeline.")
    parser.add_argument("source", help="JSON from omi --json conversation list, or '-' for stdin")
    parser.add_argument("destination", help="new .ics file to create")
    args = parser.parse_args()

    try:
        written, skipped = convert(args.source, args.destination)
    except (OSError, ValueError) as exc:
        sys.exit(f"ICS export failed: {exc}")
    print(f"{written} event(s) written, {skipped} conversation(s) skipped (no start time)")


if __name__ == "__main__":
    main()
