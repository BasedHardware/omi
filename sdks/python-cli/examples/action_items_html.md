# Build a self-contained HTML task dashboard of your action items

Use this recipe to browse, filter, or print a structured report of your Omi
action items and tasks without the CLI or a spreadsheet. It turns one or more
`action-item list` exports into a single standalone HTML dashboard featuring:

- **Executive summary metrics**: total tasks, pending/open count, completed count, and completion rate percentage.
- **Sectioned task tables**: separate interactive sections for pending and completed commitments.
- **Due dates and conversation anchors**: highlighting actionable deadlines and links to originating conversations.
- **Zero external assets**: no remote CSS, JS CDNs, or images; works 100% offline and includes `@media print` styles for clean paper/PDF export.

You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

---

## Quickstart

### 1. Direct Pipeline Export (Stdout to HTML)

Stream up to 500 action items directly into a standalone HTML dashboard:

```sh
omi --json action-item list --limit 500 | python action_items_html.py - tasks_dashboard.html
```

### 2. Export from a Saved JSON File

If you have already saved an export:

```sh
omi --json action-item list --limit 500 > action_items.json
python action_items_html.py action_items.json tasks_dashboard.html
```

Check that the command succeeded before converting the file.

### 3. Filter by Status (Pending Tasks Only)

Export only open, pending action items:

```sh
python action_items_html.py action_items.json pending_tasks.html --status open
```

---

## Converter Script

Save the following as `action_items_html.py`:

```python
import argparse
import json
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path

STYLE = """
:root {
  --bg-color: #f8fafc;
  --card-bg: #ffffff;
  --text-main: #0f172a;
  --text-muted: #64748b;
  --border-color: #e2e8f0;
  --primary: #2563eb;
  --badge-open-bg: #fef3c7;
  --badge-open-text: #92400e;
  --badge-done-bg: #dcfce7;
  --badge-done-text: #166534;
}
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  margin: 2rem auto;
  max-width: 64rem;
  padding: 0 1.5rem;
  color: var(--text-main);
  background: var(--bg-color);
  line-height: 1.5;
}
header {
  margin-bottom: 2rem;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 1rem;
}
h1 { font-size: 1.8rem; margin: 0 0 0.5rem 0; font-weight: 700; }
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 1rem;
  margin: 1.5rem 0;
}
.stat-card {
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 0.5rem;
  padding: 1rem;
  text-align: center;
}
.stat-value { font-size: 1.6rem; font-weight: 700; color: var(--primary); }
.stat-label { font-size: 0.85rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }
h2 { font-size: 1.25rem; margin-top: 2rem; color: var(--text-main); display: flex; align-items: center; gap: 0.5rem; }
.badge {
  display: inline-block;
  font-size: 0.75rem;
  font-weight: 600;
  padding: 0.2rem 0.55rem;
  border-radius: 9999px;
  text-transform: uppercase;
}
.badge-open { background: var(--badge-open-bg); color: var(--badge-open-text); }
.badge-done { background: var(--badge-done-bg); color: var(--badge-done-text); }
table {
  border-collapse: collapse;
  width: 100%;
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 0.5rem;
  overflow: hidden;
  margin-bottom: 2rem;
  font-size: 0.9rem;
}
th, td {
  padding: 0.75rem 1rem;
  text-align: left;
  border-bottom: 1px solid var(--border-color);
}
th { background: #f1f5f9; font-weight: 600; color: var(--text-muted); font-size: 0.8rem; text-transform: uppercase; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: #f8fafc; }
.checkbox { font-size: 1.1rem; }
.due-date { white-space: nowrap; color: #dc2626; font-weight: 500; font-size: 0.85rem; }
.origin { font-family: monospace; font-size: 0.8rem; color: var(--text-muted); }
@media print {
  body { margin: 0; max-width: none; background: #fff; padding: 0; }
  .stat-card, table { border: 1px solid #ccc; }
  h2 { page-break-after: avoid; }
  tr { page-break-inside: avoid; }
}
"""


def sanitize_text(value):
    """Render loosely typed field as single-line plain string."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(value.split())


def render_html(items, title="Omi Action Items Dashboard"):
    """Generate self-contained HTML task dashboard."""
    total = len(items)
    completed_count = sum(1 for it in items if it.get("completed"))
    open_count = total - completed_count
    rate = f"{(completed_count / total * 100):.1f}%" if total > 0 else "0.0%"

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    open_items = [it for it in items if not it.get("completed")]
    done_items = [it for it in items if it.get("completed")]

    def render_table(task_list, is_completed):
        if not task_list:
            return '<p style="color: var(--text-muted); font-style: italic;">No tasks in this section.</p>'
        rows = []
        for it in task_list:
            desc = escape(sanitize_text(it.get("description") or "(untitled task)"))
            due_at = sanitize_text(it.get("due_at"))
            due_display = escape(due_at[:10]) if due_at else '<span style="color: var(--text-muted);">-</span>'
            created_at = sanitize_text(it.get("created_at"))
            created_display = escape(created_at[:10]) if created_at else "-"
            origin = escape(sanitize_text(it.get("conversation_id") or "-"))
            status_badge = '<span class="badge badge-done">Done</span>' if is_completed else '<span class="badge badge-open">Pending</span>'
            checkbox = "☑" if is_completed else "☐"

            rows.append(f"""
            <tr>
              <td style="width: 2rem; text-align: center;"><span class="checkbox">{checkbox}</span></td>
              <td><strong>{desc}</strong></td>
              <td style="width: 6rem;">{status_badge}</td>
              <td style="width: 7rem;"><span class="due-date">{due_display}</span></td>
              <td style="width: 7rem; color: var(--text-muted);">{created_display}</td>
              <td style="width: 6rem;"><span class="origin">{origin}</span></td>
            </tr>
            """)
        return f"""
        <table>
          <thead>
            <tr>
              <th></th>
              <th>Task Description</th>
              <th>Status</th>
              <th>Due Date</th>
              <th>Created</th>
              <th>Conversation</th>
            </tr>
          </thead>
          <tbody>
            {''.join(rows)}
          </tbody>
        </table>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
{STYLE}
  </style>
</head>
<body>
  <header>
    <h1>{escape(title)}</h1>
    <p style="color: var(--text-muted); margin: 0;">Exported from Omi Wearable CLI · Generated on {now_str}</p>
  </header>

  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-value">{total}</div>
      <div class="stat-label">Total Tasks</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" style="color: #d97706;">{open_count}</div>
      <div class="stat-label">Pending / Open</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" style="color: #16a34a;">{completed_count}</div>
      <div class="stat-label">Completed</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">{rate}</div>
      <div class="stat-label">Completion Rate</div>
    </div>
  </div>

  <h2>Pending Tasks ({len(open_items)})</h2>
  {render_table(open_items, False)}

  <h2>Completed Tasks ({len(done_items)})</h2>
  {render_table(done_items, True)}
</body>
</html>
"""
    return html


def convert(source: str, destination: str, title: str = "Omi Action Items Dashboard", status_filter: str = "all"):
    """Convert input JSON or stdin to standalone HTML dashboard."""
    if source == "-":
        content = sys.stdin.read()
    else:
        content = Path(source).read_text(encoding="utf-8")

    data = json.loads(content)
    if isinstance(data, dict) and "action_items" in data:
        data = data["action_items"]
    if not isinstance(data, list):
        raise ValueError("Expected a JSON array of action items from 'omi --json action-item list'")

    items = []
    seen_ids = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if item_id and item_id in seen_ids:
            continue
        if item_id:
            seen_ids.add(item_id)

        completed = bool(item.get("completed"))
        if status_filter == "open" and completed:
            continue
        if status_filter == "completed" and not completed:
            continue
        items.append(item)

    payload = render_html(items, title=title)
    output_path = Path(destination)
    output_path.write_text(payload, encoding="utf-8")
    return len(items)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Omi action items JSON export to standalone HTML dashboard.")
    parser.add_argument("source", help="Path to input JSON file or '-' for stdin.")
    parser.add_argument("destination", help="Path to output HTML file.")
    parser.add_argument(
        "--status",
        choices=["all", "open", "completed"],
        default="all",
        help="Filter action items by status: all (default), open, or completed."
    )
    parser.add_argument("--title", default="Omi Action Items Dashboard", help="Custom dashboard page title.")

    args = parser.parse_args()

    try:
        count = convert(args.source, args.destination, title=args.title, status_filter=args.status)
    except (ValueError, OSError) as exc:
        sys.exit(f"Conversion failed: {exc}")

    print(f"Successfully rendered {count} action item{'s' if count != 1 else ''} to {args.destination}")
```
