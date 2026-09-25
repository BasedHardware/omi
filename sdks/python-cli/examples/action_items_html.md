# Build a self-contained HTML report of action items

Use this recipe to browse or print your Omi action items and tasks without
the CLI or a spreadsheet: it turns one or more `action-item list` exports into
a single, clean HTML dashboard with summary metrics (Total, Completed, Pending,
and Overdue tasks), visual checkmark indicators, status badges, due dates,
and conversation references.

It reads saved JSON exports, makes no network requests, and writes one
HTML file with no external scripts, remote stylesheets, or tracking images.
You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export up to 200 action items per page:

```sh
omi --json action-item list --limit 200 --offset 0 > page1.json
```

Check that the command succeeded before converting the file. If you have more
tasks, retrieve additional pages into separate files (e.g. `page2.json`)
using `--offset 200`. The report accepts multiple files and automatically
deduplicates records by action item ID.

Save the following as `action_items_html.py`:

```python
import json
import sys
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

STYLE = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 2rem auto; max-width: 65rem; padding: 0 1.5rem; color: #1e293b; background: #f8fafc; line-height: 1.5; }
h1 { font-size: 1.75rem; font-weight: 700; margin-bottom: 0.5rem; color: #0f172a; }
.subtitle { color: #64748b; font-size: 0.95rem; margin-bottom: 1.5rem; }
.metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 1rem; margin-bottom: 2rem; }
.card { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 1rem; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.card .num { font-size: 1.75rem; font-weight: 700; color: #0f172a; }
.card .label { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; margin-top: 0.25rem; }
.card.completed .num { color: #16a34a; }
.card.pending .num { color: #2563eb; }
.card.overdue .num { color: #dc2626; }
h2 { font-size: 1.25rem; font-weight: 600; margin-top: 2rem; margin-bottom: 1rem; padding-bottom: 0.5rem; border-bottom: 2px solid #e2e8f0; color: #1e293b; }
table { border-collapse: separate; border-spacing: 0; width: 100%; font-size: 0.9rem; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 0.5rem; overflow: hidden; margin-bottom: 2rem; }
th, td { padding: 0.75rem 1rem; text-align: left; vertical-align: middle; border-bottom: 1px solid #e2e8f0; }
th { background: #f1f5f9; font-weight: 600; color: #475569; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }
tr:last-child td { border-bottom: none; }
tr:hover td { background-color: #f8fafc; }
.badge { display: inline-block; padding: 0.2rem 0.55rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
.badge-completed { background: #dcfce7; color: #15803d; }
.badge-pending { background: #dbeafe; color: #1d4ed8; }
.badge-overdue { background: #fee2e2; color: #b91c1c; }
.check { font-size: 1.1rem; text-align: center; width: 2.5rem; }
.check-done { color: #16a34a; font-weight: bold; }
.check-todo { color: #cbd5e1; }
.due { white-space: nowrap; font-size: 0.85rem; color: #64748b; }
.desc { word-break: break-word; font-weight: 500; }
.conv { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 0.75rem; color: #94a3b8; }
@media print {
  body { margin: 0; max-width: none; background: #fff; padding: 0; }
  .card { box-shadow: none; border: 1px solid #ccc; }
  table { border: 1px solid #ccc; }
  th, td { border-bottom: 1px solid #ccc; }
  h2 { page-break-after: avoid; }
  tr { page-break-inside: avoid; }
}
"""


def text(value):
    """Render a loosely typed field as text; anything non-null is coerced."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    clean = " ".join(value.split())
    return clean


def parse_time(value):
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None if unusable."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_offset(value):
    """Turn '+09:00' / '-05:30' into a timezone for localized timestamps."""
    if len(value) != 6 or value[0] not in "+-" or value[3] != ":" or not (value[1:3] + value[4:]).isdigit():
        raise ValueError(f"UTC offset must look like +09:00, got {value!r}")
    delta = timedelta(hours=int(value[1:3]), minutes=int(value[4:]))
    if int(value[4:]) > 59 or delta > timedelta(hours=14):
        raise ValueError(f"UTC offset must be between -14:00 and +14:00, got {value!r}")
    return timezone(-delta if value[0] == "-" else delta)


def to_bool(value):
    """Normalize completed status into a standard boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "completed", "done")
    return False


def load(sources):
    """Load and deduplicate action items across multiple export files."""
    items_by_id = {}
    for source in sources:
        content = Path(source).read_bytes().decode("utf-8-sig")
        data = json.loads(content)
        if isinstance(data, dict):
            raw_items = (
                data.get("action_items")
                or data.get("items")
                or data.get("data")
                or [data]
            )
        else:
            raw_items = data

        if not isinstance(raw_items, list):
            raise ValueError(f"{source}: expected a JSON array or object containing action items")

        for item in raw_items:
            if not isinstance(item, dict):
                raise ValueError(f"{source}: each action item must be an object")
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id.strip():
                raise ValueError(f"{source}: action item missing valid string id")
            items_by_id[item_id.strip()] = item
    return list(items_by_id.values())


def render_html(items, tz):
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(tz)

    total = len(items)
    completed_count = 0
    overdue_count = 0
    pending_count = 0

    processed = []
    for item in items:
        completed = to_bool(item.get("completed"))
        due_dt = parse_time(item.get("due_at"))
        created_dt = parse_time(item.get("created_at"))

        if completed:
            status = "completed"
            completed_count += 1
        elif due_dt and due_dt < now_utc:
            status = "overdue"
            overdue_count += 1
        else:
            status = "pending"
            pending_count += 1

        description = item.get("description") or item.get("title") or item.get("content") or ""
        conversation_id = text(item.get("conversation_id"))

        due_display = due_dt.astimezone(tz).strftime("%Y-%m-%d %H:%M") if due_dt else "—"
        created_display = created_dt.astimezone(tz).strftime("%Y-%m-%d") if created_dt else "—"

        processed.append({
            "id": item.get("id"),
            "description": text(description),
            "completed": completed,
            "status": status,
            "due_dt": due_dt,
            "due_display": due_display,
            "created_display": created_display,
            "conversation_id": conversation_id,
        })

    # Sort: overdue first, then pending (by due date ascending), then completed (by due date)
    status_priority = {"overdue": 0, "pending": 1, "completed": 2}
    processed.sort(key=lambda x: (
        status_priority[x["status"]],
        x["due_dt"] or datetime.max.replace(tzinfo=timezone.utc),
        x["description"]
    ))

    rows_html = []
    for row in processed:
        status_cls = f"badge-{row['status']}"
        check_mark = '<span class="check check-done">&#10003;</span>' if row["completed"] else '<span class="check check-todo">&#9633;</span>'
        conv_html = f'<span class="conv">{escape(row["conversation_id"])}</span>' if row["conversation_id"] else "—"

        rows_html.append(f"""<tr>
  <td class="check">{check_mark}</td>
  <td><span class="badge {status_cls}">{row['status']}</span></td>
  <td class="desc">{escape(row['description'])}</td>
  <td class="due">{escape(row['due_display'])}</td>
  <td class="due">{escape(row['created_display'])}</td>
  <td>{conv_html}</td>
</tr>""")

    rendered_rows = "\n".join(rows_html)
    generated_at_str = now_local.strftime("%Y-%m-%d %H:%M %Z")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Omi Action Items & Tasks Dashboard</title>
  <style>{STYLE}</style>
</head>
<body>
  <h1>Action Items Dashboard</h1>
  <div class="subtitle">Generated on {escape(generated_at_str)} &bull; {total} total tasks recorded</div>

  <div class="metrics">
    <div class="card">
      <div class="num">{total}</div>
      <div class="label">Total Tasks</div>
    </div>
    <div class="card pending">
      <div class="num">{pending_count}</div>
      <div class="label">Pending</div>
    </div>
    <div class="card overdue">
      <div class="num">{overdue_count}</div>
      <div class="label">Overdue</div>
    </div>
    <div class="card completed">
      <div class="num">{completed_count}</div>
      <div class="label">Completed</div>
    </div>
  </div>

  <h2>All Tasks</h2>
  <table>
    <thead>
      <tr>
        <th style="width: 3rem;">Done</th>
        <th style="width: 7rem;">Status</th>
        <th>Description</th>
        <th style="width: 10rem;">Due Date</th>
        <th style="width: 8rem;">Created</th>
        <th style="width: 8rem;">Conversation</th>
      </tr>
    </thead>
    <tbody>
{rendered_rows}
    </tbody>
  </table>
</body>
</html>"""


def convert(sources, destination, tz):
    items = load(sources)
    html_content = render_html(items, tz)
    payload = html_content.encode("utf-8")
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
    tz = timezone.utc
    if len(args) >= 2 and args[0] == "--utc-offset":
        try:
            tz = parse_offset(args[1])
        except ValueError as exc:
            sys.exit(f"HTML report failed: {exc}")
        args = args[2:]
    if len(args) < 2:
        sys.exit("Usage: python action_items_html.py [--utc-offset +09:00] OUTPUT.html INPUT.json [INPUT.json ...]")
    try:
        convert(args[1:], args[0], tz)
    except (OSError, ValueError) as exc:
        sys.exit(f"HTML report failed: {exc}")
    print(f"Action items HTML report written to {args[0]}")
```

Run the converter (the output file comes first, then one or more export files):

```sh
python action_items_html.py tasks.html page1.json page2.json
```

Or generate with local time zone offsets for calendar and deadline analysis:

```sh
python action_items_html.py --utc-offset -05:00 tasks.html tasks.json
```

## Report Features

- **Summary Cards**: Quick count of Total Tasks, Pending, Overdue, and Completed.
- **Visual Status Badges**: Clean color-coded badges (green for completed, blue for pending, red for overdue).
- **Printable**: Formatted with `@media print` rules for clean paper or PDF printing without headers breaking across pages.
- **Safe Output**: Uses exclusive file creation (`xb`) to prevent accidental overwrites of existing reports.
