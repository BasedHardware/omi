# Build a self-contained HTML report of your action items

Use this recipe to browse, search, or print your Omi action items and tasks
without spreadsheet software: it turns one or more `action-item list` JSON exports
into a single responsive HTML dashboard with summary metrics (total tasks,
completed, pending, completion rate), live search filtering, status tabs, and
clean printable styles. It reads saved JSON exports, makes zero network
requests, embeds all CSS and filtering logic inline, and refuses to overwrite
existing reports accidentally. You need Python 3.10+ and an authenticated
`omi-cli` for the initial export.

Export the action items you want to report on:

```sh
omi --json action-item list --limit 200 --offset 0 > action_items.json
```

Check that the export succeeded before converting the file. To include multiple
pages, repeat with `--offset 200`, `--offset 400`, etc., into separate files.

Save the following as `action_items_to_html.py`:

```python
import html
import json
import sys
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path

STYLE = """
:root {
  --bg: #ffffff;
  --surface: #f8fafc;
  --border: #e2e8f0;
  --text: #0f172a;
  --muted: #64748b;
  --accent: #2563eb;
  --badge-green-bg: #dcfce7;
  --badge-green-text: #166534;
  --badge-amber-bg: #fef3c7;
  --badge-amber-text: #92400e;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f172a;
    --surface: #1e293b;
    --border: #334155;
    --text: #f8fafc;
    --muted: #94a3b8;
    --accent: #38bdf8;
    --badge-green-bg: #14532d;
    --badge-green-text: #86efac;
    --badge-amber-bg: #78350f;
    --badge-amber-text: #fde68a;
  }
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background-color: var(--bg);
  color: var(--text);
  line-height: 1.5;
  padding: 2rem 1.5rem;
  max-width: 1000px;
  margin: 0 auto;
}
header { margin-bottom: 2rem; }
h1 { font-size: 1.875rem; font-weight: 700; margin-bottom: 0.5rem; }
.meta { color: var(--muted); font-size: 0.875rem; margin-bottom: 1.5rem; }
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}
.stat-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1rem 1.25rem;
}
.stat-label { font-size: 0.8125rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }
.stat-value { font-size: 1.75rem; font-weight: 700; margin-top: 0.25rem; }
.controls {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  align-items: center;
  margin-bottom: 1.5rem;
}
.search-box {
  flex: 1;
  min-width: 240px;
  padding: 0.6rem 0.875rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  font-size: 0.9375rem;
}
.filter-btn {
  background: var(--surface);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 0.55rem 0.9rem;
  border-radius: 6px;
  font-size: 0.875rem;
  cursor: pointer;
  font-weight: 500;
}
.filter-btn.active {
  background: var(--accent);
  color: #ffffff;
  border-color: var(--accent);
}
table {
  width: 100%;
  border-collapse: collapse;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}
th {
  text-align: left;
  padding: 0.75rem 1rem;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
  border-bottom: 1px solid var(--border);
}
td {
  padding: 0.875rem 1rem;
  border-bottom: 1px solid var(--border);
  font-size: 0.9375rem;
  vertical-align: top;
}
tr:last-child td { border-bottom: none; }
tr:hover td { background-color: rgba(148, 163, 184, 0.05); }
.badge {
  display: inline-block;
  font-size: 0.75rem;
  font-weight: 600;
  padding: 0.2rem 0.55rem;
  border-radius: 9999px;
  text-transform: uppercase;
  letter-spacing: 0.025em;
  white-space: nowrap;
}
.badge-completed { background: var(--badge-green-bg); color: var(--badge-green-text); }
.badge-pending { background: var(--badge-amber-bg); color: var(--badge-amber-text); }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 0.8125rem; color: var(--muted); }
.desc { word-break: break-word; font-weight: 500; }
.empty-msg { text-align: center; padding: 3rem 1rem; color: var(--muted); }
@media print {
  body { padding: 0; background: #fff; color: #000; }
  .controls { display: none; }
  table { border: 1px solid #ccc; }
  th, td { border-bottom: 1px solid #eee; }
}
"""

COLUMNS = ["Status", "Description", "Due Date", "Created", "Conversation ID", "Action Item ID"]


def clean_text(value):
    """Normalize text whitespace and return cleaned string or empty string."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
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
    """Turn '+09:00' / '-05:30' into a timedelta for local timezone display."""
    if len(value) != 6 or value[0] not in "+-" or value[3] != ":" or not (value[1:3] + value[4:]).isdigit():
        raise ValueError(f"UTC offset must look like +09:00 or -05:00, got {value!r}")
    delta = timedelta(hours=int(value[1:3]), minutes=int(value[4:]))
    if int(value[4:]) > 59 or delta > timedelta(hours=14):
        raise ValueError(f"UTC offset must be between -14:00 and +14:00, got {value!r}")
    return -delta if value[0] == "-" else delta


def load_action_items(sources):
    """Load and deduplicate action items from multiple JSON source files."""
    items_map = OrderedDict()
    for source in sources:
        path = Path(source)
        payload = json.loads(path.read_bytes())
        if not isinstance(payload, list):
            raise ValueError(f"{source}: expected JSON array from 'omi --json action-item list'")
        for raw in payload:
            if not isinstance(raw, dict):
                raise ValueError(f"{source}: each action item must be a JSON object")
            item_id = raw.get("id")
            if not isinstance(item_id, str) or not item_id:
                raise ValueError(f"{source}: action item missing non-empty string 'id'")
            items_map[item_id] = raw
    return list(items_map.values())


def format_timestamp(dt, offset):
    """Format UTC datetime with timezone offset into 'YYYY-MM-DD HH:MM' string."""
    if dt is None:
        return "-"
    local_dt = dt + offset
    return local_dt.strftime("%Y-%m-%d %H:%M")


def build_report_html(items, offset, offset_label, title="Omi Action Items Report"):
    """Generate self-contained HTML document string with summary cards and task table."""
    total = len(items)
    completed_count = sum(1 for it in items if bool(it.get("completed")))
    pending_count = total - completed_count
    rate = (completed_count / total * 100) if total > 0 else 0.0

    rows_html = []
    for it in items:
        is_completed = bool(it.get("completed"))
        desc = clean_text(it.get("description")) or "(no description)"
        due_dt = parse_time(it.get("due_at"))
        created_dt = parse_time(it.get("created_at"))
        conv_id = clean_text(it.get("conversation_id")) or "-"
        item_id = clean_text(it.get("id"))

        badge_class = "badge-completed" if is_completed else "badge-pending"
        badge_text = "Completed" if is_completed else "Pending"
        filter_status = "completed" if is_completed else "pending"

        due_str = format_timestamp(due_dt, offset)
        created_str = format_timestamp(created_dt, offset)

        row = f"""<tr data-status="{filter_status}" data-desc="{html.escape(desc.lower())}">
  <td><span class="badge {badge_class}">{badge_text}</span></td>
  <td class="desc">{html.escape(desc)}</td>
  <td>{html.escape(due_str)}</td>
  <td>{html.escape(created_str)}</td>
  <td class="mono">{html.escape(conv_id)}</td>
  <td class="mono">{html.escape(item_id)}</td>
</tr>"""
        rows_html.append(row)

    table_body = "\n".join(rows_html) if rows_html else """<tr><td colspan="6" class="empty-msg">No action items found in export.</td></tr>"""

    js_filter = """<script>
function filterItems() {
  const query = document.getElementById('search').value.toLowerCase();
  const activeBtn = document.querySelector('.filter-btn.active');
  const status = activeBtn ? activeBtn.getAttribute('data-filter') : 'all';
  const rows = document.querySelectorAll('tbody tr');
  rows.forEach(row => {
    if (!row.getAttribute('data-status')) return;
    const rowStatus = row.getAttribute('data-status');
    const rowDesc = row.getAttribute('data-desc') || '';
    const matchStatus = (status === 'all' || rowStatus === status);
    const matchQuery = !query || rowDesc.includes(query);
    row.style.display = (matchStatus && matchQuery) ? '' : 'none';
  });
}
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');
      filterItems();
    });
  });
  const searchInput = document.getElementById('search');
  if (searchInput) {
    searchInput.addEventListener('input', filterItems);
  }
});
</script>"""

    tz_info = f"Times shown in UTC{offset_label}." if offset_label else "Times shown in UTC."

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>{STYLE}</style>
</head>
<body>
  <header>
    <h1>{html.escape(title)}</h1>
    <p class="meta">Generated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")} · {tz_info}</p>
  </header>

  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-label">Total Tasks</div>
      <div class="stat-value">{total}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Completed</div>
      <div class="stat-value" style="color: var(--badge-green-text);">{completed_count}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Pending</div>
      <div class="stat-value" style="color: var(--badge-amber-text);">{pending_count}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Completion Rate</div>
      <div class="stat-value">{rate:.1f}%</div>
    </div>
  </div>

  <div class="controls">
    <input type="text" id="search" class="search-box" placeholder="Search tasks by description...">
    <div>
      <button class="filter-btn active" data-filter="all">All ({total})</button>
      <button class="filter-btn" data-filter="pending">Pending ({pending_count})</button>
      <button class="filter-btn" data-filter="completed">Completed ({completed_count})</button>
    </div>
  </div>

  <table>
    <thead>
      <tr>
        {"".join(f"<th>{html.escape(c)}</th>" for c in COLUMNS)}
      </tr>
    </thead>
    <tbody>
      {table_body}
    </tbody>
  </table>

  {js_filter}
</body>
</html>
"""


def convert(sources, destination, offset, offset_label, title="Omi Action Items Report"):
    """Load items and write report HTML securely to destination file."""
    items = load_action_items(sources)
    payload = build_report_html(items, offset, offset_label, title=title).encode("utf-8")
    output_path = Path(destination)
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
    title = "Omi Action Items Report"

    while args and args[0].startswith("--"):
        if args[0] == "--utc-offset":
            if len(args) < 2:
                sys.exit("Error: --utc-offset requires an argument (e.g. +09:00)")
            try:
                offset = parse_offset(args[1])
            except ValueError as exc:
                sys.exit(f"Report failed: {exc}")
            offset_label = args[1]
            args = args[2:]
        elif args[0] == "--title":
            if len(args) < 2:
                sys.exit("Error: --title requires a title string")
            title = args[1]
            args = args[2:]
        else:
            sys.exit(f"Unknown option: {args[0]}")

    if len(args) < 2:
        sys.exit("Usage: python action_items_to_html.py [--utc-offset +09:00] [--title 'My Tasks'] OUTPUT.html INPUT.json [INPUT.json ...]")

    dest = args[0]
    srcs = args[1:]
    try:
        convert(srcs, dest, offset, offset_label, title=title)
        print(f"Report successfully written to {dest}")
    except (OSError, ValueError) as exc:
        sys.exit(f"Report failed: {exc}")
```

Run it (the output file comes first, then one or more exports):

```sh
python action_items_to_html.py --utc-offset +09:00 tasks_report.html action_items.json
```

Open `tasks_report.html` in your web browser. You can click the **Pending** or
**Completed** buttons to filter tasks instantly, or type keywords in the search
bar. All timestamps are displayed in your configured timezone. Print the page
or export to PDF using `Ctrl+P` / `Cmd+P` with interactive controls cleanly
hidden.
