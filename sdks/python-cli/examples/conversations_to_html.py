import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

COLUMNS = ("Start", "Duration", "Title", "Category", "Folder", "Source", "Language", "ID")

STYLE = """
body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 70rem; padding: 0 1rem; color: #1a1a1a; background: #fff; }
h1 { font-size: 1.6rem; } h2 { font-size: 1.2rem; margin-top: 2rem; border-bottom: 1px solid #ccc; }
p.summary { color: #444; } table { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
th, td { border: 1px solid #ddd; padding: 0.3rem 0.5rem; text-align: left; vertical-align: top; }
th { background: #f3f3f3; } td.num { text-align: right; white-space: nowrap; } td.id { font-family: monospace; font-size: 0.8rem; }
@media print { body { margin: 0; max-width: none; } h2 { page-break-after: avoid; } tr { page-break-inside: avoid; } }
"""


def strip_surrogates(value: str) -> str:
    """Drop unpaired surrogate code points that cannot be encoded as UTF-8."""
    return value.encode("utf-8", "ignore").decode("utf-8")


def text(value):
    """Render a loosely typed field as one line of text; anything non-null is coerced, not rejected."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    value = strip_surrogates(value)
    return " ".join(value.split())


def parse_time(value):
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


def parse_offset(value):
    """Turn '+09:00' / '-05:30' into a timedelta for local calendar days and clock times."""
    if len(value) != 6 or value[0] not in "+-" or value[3] != ":" or not (value[1:3] + value[4:]).isdigit():
        raise ValueError(f"UTC offset must look like +09:00, got {value!r}")
    delta = timedelta(hours=int(value[1:3]), minutes=int(value[4:]))
    if int(value[4:]) > 59 or delta > timedelta(hours=14):
        raise ValueError(f"UTC offset must be between -14:00 and +14:00, got {value!r}")
    return -delta if value[0] == "-" else delta


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


def load(sources):
    conversations = {}
    for source in sources:
        if source == "-":
            raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
        else:
            raw = Path(source).read_bytes().decode("utf-8-sig", errors="replace")
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{source}: invalid JSON: {exc}") from exc
        items = extract_conversations(data)
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"{source}: each conversation must be an object")
            raw_id = item.get("id")
            if not isinstance(raw_id, str) or not raw_id:
                raise ValueError(f"{source}: each conversation needs a string id")
            item_id = strip_surrogates(raw_id)
            structured = item.get("structured")
            if structured is None:
                structured = {}
            if not isinstance(structured, dict):
                raise ValueError(f"{source}: conversation structured field must be an object or null")
            conversations[item_id] = item
    return conversations


def rows_by_day(conversations, offset):
    """Group conversations into local calendar days; returns (days, undated) with rows sorted by start."""
    days, undated = defaultdict(list), []
    for item_id, item in conversations.items():
        start, end = parse_time(item.get("started_at")), parse_time(item.get("finished_at"))
        structured = item.get("structured") or {}
        seconds = int((end - start).total_seconds()) if start is not None and end is not None and end >= start else 0
        row = {
            "start": (start + offset).strftime("%H:%M") if start is not None else "",
            "sort": start if start is not None else datetime.max.replace(tzinfo=timezone.utc),
            "seconds": seconds,
            "title": text(structured.get("title")) or "(untitled conversation)",
            "category": text(structured.get("category")),
            "folder": text(item.get("folder_name")),
            "source": text(item.get("source")),
            "language": text(item.get("language")),
            "id": strip_surrogates(str(item_id)),
        }
        if start is None:
            undated.append(row)
        else:
            days[(start + offset).strftime("%Y-%m-%d")].append(row)
    for bucket in list(days.values()) + [undated]:
        bucket.sort(key=lambda r: (r["sort"], r["id"]))
    return dict(sorted(days.items())), undated


def minutes(seconds):
    return f"{seconds / 60:.0f} min"


def table(rows):
    lines = ["<table>", "<thead><tr>" + "".join(f"<th>{escape(column)}</th>" for column in COLUMNS) + "</tr></thead>", "<tbody>"]
    for row in rows:
        cells = [
            f"<td class=\"num\">{escape(row['start'])}</td>",
            f"<td class=\"num\">{escape(minutes(row['seconds']))}</td>",
            f"<td>{escape(row['title'])}</td>",
            f"<td>{escape(row['category'])}</td>",
            f"<td>{escape(row['folder'])}</td>",
            f"<td>{escape(row['source'])}</td>",
            f"<td>{escape(row['language'])}</td>",
            f"<td class=\"id\">{escape(row['id'])}</td>",
        ]
        lines.append("<tr>" + "".join(cells) + "</tr>")
    lines += ["</tbody>", "</table>"]
    return "\n".join(lines)


def report(conversations, offset, offset_label):
    days, undated = rows_by_day(conversations, offset)
    total = sum(len(rows) for rows in days.values())
    total_seconds = sum(row["seconds"] for rows in days.values() for row in rows)
    summary = f"Conversations: {total} · Recorded time: {total_seconds / 3600:.1f} h · Days with recordings: {len(days)}"
    if undated:
        summary += f" · Undated: {len(undated)}"
    parts = ["<!DOCTYPE html>", "<html lang=\"en\">", "<head>", "<meta charset=\"utf-8\">",
             "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
             "<title>Omi conversation report</title>", f"<style>{STYLE}</style>", "</head>", "<body>",
             "<h1>Omi conversation report</h1>",
             f"<p class=\"summary\">{escape(summary)}<br>Times shown in UTC{escape(offset_label)}.</p>"]
    if not days and not undated:
        parts.append("<p>No conversations in the export.</p>")
    for day, rows in days.items():
        day_seconds = sum(row["seconds"] for row in rows)
        parts += [f"<h2 id=\"d{escape(day)}\">{escape(day)}</h2>",
                  f"<p class=\"summary\">{len(rows)} conversation{'s' if len(rows) != 1 else ''} · {day_seconds / 3600:.1f} h</p>",
                  table(rows)]
    if undated:
        parts += ["<h2 id=\"undated\">Undated</h2>",
                  f"<p class=\"summary\">{len(undated)} conversation{'s' if len(undated) != 1 else ''} without a start time</p>",
                  table(undated)]
    parts += ["</body>", "</html>"]
    return strip_surrogates("\n".join(parts) + "\n")


def convert(sources, destination, offset=timedelta(0), offset_label=""):
    payload = report(load(sources), offset, offset_label).encode("utf-8")
    output_path = Path(destination)
    # Exclusive creation protects an existing report; a failed write leaves no partial file.
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


def main():
    parser = argparse.ArgumentParser(description="Build a self-contained HTML report of your conversations.")
    parser.add_argument("--utc-offset", default=None, help="UTC offset, e.g. +09:00 or -05:00")
    parser.add_argument("destination", help="HTML file to generate")
    parser.add_argument("sources", nargs="+", help="one or more JSON export files from omi conversation list, or '-' for stdin")
    args = parser.parse_args()

    offset = timedelta(0)
    offset_label = ""
    if args.utc_offset:
        try:
            offset = parse_offset(args.utc_offset)
            offset_label = args.utc_offset
        except ValueError as exc:
            sys.exit(f"Report failed: {exc}")

    try:
        convert(args.sources, args.destination, offset, offset_label)
    except (OSError, ValueError) as exc:
        sys.exit(f"Report failed: {exc}")
    print(f"report written to {args.destination}")


if __name__ == "__main__":
    main()
