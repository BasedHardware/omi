"""Convert Omi conversations JSON exports into a clean, self-contained HTML report.

Usage:
    # Print HTML report to stdout from saved export
    python conversations_to_html.py conversations.json

    # Write report to file
    python conversations_to_html.py conversations.json -o week.html

    # With local timezone offset and custom title
    python conversations_to_html.py conversations.json --utc-offset +09:00 --title "Weekly Standups" -o report.html

    # Stream from omi CLI pipeline
    omi --json conversation list --limit 200 | python conversations_to_html.py - -o conversations.html
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
from typing import Any, Dict, List, Optional, Sequence, Tuple
import uuid

COLUMNS = ("Start", "Duration", "Title", "Category", "Folder", "Source", "Language", "ID")

DEFAULT_TITLE = "Omi Conversation Report"

STYLE = """
:root {
  --bg: #ffffff;
  --text: #1f2937;
  --muted: #4b5563;
  --border: #e5e7eb;
  --table-header: #f9fafb;
  --row-hover: #f3f4f6;
  --tag-bg: #eff6ff;
  --tag-text: #1d4ed8;
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
h2 {
  font-size: 1.25rem;
  font-weight: 600;
  margin-top: 2rem;
  margin-bottom: 0.75rem;
  border-bottom: 2px solid var(--border);
  padding-bottom: 0.3rem;
}
p.summary { color: var(--muted); font-size: 0.95rem; margin-bottom: 1.5rem; }
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
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
.stat-card .num { font-size: 1.5rem; font-weight: 700; color: var(--text); }
.stat-card .lbl { font-size: 0.75rem; text-transform: uppercase; color: var(--muted); letter-spacing: 0.05em; }
table { border-collapse: collapse; width: 100%; font-size: 0.9rem; margin-bottom: 2rem; }
th, td { border: 1px solid var(--border); padding: 0.45rem 0.6rem; text-align: left; vertical-align: top; }
th { background: var(--table-header); font-weight: 600; }
tr:hover { background: var(--row-hover); }
td.num { white-space: nowrap; font-variant-numeric: tabular-nums; text-align: right; }
td.id {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.8rem;
  color: var(--muted);
}
.badge {
  display: inline-block;
  padding: 0.15rem 0.45rem;
  border-radius: 0.25rem;
  font-size: 0.75rem;
  font-weight: 500;
  background: var(--tag-bg);
  color: var(--tag-text);
}
@media print {
  body { margin: 0; max-width: none; padding: 0; }
  h2 { page-break-after: avoid; }
  tr { page-break-inside: avoid; }
  .stats-grid { break-inside: avoid; }
}
"""


def text(value: Any) -> str:
    """Render a field as safe text, dropping C0 control codes, surrogates, and noncharacters."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    collapsed = " ".join(value.split())
    return "".join(
        ch for ch in collapsed
        if ch >= " " and not ("\ud800" <= ch <= "\udfff") and ch not in ("\ufffe", "\uffff")
    )


def parse_time(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None if unusable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
        return parsed
    except (ValueError, OverflowError):
        return None


def parse_offset(value: str) -> timedelta:
    """Turn '+09:00' / '-05:30' into a timedelta for local calendar days and clock times."""
    val = value.strip()
    if len(val) != 6 or val[0] not in "+-" or val[3] != ":" or not (val[1:3] + val[4:]).isdigit():
        raise ValueError(f"UTC offset must match '+HH:MM' or '-HH:MM' (e.g. '+09:00'), got {value!r}")
    hours = int(val[1:3])
    minutes = int(val[4:])
    if minutes > 59 or hours > 14 or (hours == 14 and minutes > 0):
        raise ValueError(f"UTC offset must be between -14:00 and +14:00, got {value!r}")
    delta = timedelta(hours=hours, minutes=minutes)
    return -delta if val[0] == "-" else delta


def format_duration(seconds: int) -> str:
    """Format duration into human-readable minutes or hours:minutes."""
    if seconds <= 0:
        return "0 min"
    if seconds < 3600:
        mins = seconds / 60.0
        return f"{mins:.0f} min" if mins >= 1 else "< 1 min"
    hours = seconds // 3600
    rem_mins = (seconds % 3600) // 60
    return f"{hours}h {rem_mins}m" if rem_mins else f"{hours}h"


def unwrap_conversations(raw: Any, source_label: str) -> List[Any]:
    """Extract conversations list from various JSON envelopes."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("conversations", "items", "data", "results"):
            val = raw.get(key)
            if isinstance(val, list):
                return val
        if any(k in raw for k in ("id", "started_at", "structured")):
            return [raw]
        return []
    raise ValueError(f"{source_label}: expected JSON array or object containing conversations")


def load(sources: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """Load and deduplicate conversations from files or stdin."""
    conversations_by_id: Dict[str, Dict[str, Any]] = {}
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
        items = unwrap_conversations(raw, source_label)
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"{source_label} item {idx}: each conversation must be an object")
            item_id = item.get("id")
            if item_id is not None and str(item_id).strip():
                clean_id = str(item_id).strip()
            else:
                clean_id = f"auto_{uuid.uuid4().hex}"
                while clean_id in conversations_by_id:
                    clean_id = f"auto_{uuid.uuid4().hex}"
            conversations_by_id[clean_id] = item
    return conversations_by_id


def rows_by_day(
    conversations: Dict[str, Dict[str, Any]],
    offset: timedelta,
) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
    """Group conversations into local calendar days; returns (days, undated)."""
    days: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    undated: List[Dict[str, Any]] = []

    for item_id, item in conversations.items():
        start = parse_time(item.get("started_at"))
        end = parse_time(item.get("finished_at"))
        structured = item.get("structured")
        if not isinstance(structured, dict):
            structured = {}

        seconds = (
            int((end - start).total_seconds())
            if start is not None and end is not None and end >= start
            else 0
        )

        title = text(structured.get("title")) or text(item.get("title")) or "(untitled conversation)"
        category = text(structured.get("category")) or text(item.get("category"))
        folder = text(item.get("folder_name")) or text(item.get("folder"))
        source = text(item.get("source"))
        language = text(item.get("language"))

        row = {
            "id": item_id,
            "start": (start + offset).strftime("%H:%M") if start is not None else "",
            "sort": start if start is not None else datetime.max.replace(tzinfo=timezone.utc),
            "seconds": seconds,
            "title": title,
            "category": category,
            "folder": folder,
            "source": source,
            "language": language,
        }

        if start is None:
            undated.append(row)
        else:
            day_str = (start + offset).strftime("%Y-%m-%d")
            days[day_str].append(row)

    for bucket in list(days.values()) + [undated]:
        bucket.sort(key=lambda r: (r["sort"], r["id"]))

    return dict(sorted(days.items())), undated


def render_table(rows: List[Dict[str, Any]]) -> str:
    """Render HTML table for a list of conversation rows."""
    lines = [
        "<table>",
        "  <thead>",
        "    <tr>" + "".join(f"<th>{escape(col)}</th>" for col in COLUMNS) + "</tr>",
        "  </thead>",
        "  <tbody>",
    ]
    for row in rows:
        badge_html = f'<span class="badge">{escape(row["category"])}</span>' if row["category"] else ""
        cells = [
            f'<td class="num">{escape(row["start"])}</td>',
            f'<td class="num">{escape(format_duration(row["seconds"]))}</td>',
            f'<td><strong>{escape(row["title"])}</strong></td>',
            f'<td>{badge_html}</td>',
            f'<td>{escape(row["folder"])}</td>',
            f'<td>{escape(row["source"])}</td>',
            f'<td>{escape(row["language"])}</td>',
            f'<td class="id">{escape(row["id"])}</td>',
        ]
        lines.append("    <tr>" + "".join(cells) + "</tr>")
    lines.append("  </tbody>")
    lines.append("</table>")
    return "\n".join(lines)


def build_report(
    conversations: Dict[str, Dict[str, Any]],
    offset: timedelta = timedelta(0),
    offset_label: str = "+00:00",
    report_title: str = DEFAULT_TITLE,
) -> str:
    """Format conversations into a self-contained, printable HTML report."""
    clean_title = text(report_title).strip() or DEFAULT_TITLE
    days, undated = rows_by_day(conversations, offset)

    total_dated = sum(len(rows) for rows in days.values())
    total_convs = total_dated + len(undated)
    total_seconds = sum(row["seconds"] for rows in days.values() for row in rows) + sum(
        row["seconds"] for row in undated
    )
    total_hours = total_seconds / 3600.0
    days_count = len(days)

    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="utf-8">',
        '  <meta name="viewport" content="width=device-width, initial-scale=1">',
        f"  <title>{escape(clean_title)}</title>",
        f"  <style>{STYLE}</style>",
        "</head>",
        "<body>",
        f"  <h1>{escape(clean_title)}</h1>",
        f'  <p class="summary">Generated report with times shown in UTC{escape(offset_label)}.</p>',
        '  <div class="stats-grid">',
        '    <div class="stat-card">',
        f'      <div class="num">{total_convs}</div>',
        '      <div class="lbl">Conversations</div>',
        '    </div>',
        '    <div class="stat-card">',
        f'      <div class="num">{total_hours:.1f}h</div>',
        '      <div class="lbl">Recorded Time</div>',
        '    </div>',
        '    <div class="stat-card">',
        f'      <div class="num">{days_count}</div>',
        '      <div class="lbl">Active Days</div>',
        '    </div>',
        '    <div class="stat-card">',
        f'      <div class="num">{len(undated)}</div>',
        '      <div class="lbl">Undated</div>',
        '    </div>',
        "  </div>",
    ]

    if not days and not undated:
        parts.append('  <p class="summary">No conversations found in the exported data.</p>')

    for day_str, rows in days.items():
        day_seconds = sum(r["seconds"] for r in rows)
        day_hours = day_seconds / 3600.0
        parts.append(f'  <h2 id="d{escape(day_str)}">{escape(day_str)}</h2>')
        parts.append(
            f'  <p class="summary">{len(rows)} conversation{"s" if len(rows) != 1 else ""} · {day_hours:.1f} hours</p>'
        )
        parts.append(render_table(rows))

    if undated:
        parts.append('  <h2 id="undated">Undated</h2>')
        parts.append(
            f'  <p class="summary">{len(undated)} conversation{"s" if len(undated) != 1 else ""}'
            ' without valid start timestamp</p>'
        )
        parts.append(render_table(undated))

    parts.append("</body>")
    parts.append("</html>\n")
    return "\n".join(parts)


def convert(
    sources: Sequence[str],
    destination: Optional[str] = None,
    utc_offset: str = "+00:00",
    report_title: str = DEFAULT_TITLE,
    overwrite: bool = False,
) -> int:
    """Load conversations, build HTML report, and write to destination file or stdout."""
    offset = parse_offset(utc_offset)
    conversations = load(sources)
    html_content = build_report(
        conversations,
        offset=offset,
        offset_label=utc_offset,
        report_title=report_title,
    )
    payload = html_content.encode("utf-8")
    count = len(conversations)

    if not destination or destination == "-":
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
        return count

    output_path = Path(destination)
    parent_dir = output_path.parent
    parent_dir.mkdir(parents=True, exist_ok=True)

    if not overwrite:
        try:
            output = output_path.open("xb")
        except FileExistsError:
            raise FileExistsError(
                f"Refusing to overwrite existing {output_path} (use --overwrite to replace)"
            ) from None
        try:
            os.chmod(output_path, 0o644)
            with output:
                output.write(payload)
        except OSError:
            output_path.unlink(missing_ok=True)
            raise
    else:
        tmp_name = f".tmp_conversations_html_{uuid.uuid4().hex}.html"
        tmp_path = parent_dir / tmp_name
        try:
            with tmp_path.open("xb") as tmp_file:
                os.chmod(tmp_path, 0o644)
                tmp_file.write(payload)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            os.chmod(tmp_path, 0o644)
            tmp_path.replace(output_path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

    return count


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi conversations JSON exports into a self-contained HTML report."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="One or more conversation JSON export files, or '-' for stdin",
    )
    parser.add_argument("-o", "--output", help="Destination HTML file path (defaults to stdout)")
    parser.add_argument(
        "--utc-offset",
        default="+00:00",
        help="UTC timezone offset for clock times and day groupings, e.g. +09:00 or -05:00 (default: +00:00)",
    )
    parser.add_argument(
        "--title",
        default=DEFAULT_TITLE,
        help=f"HTML report title (default: '{DEFAULT_TITLE}')",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting existing destination file",
    )

    args = parser.parse_args(argv)

    try:
        count = convert(
            args.inputs,
            destination=args.output,
            utc_offset=args.utc_offset,
            report_title=args.title,
            overwrite=args.overwrite,
        )
        if args.output and args.output != "-":
            print(f"HTML report written to {args.output} ({count} conversations)")
        return 0
    except BrokenPipeError:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        os.close(devnull)
        return 1
    except (OSError, ValueError) as exc:
        sys.exit(f"HTML report generation failed: {exc}")


if __name__ == "__main__":
    sys.exit(main())
