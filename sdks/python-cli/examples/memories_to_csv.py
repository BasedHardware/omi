import csv
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FIELDS = ("id", "category", "created_at", "manually_added", "content")


def spreadsheet_text(value):
    """Render one exported field as spreadsheet-safe text.

    The dev API is loosely typed, so a field can arrive as a non-string even
    though the CLI models it as Optional[str]. One odd row must not destroy a
    whole export, so anything non-null is coerced rather than rejected.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    # Avoid treating common formula prefixes as formulas on spreadsheet import.
    # The apostrophe is intentional and may be visible in some importers.
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def utc_text(value):
    """Render an ISO-8601 timestamp as UTC text, or keep it verbatim if unusable.

    Memories arrive with timestamps from several clients, so some carry an
    offset and some do not. A naive timestamp is read as UTC, which matches the
    server's own storage, and everything is rendered in one format so that
    spreadsheet sorting is stable.
    """
    if not isinstance(value, str) or not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def memory_content(item):
    """Pick the best available text for a memory.

    Memories carry their text under `content` in current exports and under
    `aw_json` in older ones, where the payload is a JSON envelope rather than
    plain text. Both shapes appear in the same account, so the envelope is
    unwrapped when it is recognised and the raw text is kept otherwise.
    """
    content = item.get("content")
    if isinstance(content, str) and content.strip():
        return content
    envelope = item.get("aw_json")
    if isinstance(envelope, str) and envelope.strip():
        try:
            decoded = json.loads(envelope)
        except ValueError:
            return envelope
        if isinstance(decoded, dict):
            for key in ("content", "text", "message"):
                inner = decoded.get(key)
                if isinstance(inner, str) and inner.strip():
                    return inner
        return envelope
    return ""


def convert(source, destination):
    items = json.loads(Path(source).read_bytes())
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json memory list")
    rows = []
    known_categories = set()
    undated = 0
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each memory must be an object")
        created = utc_text(item.get("created_at"))
        if not created:
            undated += 1
        category = item.get("category")
        if isinstance(category, str) and category:
            known_categories.add(category)
        values = (item.get("id"), category, created,
                  item.get("manually_added"), memory_content(item))
        rows.append([spreadsheet_text(value) for value in values])
    rows.sort(key=lambda row: (row[2] == "", row[2], row[0]))
    # Format and encode the whole export before touching the filesystem, so a
    # conversion failure cannot leave a truncated CSV behind for the next run.
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(FIELDS)
    writer.writerows(rows)
    payload = buffer.getvalue().encode("utf-8-sig")
    output_path = Path(destination)
    # Exclusive creation still protects an existing export.
    try:
        output = output_path.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {output_path}") from None
    try:
        with output:
            output.write(payload)
    except OSError:
        # Leave no partial export behind when the write itself fails.
        output_path.unlink(missing_ok=True)
        raise
    return len(rows), len(known_categories), undated


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python memories_to_csv.py INPUT.json OUTPUT.csv")
    try:
        written, categories, undated = convert(sys.argv[1], sys.argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"CSV export failed: {exc}")
    print(f"{written} memory row(s) written, {categories} category value(s), {undated} without a timestamp")
