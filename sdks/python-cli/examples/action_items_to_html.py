#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
Convert Omi action-item list JSON export to a standalone HTML report.

Usage:
    python action_items_to_html.py tasks.json -o tasks.html
    omi --json action-item list | python action_items_to_html.py - -o tasks.html

Produces a self-contained, responsive, print-friendly HTML page summarizing
action items with status badges, due dates, completion stats, and safe HTML escaping.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

COLUMNS = ("Status", "Description", "Due Date", "Created", "Conversation ID", "Task ID")

STYLE = """
:root {
  --bg: #ffffff;
  --text: #1f2937;
  --muted: #6b7280;
  --border: #e5e7eb;
  --header-bg: #f9fafb;
  --card-bg: #ffffff;
  --card-border: #e5e7eb;
  --pending-badge-bg: #fef3c7;
  --pending-badge-text: #92400e;
  --completed-badge-bg: #d1fae5;
  --completed-badge-text: #065f46;
  --primary: #4f46e5;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #111827;
    --text: #f9fafb;
    --muted: #9ca3af;
    --border: #374151;
    --header-bg: #1f2937;
    --card-bg: #1f2937;
    --card-border: #374151;
    --pending-badge-bg: #78350f;
    --pending-badge-text: #fef3c7;
    --completed-badge-bg: #064e3b;
    --completed-badge-text: #d1fae5;
    --primary: #818cf8;
  }
}

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  margin: 2rem auto;
  max-width: 72rem;
  padding: 0 1.5rem;
  color: var(--text);
  background: var(--bg);
  line-height: 1.5;
}

h1 { font-size: 1.875rem; font-weight: 700; margin-bottom: 0.5rem; }
.subtitle { color: var(--muted); margin-bottom: 2rem; font-size: 0.95rem; }

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 1rem;
  margin-bottom: 2.5rem;
}

.stat-card {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 0.75rem;
  padding: 1rem 1.25rem;
}
.stat-label { font-size: 0.8rem; font-weight: 500; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
.stat-value { font-size: 1.75rem; font-weight: 700; color: var(--text); margin-top: 0.25rem; }

h2 { font-size: 1.25rem; font-weight: 600; margin-top: 2rem; margin-bottom: 1rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; }

table {
  border-collapse: collapse;
  width: 100%;
  font-size: 0.875rem;
  margin-bottom: 2rem;
  background: var(--card-bg);
  border-radius: 0.5rem;
  overflow: hidden;
  border: 1px solid var(--border);
}

th, td {
  padding: 0.75rem 1rem;
  text-align: left;
  vertical-align: top;
  border-bottom: 1px solid var(--border);
}

th {
  background: var(--header-bg);
  font-weight: 600;
  color: var(--text);
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

tr:last-child td { border-bottom: none; }
tr:hover { background-color: var(--header-bg); }

.badge {
  display: inline-block;
  padding: 0.2rem 0.5rem;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 600;
}
.badge-pending { background: var(--pending-badge-bg); color: var(--pending-badge-text); }
.badge-completed { background: var(--completed-badge-bg); color: var(--completed-badge-text); }

.monospace { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 0.8rem; color: var(--muted); }
.completed-desc { text-decoration: line-through; color: var(--muted); }

@media print {
  body { margin: 0; max-width: none; padding: 0; background: #fff; color: #000; }
  .stats-grid { display: flex; gap: 2rem; }
  .stat-card { border: 1px solid #ccc; }
  table { border: 1px solid #ccc; }
  th, td { border: 1px solid #ddd; }
  tr { page-break-inside: avoid; }
  h2 { page-break-after: avoid; }
}
"""


def format_iso(value: Optional[str]) -> str:
    """Format an ISO-8601 timestamp for display (YYYY-MM-DD HH:MM)."""
    if not value or not isinstance(value, str):
        return "—"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return value


def load_action_items(sources: List[str]) -> List[Dict[str, Any]]:
    """Parse one or more JSON files or stdin and return normalized action items."""
    items_by_id: Dict[str, Dict[str, Any]] = {}
    for source in sources:
        if str(source) == "-":
            raw = sys.stdin.read()
        else:
            raw = Path(source).read_bytes().decode("utf-8-sig")

        if not raw.strip():
            continue

        data = json.loads(raw)
        if isinstance(data, dict):
            items = next(
                (v for v in (data.get(k) for k in ("action_items", "items", "data")) if isinstance(v, list)),
                [data],
            )
        elif isinstance(data, list):
            items = data
        else:
            raise ValueError(f"{source}: expected JSON array or object containing action items")

        if not isinstance(items, list):
            raise ValueError(f"{source}: expected array of action items")

        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"{source}: each action item must be an object")
            item_id = item.get("id")
            if not item_id:
                raise ValueError(f"{source}: action item missing required 'id'")
            # Deduplicate by id preserving latest
            items_by_id[str(item_id)] = item

    return list(items_by_id.values())


def render_html_report(items: List[Dict[str, Any]], title: str = "Omi Action Items Report") -> str:
    """Render the action items list as a complete, standalone HTML document."""
    total = len(items)
    completed_items = []
    pending_items = []

    for item in items:
        completed = item.get("completed")
        is_completed = bool(
            completed is True
            or (isinstance(completed, str) and completed.strip().lower() in ("true", "1", "yes"))
            or (isinstance(completed, (int, float)) and completed == 1)
        )
        if is_completed:
            completed_items.append(item)
        else:
            pending_items.append(item)

    # Sort items by created_at descending
    pending_items.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    completed_items.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)

    completed_count = len(completed_items)
    pending_count = len(pending_items)
    pct_complete = (completed_count / total * 100) if total > 0 else 0

    def render_table(item_list: List[Dict[str, Any]], is_completed: bool) -> str:
        if not item_list:
            return '<p style="color: var(--muted); font-style: italic; margin-bottom: 2rem;">No items.</p>'

        lines = [
            "<table>",
            "<thead><tr>",
            "".join(f"<th>{escape(col)}</th>" for col in COLUMNS),
            "</tr></thead>",
            "<tbody>",
        ]
        for it in item_list:
            desc = escape(str(it.get("description") or it.get("title") or "(no description)"))
            desc_html = f'<span class="completed-desc">{desc}</span>' if is_completed else desc
            badge = (
                '<span class="badge badge-completed">Completed</span>'
                if is_completed
                else '<span class="badge badge-pending">Pending</span>'
            )
            due = escape(format_iso(it.get("due_at")))
            created = escape(format_iso(it.get("created_at")))
            conv_id = escape(str(it.get("conversation_id") or "—"))
            task_id = escape(str(it.get("id") or "—"))

            lines.append("<tr>")
            lines.append(f"<td>{badge}</td>")
            lines.append(f"<td>{desc_html}</td>")
            lines.append(f"<td>{due}</td>")
            lines.append(f"<td>{created}</td>")
            lines.append(f'<td class="monospace">{conv_id}</td>')
            lines.append(f'<td class="monospace">{task_id}</td>')
            lines.append("</tr>")

        lines.append("</tbody></table>")
        return "\n".join(lines)

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>{STYLE}</style>
</head>
<body>
  <h1>{escape(title)}</h1>
  <p class="subtitle">Generated on {now_utc} &bull; {total} total action item(s)</p>

  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-label">Total Tasks</div>
      <div class="stat-value">{total}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Pending</div>
      <div class="stat-value" style="color: #d97706;">{pending_count}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Completed</div>
      <div class="stat-value" style="color: #059669;">{completed_count}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Completion</div>
      <div class="stat-value">{pct_complete:.0f}%</div>
    </div>
  </div>

  <h2>Pending Action Items ({pending_count})</h2>
  {render_table(pending_items, is_completed=False)}

  <h2>Completed Action Items ({completed_count})</h2>
  {render_table(completed_items, is_completed=True)}
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert OMI action item JSON export to a standalone HTML report."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="One or more JSON files exported from omi-cli, or '-' for stdin",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="action_items.html",
        help="Output HTML file path (default: action_items.html, '-' for stdout)",
    )
    parser.add_argument(
        "--title",
        default="Omi Action Items Report",
        help="Report title displayed in header and page title",
    )

    args = parser.parse_args()

    try:
        items = load_action_items(args.inputs)
    except (OSError, ValueError) as err:
        sys.exit(f"Error loading action items: {err}")

    html_content = render_html_report(items, title=args.title)

    if args.output == "-":
        sys.stdout.write(html_content)
    else:
        out_path = Path(args.output)
        out_path.write_text(html_content, encoding="utf-8")
        print(f"Generated {out_path} with {len(items)} action item(s)")


if __name__ == "__main__":
    main()
