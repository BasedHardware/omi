#!/usr/bin/env python3
"""
Convert Omi action items JSON exports to a self-contained HTML report.

Usage:
    python action_items_to_html.py [--utc-offset +09:00] OUTPUT.html INPUT.json [INPUT.json ...]

Features:
- Self-contained HTML with zero external scripts, stylesheets, or images (print & offline friendly).
- Grouped by status (Pending Tasks vs Completed Tasks) or by calendar days.
- UTC offset support for local datetime rendering.
- Preserves task descriptions, due dates, completion status, conversation links, and IDs.
- Automatic HTML escaping to prevent XSS/injection.
- Exclusive creation (xb mode) prevents accidental overwriting.
"""

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

COLUMNS = ("Status", "Due Date", "Description", "Created At", "Conversation ID", "Task ID")

STYLE = """
body { font-family: system-ui, -apple-system, sans-serif; margin: 2rem auto; max-width: 70rem; padding: 0 1rem; color: #1a1a1a; background: #fff; line-height: 1.5; }
h1 { font-size: 1.6rem; color: #111; margin-bottom: 0.5rem; }
h2 { font-size: 1.2rem; margin-top: 2rem; border-bottom: 2px solid #eaeaea; padding-bottom: 0.3rem; color: #333; }
p.summary { color: #555; font-size: 0.95rem; margin-bottom: 1.5rem; }
table { border-collapse: collapse; width: 100%; font-size: 0.9rem; margin-top: 0.5rem; }
th, td { border: 1px solid #ddd; padding: 0.4rem 0.6rem; text-align: left; vertical-align: middle; }
th { background: #f7f7f7; font-weight: 600; color: #333; }
tr:nth-child(even) { background: #fafafa; }
td.status { font-weight: 600; text-align: center; width: 6rem; }
td.status-open { color: #d97706; background: #fef3c7; }
td.status-done { color: #059669; background: #d1fae5; }
td.date { white-space: nowrap; font-size: 0.85rem; color: #4b5563; }
td.desc { font-weight: 500; }
td.id { font-family: ui-monospace, SFMono-Regular, monospace; font-size: 0.8rem; color: #6b7280; }
@media print { body { margin: 0; max-width: none; } h2 { page-break-after: avoid; } tr { page-break-inside: avoid; } }
"""


def text(value: Any) -> str:
    """Render a loosely typed field as text; anything non-null is coerced and whitespace-normalized."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(value.split())


def parse_time(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None if unusable."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_offset(value: str) -> timedelta:
    """Turn '+09:00' / '-05:30' into a timedelta for local calendar days and clock times."""
    if len(value) != 6 or value[0] not in "+-" or value[3] != ":" or not (value[1:3] + value[4:]).isdigit():
        raise ValueError(f"UTC offset must look like +09:00 or -05:00, got {value!r}")
    delta = timedelta(hours=int(value[1:3]), minutes=int(value[4:]))
    if int(value[4:]) > 59 or delta > timedelta(hours=14):
        raise ValueError(f"UTC offset must be between -14:00 and +14:00, got {value!r}")
    return -delta if value[0] == "-" else delta


def load(sources: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """Load action items from one or more JSON files, deduplicating by ID."""
    action_items: Dict[str, Dict[str, Any]] = {}
    for source in sources:
        path = Path(source)
        if ".." in path.parts:
            raise ValueError(f"Path traversal detected: {source}")
        raw_bytes = path.read_bytes()
        try:
            items = json.loads(raw_bytes.decode("utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{source}: invalid JSON payload: {exc}")

        if isinstance(items, dict):
            items = (
                items.get("action_items")
                or items.get("items")
                or items.get("data")
                or [items]
            )
        if not isinstance(items, list):
            raise ValueError(f"{source}: expected a JSON array of action items")

        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"{source}: each action item must be an object")
            item_id = item.get("id")
            if not isinstance(item_id, (str, int)) or not str(item_id).strip():
                raise ValueError(f"{source}: each action item needs a non-empty id")
            action_items[str(item_id)] = item
    return action_items


def format_table(rows: List[Dict[str, Any]]) -> str:
    """Render a table of action items."""
    lines = ["<table>", "<thead><tr>" + "".join(f"<th>{escape(col)}</th>" for col in COLUMNS) + "</tr></thead>", "<tbody>"]
    for row in rows:
        status_class = "status-done" if row["completed"] else "status-open"
        status_label = "Completed" if row["completed"] else "Pending"
        cells = [
            f"<td class=\"status {status_class}\">{escape(status_label)}</td>",
            f"<td class=\"date\">{escape(row['due_date'])}</td>",
            f"<td class=\"desc\">{escape(row['description'])}</td>",
            f"<td class=\"date\">{escape(row['created_at'])}</td>",
            f"<td class=\"id\">{escape(row['conversation_id'])}</td>",
            f"<td class=\"id\">{escape(row['id'])}</td>",
        ]
        lines.append("<tr>" + "".join(cells) + "</tr>")
    lines += ["</tbody>", "</table>"]
    return "\n".join(lines)


def report(action_items: Dict[str, Dict[str, Any]], offset: timedelta, offset_label: str) -> str:
    """Generate self-contained HTML report document."""
    total = len(action_items)
    completed_items = []
    pending_items = []

    for item_id, item in sorted(action_items.items(), key=lambda x: str(x[0])):
        completed = bool(item.get("completed", False))
        created_dt = parse_time(item.get("created_at"))
        due_dt = parse_time(item.get("due_at"))

        created_str = (created_dt + offset).strftime("%Y-%m-%d %H:%M") if created_dt else ""
        due_str = (due_dt + offset).strftime("%Y-%m-%d %H:%M") if due_dt else "—"

        desc = text(item.get("description") or item.get("title") or "(untitled action item)")
        conv_id = text(item.get("conversation_id"))

        row = {
            "id": item_id,
            "description": desc,
            "completed": completed,
            "created_at": created_str,
            "due_date": due_str,
            "conversation_id": conv_id or "—",
        }

        if completed:
            completed_items.append(row)
        else:
            pending_items.append(row)

    summary = f"Total Action Items: {total} · Pending: {len(pending_items)} · Completed: {len(completed_items)}"
    tz_info = f"Times shown in UTC{escape(offset_label)}." if offset_label else "Times shown in UTC."

    parts = [
        "<!DOCTYPE html>",
        "<html lang=\"en\">",
        "<head>",
        "<meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        "<title>Omi Action Items Report</title>",
        f"<style>{STYLE}</style>",
        "</head>",
        "<body>",
        "<h1>Omi Action Items Report</h1>",
        f"<p class=\"summary\">{escape(summary)}<br>{tz_info}</p>",
    ]

    if not action_items:
        parts.append("<p>No action items in the export.</p>")
    else:
        parts += [
            "<h2 id=\"pending\">📌 Pending Tasks (" + str(len(pending_items)) + ")</h2>",
            format_table(pending_items) if pending_items else "<p><em>No pending tasks.</em></p>",
            "<h2 id=\"completed\">✅ Completed Tasks (" + str(len(completed_items)) + ")</h2>",
            format_table(completed_items) if completed_items else "<p><em>No completed tasks.</em></p>",
        ]

    parts += ["</body>", "</html>"]
    return "\n".join(parts) + "\n"


def convert(sources: Sequence[str], destination: str, offset: timedelta, offset_label: str) -> None:
    """Read JSON exports and write report to HTML destination with exclusive-create guard."""
    output_path = Path(destination)
    if ".." in output_path.parts:
        raise ValueError(f"Path traversal detected: {destination}")
    payload = report(load(sources), offset, offset_label).encode("utf-8")

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


if __name__ == "__main__":
    args = sys.argv[1:]
    offset, offset_label = timedelta(0), ""
    if len(args) >= 2 and args[0] == "--utc-offset":
        try:
            offset = parse_offset(args[1])
        except ValueError as exc:
            sys.exit(f"Report failed: {exc}")
        offset_label = args[1]
        args = args[2:]
    if len(args) < 2:
        sys.exit("Usage: python action_items_to_html.py [--utc-offset +09:00] OUTPUT.html INPUT.json [INPUT.json ...]")
    try:
        convert(args[1:], args[0], offset, offset_label)
    except (OSError, ValueError) as exc:
        sys.exit(f"Report failed: {exc}")
    print(f"report written to {args[0]}")
