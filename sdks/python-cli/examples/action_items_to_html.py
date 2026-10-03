"""Convert Omi action items JSON exports into a clean, self-contained HTML checklist and report.

Usage:
    # Basic export from saved JSON
    python action_items_to_html.py tasks.html action_items.json

    # With local timezone offset and custom title
    python action_items_to_html.py --utc-offset +09:00 --title "Sprint Tasks" tasks.html week1.json week2.json

    # From stdin pipeline
    omi --json action-item list --limit 200 | python action_items_to_html.py tasks.html -
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html import escape
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple
import uuid

COLUMNS = ("Status", "Due", "Description", "Created", "Conversation", "ID")

STYLE = """
:root {
  --bg: #ffffff;
  --text: #1f2937;
  --muted: #4b5563;
  --border: #e5e7eb;
  --table-header: #f9fafb;
  --row-hover: #f3f4f6;
  --badge-open-bg: #eff6ff;
  --badge-open-text: #1d4ed8;
  --badge-done-bg: #ecfdf5;
  --badge-done-text: #047857;
  --badge-overdue-bg: #fef2f2;
  --badge-overdue-text: #b91c1c;
}
body {
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  margin: 2rem auto;
  max-width: 72rem;
  padding: 0 1.25rem;
  color: var(--text);
  background: var(--bg);
  line-height: 1.5;
}
h1 { font-size: 1.75rem; font-weight: 700; margin-bottom: 0.5rem; }
h2 { font-size: 1.25rem; font-weight: 600; margin-top: 2rem; margin-bottom: 0.75rem; border-bottom: 2px solid var(--border); padding-bottom: 0.3rem; }
p.summary { color: var(--muted); font-size: 0.95rem; margin-bottom: 1.5rem; }
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}
.stat-card {
  background: var(--table-header);
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  padding: 0.75rem 1rem;
  text-align: center;
}
.stat-card .num { font-size: 1.5rem; font-weight: 700; }
.stat-card .lbl { font-size: 0.75rem; text-transform: uppercase; color: var(--muted); letter-spacing: 0.05em; }
table { border-collapse: collapse; width: 100%; font-size: 0.9rem; margin-bottom: 2rem; }
th, td { border: 1px solid var(--border); padding: 0.45rem 0.6rem; text-align: left; vertical-align: top; }
th { background: var(--table-header); font-weight: 600; }
tr:hover { background: var(--row-hover); }
td.num { white-space: nowrap; font-variant-numeric: tabular-nums; }
td.id { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 0.8rem; color: var(--muted); }
.badge {
  display: inline-block;
  padding: 0.15rem 0.45rem;
  font-size: 0.75rem;
  font-weight: 600;
  border-radius: 0.25rem;
  white-space: nowrap;
}
.badge-open { background: var(--badge-open-bg); color: var(--badge-open-text); }
.badge-done { background: var(--badge-done-bg); color: var(--badge-done-text); }
.badge-overdue { background: var(--badge-overdue-bg); color: var(--badge-overdue-text); }
.completed-row td.desc { text-decoration: line-through; color: var(--muted); }
@media print {
  body { margin: 0; max-width: none; }
  h2 { page-break-after: avoid; }
  tr { page-break-inside: avoid; }
  .stats-grid { display: flex; justify-content: space-between; }
}
"""


def text(value: Any) -> str:
    """Render a loosely typed field as one line of text; anything non-null is coerced."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(value.split())


def parse_time(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None if unusable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def parse_offset(value: str) -> timedelta:
    """Turn '+09:00' / '-05:30' into a timedelta for local calendar dates and times."""
    if len(value) != 6 or value[0] not in "+-" or value[3] != ":" or not (value[1:3] + value[4:]).isdigit():
        raise ValueError(f"UTC offset must look like +09:00, got {value!r}")
    delta = timedelta(hours=int(value[1:3]), minutes=int(value[4:]))
    if int(value[4:]) > 59 or delta > timedelta(hours=14):
        raise ValueError(f"UTC offset must be between -14:00 and +14:00, got {value!r}")
    return -delta if value[0] == "-" else delta


def unwrap_items(raw: Any, source_name: str = "") -> List[Dict[str, Any]]:
    """Unwrap an array of items, an envelope dict, or a single item object."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("action_items", "items", "data", "results"):
            candidate = raw.get(key)
            if isinstance(candidate, list):
                return candidate
        if "id" in raw or "description" in raw:
            return [raw]
    raise ValueError(f"{source_name}: expected a JSON array or envelope of action items")


def load(sources: List[str]) -> Dict[str, Dict[str, Any]]:
    """Load and deduplicate action items from multiple files or stdin."""
    items_by_id: Dict[str, Dict[str, Any]] = {}
    for source in sources:
        if source == "-":
            content = sys.stdin.buffer.read()
            source_label = "stdin"
        else:
            source_label = source
            content = Path(source).read_bytes()

        if not content.strip():
            continue

        raw = json.loads(content.decode("utf-8-sig"))
        items = unwrap_items(raw, source_label)
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"{source_label} item {idx}: each action item must be an object")
            item_id = item.get("id")
            if isinstance(item_id, str) and item_id.strip():
                clean_id = item_id.strip()
            else:
                clean_id = f"auto_{uuid.uuid4().hex}"
                while clean_id in items_by_id:
                    clean_id = f"auto_{uuid.uuid4().hex}"
            items_by_id[clean_id] = item
    return items_by_id


def is_completed(item: Dict[str, Any]) -> bool:
    """Check if an item is completed using standard truthy checks."""
    val = item.get("completed")
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "y", "done", "completed", "x")
    return False


def build_row(item_id: str, item: Dict[str, Any], offset: timedelta, now: datetime) -> Dict[str, Any]:
    due_dt = parse_time(item.get("due_at"))
    created_dt = parse_time(item.get("created_at"))
    completed = is_completed(item)
    overdue = bool(not completed and due_dt is not None and due_dt < now)

    due_str = (due_dt + offset).strftime("%Y-%m-%d %H:%M") if due_dt else ""
    created_str = (created_dt + offset).strftime("%Y-%m-%d %H:%M") if created_dt else ""

    desc = text(item.get("description")) or "(no description)"
    conv_id = text(item.get("conversation_id"))

    return {
        "id": item_id,
        "completed": completed,
        "overdue": overdue,
        "due_dt": due_dt,
        "created_dt": created_dt,
        "due_str": due_str,
        "created_str": created_str,
        "description": desc,
        "conversation_id": conv_id,
    }


def table(rows: List[Dict[str, Any]]) -> str:
    lines = [
        "<table>",
        "<thead><tr>" + "".join(f"<th>{escape(column)}</th>" for column in COLUMNS) + "</tr></thead>",
        "<tbody>",
    ]
    for row in rows:
        tr_class = ' class="completed-row"' if row["completed"] else ""
        if row["completed"]:
            badge = '<span class="badge badge-done">&#10003; Done</span>'
        elif row["overdue"]:
            badge = '<span class="badge badge-overdue">&#9888; Overdue</span>'
        else:
            badge = '<span class="badge badge-open">Open</span>'

        cells = [
            f'<td class="num">{badge}</td>',
            f'<td class="num">{escape(row["due_str"])}</td>',
            f'<td class="desc">{escape(row["description"])}</td>',
            f'<td class="num">{escape(row["created_str"])}</td>',
            f'<td class="id">{escape(row["conversation_id"])}</td>',
            f'<td class="id">{escape(row["id"])}</td>',
        ]
        lines.append(f"<tr{tr_class}>" + "".join(cells) + "</tr>")
    lines += ["</tbody>", "</table>"]
    return "\n".join(lines)


def report(
    items: Dict[str, Dict[str, Any]],
    offset: timedelta,
    offset_label: str,
    title: str = "Omi Action Items Report",
    now: Optional[datetime] = None,
) -> str:
    current_time = now or datetime.now(timezone.utc)
    rows = [build_row(item_id, item, offset, current_time) for item_id, item in items.items()]

    total = len(rows)
    completed_count = sum(1 for r in rows if r["completed"])
    open_count = total - completed_count
    overdue_count = sum(1 for r in rows if r["overdue"])

    # Group open items into overdue, upcoming (with due date), and undated
    overdue_items = [r for r in rows if r["overdue"]]
    upcoming_items = [r for r in rows if not r["completed"] and not r["overdue"] and r["due_dt"] is not None]
    undated_open = [r for r in rows if not r["completed"] and r["due_dt"] is None]
    completed_items = [r for r in rows if r["completed"]]

    # Sort upcoming by due date, others by created date or id
    overdue_items.sort(key=lambda r: (r["due_dt"] or datetime.max.replace(tzinfo=timezone.utc), r["id"]))
    upcoming_items.sort(key=lambda r: (r["due_dt"] or datetime.max.replace(tzinfo=timezone.utc), r["id"]))
    undated_open.sort(key=lambda r: (r["created_dt"] or datetime.max.replace(tzinfo=timezone.utc), r["id"]))
    completed_items.sort(key=lambda r: (r["created_dt"] or datetime.min.replace(tzinfo=timezone.utc), r["id"]), reverse=True)

    summary_text = (
        f"Total: {total} · Open: {open_count} · Completed: {completed_count} · Overdue: {overdue_count}"
    )
    tz_text = f"Times shown in UTC{offset_label}." if offset_label else "Times shown in UTC."

    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{escape(title)}</title>",
        f"<style>{STYLE}</style>",
        "</head>",
        "<body>",
        f"<h1>{escape(title)}</h1>",
        f'<p class="summary">{escape(summary_text)}<br>{escape(tz_text)}</p>',
        '<div class="stats-grid">',
        f'  <div class="stat-card"><div class="num">{total}</div><div class="lbl">Total</div></div>',
        f'  <div class="stat-card"><div class="num" style="color:var(--badge-open-text);">{open_count}</div><div class="lbl">Open</div></div>',
        f'  <div class="stat-card"><div class="num" style="color:var(--badge-done-text);">{completed_count}</div><div class="lbl">Completed</div></div>',
        f'  <div class="stat-card"><div class="num" style="color:var(--badge-overdue-text);">{overdue_count}</div><div class="lbl">Overdue</div></div>',
        "</div>",
    ]

    if not rows:
        parts.append("<p>No action items in the export.</p>")
    else:
        if overdue_items:
            parts += [
                '<h2 id="overdue">&#9888; Overdue Items</h2>',
                f'<p class="summary">{len(overdue_items)} item(s) past due date.</p>',
                table(overdue_items),
            ]
        if upcoming_items:
            parts += [
                '<h2 id="upcoming">&#128197; Open Tasks (Scheduled)</h2>',
                f'<p class="summary">{len(upcoming_items)} upcoming task(s) with due dates.</p>',
                table(upcoming_items),
            ]
        if undated_open:
            parts += [
                '<h2 id="undated">&#9776; Open Tasks (Undated)</h2>',
                f'<p class="summary">{len(undated_open)} task(s) without a due date.</p>',
                table(undated_open),
            ]
        if completed_items:
            parts += [
                '<h2 id="completed">&#10003; Completed Tasks</h2>',
                f'<p class="summary">{len(completed_items)} completed task(s).</p>',
                table(completed_items),
            ]

    parts += ["</body>", "</html>\n"]
    return "\n".join(parts)


def convert(
    sources: List[str],
    destination: str,
    offset: timedelta,
    offset_label: str,
    title: str = "Omi Action Items Report",
    overwrite: bool = False,
    now: Optional[datetime] = None,
) -> int:
    """Generate the HTML report and write it safely."""
    items = load(sources)
    html_content = report(items, offset, offset_label, title=title, now=now).encode("utf-8")
    output_path = Path(destination)
    parent_dir = output_path.parent
    parent_dir.mkdir(parents=True, exist_ok=True)

    if not overwrite:
        try:
            with output_path.open("xb") as output:
                output.write(html_content)
        except FileExistsError:
            raise FileExistsError(f"Refusing to overwrite existing {output_path} (use --overwrite to replace)") from None
    else:
        # Atomic write to temporary file in same directory, then replace destination
        with tempfile.NamedTemporaryFile("wb", dir=parent_dir, delete=False, prefix=".tmp_report_") as tmp_file:
            tmp_path = Path(tmp_file.name)
            try:
                tmp_file.write(html_content)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            except BaseException:
                tmp_path.unlink(missing_ok=True)
                raise
        tmp_path.replace(output_path)
    return len(items)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi action items JSON exports into a self-contained HTML report."
    )
    parser.add_argument("output", help="Destination HTML file path")
    parser.add_argument("inputs", nargs="+", help="One or more action items JSON export files, or '-' for stdin")
    parser.add_argument("--utc-offset", default="", help="Local UTC offset, e.g. +09:00 or --utc-offset=-05:00")
    parser.add_argument("--title", default="Omi Action Items Report", help="Report document title")
    parser.add_argument("--overwrite", action="store_true", help="Allow overwriting existing destination file")

    args = parser.parse_args(argv)

    offset = timedelta(0)
    offset_label = ""
    if args.utc_offset:
        try:
            offset = parse_offset(args.utc_offset)
            offset_label = args.utc_offset
        except ValueError as exc:
            sys.exit(f"Report failed: {exc}")

    try:
        count = convert(
            args.inputs,
            args.output,
            offset,
            offset_label,
            title=args.title,
            overwrite=args.overwrite,
        )
        print(f"Report written to {args.output} ({count} action items)")
        return 0
    except (OSError, ValueError) as exc:
        sys.exit(f"Report failed: {exc}")


if __name__ == "__main__":
    sys.exit(main())
