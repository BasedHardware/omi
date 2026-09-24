#!/usr/bin/env python3
"""Convert Omi action items JSON exports to a self-contained, printable HTML report.

Usage:
    python action_items_to_html.py action_items.json -o tasks.html
    omi --json action-item list | python action_items_to_html.py - -o tasks.html
    python action_items_to_html.py page1.json page2.json -o all_tasks.html

Writes a single HTML file with summary statistics, open and completed task tables,
clean typography, and print-ready CSS with no external stylesheets or scripts.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

COLUMNS = ("Status", "Description", "Due Date", "Created", "Conversation", "ID")

STYLE = """
body { font-family: system-ui, -apple-system, sans-serif; margin: 2rem auto; max-width: 68rem; padding: 0 1.5rem; color: #1a1a1a; background: #fff; line-height: 1.5; }
h1 { font-size: 1.6rem; margin-bottom: 0.5rem; }
h2 { font-size: 1.2rem; margin-top: 2rem; border-bottom: 2px solid #eaeaea; padding-bottom: 0.3rem; }
p.summary { color: #555; font-size: 0.95rem; margin-bottom: 1.5rem; }
.stats-cards { display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
.stat-card { border: 1px solid #e0e0e0; border-radius: 6px; padding: 0.75rem 1.25rem; min-width: 8rem; background: #fafafa; }
.stat-num { font-size: 1.4rem; font-weight: bold; }
.stat-label { font-size: 0.8rem; color: #666; text-transform: uppercase; letter-spacing: 0.5px; }
table { border-collapse: collapse; width: 100%; font-size: 0.9rem; margin-bottom: 2rem; }
th, td { border: 1px solid #e0e0e0; padding: 0.5rem 0.6rem; text-align: left; vertical-align: top; }
th { background: #f5f5f5; font-weight: 600; }
td.mono { font-family: ui-monospace, SFMono-Regular, monospace; font-size: 0.8rem; color: #555; }
td.nowrap { white-space: nowrap; }
.badge { display: inline-block; padding: 0.15rem 0.45rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }
.badge-open { background: #e3f2fd; color: #0d47a1; }
.badge-done { background: #e8f5e9; color: #1b5e20; }
@media print {
  body { margin: 0; max-width: none; padding: 0; font-size: 9pt; }
  .stats-cards { border: none; }
  .stat-card { border: 1px solid #ccc; }
  h2 { page-break-after: avoid; }
  tr { page-break-inside: avoid; }
}
"""


def utc_stamp(value: Optional[str]) -> str:
    """Normalise an ISO-8601 timestamp to UTC 'YYYY-MM-DD HH:MM:SS' text."""
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        return str(value)


def extract_action_items(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON content and extract a list of action item dictionaries."""
    raw = content.lstrip("\ufeff")
    items = json.loads(raw)

    if isinstance(items, dict):
        for key in ("action_items", "items", "data"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError(f"{source_label}: expected a JSON array or wrapped action items object")

    results: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source_label}: each action item must be a JSON object")
        if not item.get("id") or str(item.get("id")).strip() == "":
            raise ValueError(f"{source_label}: action item missing required 'id' field")
        results.append(item)

    return results


def render_html_table(items: Sequence[Dict[str, Any]]) -> str:
    """Render a sequence of action items into an HTML table."""
    if not items:
        return "<p><em>No tasks in this section.</em></p>"

    rows_html = []
    for it in items:
        completed = bool(it.get("completed", False))
        badge_cls = "badge-done" if completed else "badge-open"
        badge_txt = "Completed" if completed else "Open"

        desc = escape(str(it.get("description") or "Untitled task"))
        due = escape(utc_stamp(it.get("due_at"))) or "&mdash;"
        created = escape(utc_stamp(it.get("created_at"))) or "&mdash;"
        conv_id = escape(str(it.get("conversation_id") or "&mdash;"))
        task_id = escape(str(it.get("id") or ""))

        rows_html.append(
            f"<tr>"
            f"<td class='nowrap'><span class='badge {badge_cls}'>{badge_txt}</span></td>"
            f"<td>{desc}</td>"
            f"<td class='nowrap'>{due}</td>"
            f"<td class='nowrap'>{created}</td>"
            f"<td class='mono nowrap'>{conv_id}</td>"
            f"<td class='mono nowrap'>{task_id}</td>"
            f"</tr>"
        )

    headers_html = "".join(f"<th>{escape(col)}</th>" for col in COLUMNS)
    return f"<table><thead><tr>{headers_html}</tr></thead><tbody>{''.join(rows_html)}</tbody></table>"


def generate_html_report(items: Sequence[Dict[str, Any]], title: str = "Omi Action Items Report") -> str:
    """Generate a full standalone HTML report document."""
    # Deduplicate by id preserving order
    seen_ids = set()
    deduped: List[Dict[str, Any]] = []
    for it in items:
        tid = str(it.get("id"))
        if tid not in seen_ids:
            seen_ids.add(tid)
            deduped.append(it)

    open_tasks = [it for it in deduped if not bool(it.get("completed", False))]
    completed_tasks = [it for it in deduped if bool(it.get("completed", False))]

    total_count = len(deduped)
    open_count = len(open_tasks)
    completed_count = len(completed_tasks)
    completion_pct = round((completed_count / total_count * 100.0), 1) if total_count > 0 else 0.0

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    open_table = render_html_table(open_tasks)
    completed_table = render_html_table(completed_tasks)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escape(title)}</title>
  <style>{STYLE}</style>
</head>
<body>
  <h1>{escape(title)}</h1>
  <p class="summary">Generated on {now_utc} &bull; {total_count} total task(s) processed</p>

  <div class="stats-cards">
    <div class="stat-card">
      <div class="stat-num">{total_count}</div>
      <div class="stat-label">Total Tasks</div>
    </div>
    <div class="stat-card">
      <div class="stat-num">{open_count}</div>
      <div class="stat-label">Open Tasks</div>
    </div>
    <div class="stat-card">
      <div class="stat-num">{completed_count}</div>
      <div class="stat-label">Completed</div>
    </div>
    <div class="stat-card">
      <div class="stat-num">{completion_pct}%</div>
      <div class="stat-label">Completion Rate</div>
    </div>
  </div>

  <h2>📋 Open Tasks ({open_count})</h2>
  {open_table}

  <h2>✅ Completed Tasks ({completed_count})</h2>
  {completed_table}
</body>
</html>
"""


def convert_paths_to_html(sources: Sequence[str | Path], output_dest: Optional[str | Path] = None) -> int:
    """Convert one or more JSON files (or stdin) to an HTML report."""
    all_items: List[Dict[str, Any]] = []

    for src in sources:
        if str(src) == "-":
            content = sys.stdin.read()
            all_items.extend(extract_action_items(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_items.extend(extract_action_items(content, str(p)))

    html_content = generate_html_report(all_items)

    if output_dest and str(output_dest) != "-":
        out_path = Path(output_dest)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html_content, encoding="utf-8")
    else:
        sys.stdout.write(html_content)

    return len(all_items)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi action items JSON exports to a self-contained HTML report."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Input JSON files or '-' for standard input",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Destination HTML file (defaults to stdout)",
    )
    args = parser.parse_args()

    try:
        count = convert_paths_to_html(args.inputs, args.output)
        if args.output != "-":
            print(f"Exported {count} action item(s) to {args.output}", file=sys.stderr)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
