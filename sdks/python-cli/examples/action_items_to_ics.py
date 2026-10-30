import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

EVENT_LENGTH = timedelta(minutes=30)
DONE_WORDS = {"true", "yes", "1", "done", "completed"}


def strip_surrogates(value: str) -> str:
    """Drop unpaired surrogate code points that cannot be encoded as UTF-8."""
    return value.encode("utf-8", "ignore").decode("utf-8")


def is_completed(value) -> bool:
    """Normalize completion state handling booleans, numbers, and loose strings."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in DONE_WORDS
    return False


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
    """Parse an ISO-8601 timestamp into an iCalendar UTC stamp, or None if unusable."""
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


def extract_action_items(data):
    """Unwrap action items from bare lists or documented envelope dictionaries."""
    if isinstance(data, list):
        return [it for it in data if isinstance(it, dict)]
    if isinstance(data, dict):
        for key in ("action_items", "items", "data"):
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
        items = extract_action_items(data)

    now = stamp(datetime.now(timezone.utc))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//omi-cli examples//action_items_to_ics//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Omi action items"]
    skipped = 0
    written = 0
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each action item must be an object")
        due = ics_datetime(item.get("due_at") or item.get("due_date") or item.get("due"))
        if due is None:
            skipped += 1
            continue
        item_id = ics_text(item.get("id")) or "unknown"
        description = ics_text(item.get("description") or item.get("text") or item.get("title")) or "(no description)"
        notes = [f"Omi action item {item_id}"]
        if item.get("conversation_id"):
            notes.append(f"Conversation: {ics_text(item.get('conversation_id'))}")
        created = ics_datetime(item.get("created_at") or item.get("created"))
        completed_val = item.get("completed") if item.get("completed") is not None else item.get("is_completed")
        status = "COMPLETED" if is_completed(completed_val) else "CONFIRMED"
        lines += ["BEGIN:VEVENT", f"UID:omi-action-{item_id}@omi-cli", f"DTSTAMP:{now}",
                  f"DTSTART:{stamp(due)}", f"DTEND:{stamp(due + EVENT_LENGTH)}",
                  f"SUMMARY:{description}", "DESCRIPTION:" + "\\n".join(notes),
                  f"STATUS:{status}",
                  "CATEGORIES:Omi"]
        if created is not None:
            lines.append(f"CREATED:{stamp(created)}")
        lines.append("END:VEVENT")
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
    parser = argparse.ArgumentParser(description="Convert an Omi action item export to an iCalendar (.ics) timeline.")
    parser.add_argument("source", help="JSON from omi --json action-item list, or '-' for stdin")
    parser.add_argument("destination", help="new .ics file to create")
    args = parser.parse_args()

    try:
        written, skipped = convert(args.source, args.destination)
    except (OSError, ValueError) as exc:
        sys.exit(f"ICS export failed: {exc}")
    print(f"{written} event(s) written, {skipped} item(s) skipped (no due date)")


if __name__ == "__main__":
    main()
