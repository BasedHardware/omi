# Recipe: Action Items → HTML Dashboard Report

Export your Omi action items to a self-contained, printable HTML dashboard —
zero third-party dependencies, pure Python standard library.

## What you get

- Summary cards: **Total / Pending / Overdue / Completed**
- Color-coded status badges per task row
- Due-date normalization with optional UTC offset
- Multi-page deduplication (same task ID across paginated exports counted once)
- `@media print` rules so the page prints cleanly or saves to PDF
- No external scripts, fonts, or tracking — safe for offline and air-gapped use

## Prerequisites

```bash
pipx install omi-cli          # or: pip install omi-cli
export OMI_API_KEY="<your key>"
```

Python ≥ 3.8. No `pip install` needed beyond the CLI itself.

## Step 1 — Export action items to JSON

Fetch all pages and write each to its own file:

```bash
# Page 1 (default limit is 100)
omi --json action-item list > action_items_p1.json

# If you have more than 100 items, fetch additional pages:
omi --json action-item list --skip 100 > action_items_p2.json
omi --json action-item list --skip 200 > action_items_p3.json
```

Or fetch only open items:

```bash
omi --json action-item list --open > action_items_open.json
```

## Step 2 — The conversion script

Save this as `action_items_html.py` and run it against any number of JSON files.

```python
#!/usr/bin/env python3
"""action_items_html.py — Render Omi action-item JSON exports to a
self-contained HTML dashboard.

Usage:
    python action_items_html.py action_items_p1.json [action_items_p2.json ...]
                                --output report.html
                                [--utc-offset +09:00]
                                [--title "My Task Board"]

Requires: Python >= 3.8, stdlib only.
"""
import argparse
import html
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_utc_offset(offset_str):  # type: (str) -> timezone
    """Parse '+HH:MM' or '-HH:MM' into a timezone object."""
    sign = 1 if offset_str[0] != "-" else -1
    parts = offset_str.lstrip("+-").split(":")
    hours = int(parts[0])
    minutes = int(parts[1]) if len(parts) > 1 else 0
    return timezone(timedelta(hours=sign * hours, minutes=sign * minutes))


def parse_due(raw, tz):  # type: (Optional[str], timezone) -> Optional[datetime]
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw[:19], fmt[:len(fmt)])
            return dt.replace(tzinfo=timezone.utc).astimezone(tz)
        except ValueError:
            continue
    return None


def status_badge(completed, due, now):  # type: (bool, Optional[datetime], datetime) -> Tuple[str, str]
    """Return (css_class, label) for a task."""
    if completed:
        return "done", "Completed"
    if due and due < now:
        return "overdue", "Overdue"
    return "pending", "Pending"


def load_items(paths):  # type: (List[Path]) -> List[Dict]
    """Load and deduplicate tasks from one or more JSON export files."""
    seen = {}  # type: Dict[str, Dict]
    for p in paths:
        raw = json.loads(p.read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else raw.get("items", [])
        for item in items:
            item_id = item.get("id") or item.get("action_item_id")
            if item_id and item_id not in seen:
                seen[item_id] = item
    return list(seen.values())


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, sans-serif; background: #f5f6fa; color: #222; }
header { background: #1a1a2e; color: #fff; padding: 1.5rem 2rem; }
header h1 { font-size: 1.4rem; font-weight: 600; }
header p  { font-size: .85rem; opacity: .7; margin-top: .25rem; }
.metrics { display: flex; gap: 1rem; padding: 1.5rem 2rem; flex-wrap: wrap; }
.card { background: #fff; border-radius: 8px; padding: 1rem 1.5rem;
        box-shadow: 0 1px 4px rgba(0,0,0,.08); min-width: 120px; }
.card .num { font-size: 2rem; font-weight: 700; }
.card .lbl { font-size: .8rem; color: #666; margin-top: .2rem; }
.card.total   .num { color: #3b82f6; }
.card.pending .num { color: #f59e0b; }
.card.overdue .num { color: #ef4444; }
.card.done    .num { color: #22c55e; }
table { width: calc(100% - 4rem); margin: 0 2rem 2rem;
        border-collapse: collapse; background: #fff;
        border-radius: 8px; overflow: hidden;
        box-shadow: 0 1px 4px rgba(0,0,0,.08); }
th { background: #1a1a2e; color: #fff; text-align: left;
     padding: .65rem 1rem; font-size: .8rem; font-weight: 600;
     letter-spacing: .04em; text-transform: uppercase; }
td { padding: .6rem 1rem; font-size: .88rem;
     border-bottom: 1px solid #eee; vertical-align: top; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: #f9fafb; }
.badge { display: inline-block; padding: .15rem .55rem;
         border-radius: 999px; font-size: .75rem; font-weight: 600; }
.badge.pending { background: #fef3c7; color: #92400e; }
.badge.overdue { background: #fee2e2; color: #991b1b; }
.badge.done    { background: #dcfce7; color: #166534; }
.check { font-size: 1.1rem; }
.conv-id { font-size: .75rem; color: #888; font-family: monospace; }
@media print {
  body { background: #fff; }
  .metrics { padding: .5rem 0; }
  table { width: 100%; margin: 0; box-shadow: none; }
  header { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .badge { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
}
"""


def render_html(items, title, tz, now):  # type: (List[Dict], str, timezone, datetime) -> str
    rows_html = []
    total = pending = overdue = done = 0

    for item in items:
        total += 1
        completed = bool(item.get("completed") or item.get("done"))
        due_raw = item.get("due_date") or item.get("due")
        due = parse_due(due_raw, tz)
        css, label = status_badge(completed, due, now)

        if css == "done":      done += 1
        elif css == "overdue": overdue += 1
        else:                  pending += 1

        check = "\u2705" if completed else "\u2b1c"
        due_str = due.strftime("%Y-%m-%d %H:%M") if due else "\u2014"
        content = html.escape(item.get("content") or item.get("text") or "(no content)")
        conv_id = html.escape(str(item.get("memory_id") or item.get("conversation_id") or ""))
        conv_cell = '<span class="conv-id">{}</span>'.format(conv_id) if conv_id else "\u2014"

        rows_html.append(
            "<tr>"
            "<td><span class='check'>{}</span></td>".format(check) +
            "<td>{}</td>".format(content) +
            "<td><span class='badge {}'>{}</span></td>".format(css, label) +
            "<td>{}</td>".format(due_str) +
            "<td>{}</td>".format(conv_cell) +
            "</tr>"
        )

    generated = now.strftime("%Y-%m-%d %H:%M %Z")
    escaped_title = html.escape(title)
    tbody = "".join(rows_html) if rows_html else (
        '<tr><td colspan="5" style="text-align:center;color:#aaa">No tasks found.</td></tr>'
    )

    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<header>
  <h1>{title}</h1>
  <p>Generated {generated} &mdash; {total} task(s) from Omi export</p>
</header>
<div class="metrics">
  <div class="card total"><div class="num">{total}</div><div class="lbl">Total</div></div>
  <div class="card pending"><div class="num">{pending}</div><div class="lbl">Pending</div></div>
  <div class="card overdue"><div class="num">{overdue}</div><div class="lbl">Overdue</div></div>
  <div class="card done"><div class="num">{done}</div><div class="lbl">Completed</div></div>
</div>
<table>
  <thead>
    <tr>
      <th></th>
      <th>Task</th>
      <th>Status</th>
      <th>Due</th>
      <th>Conversation</th>
    </tr>
  </thead>
  <tbody>
    {tbody}
  </tbody>
</table>
</body>
</html>
""".format(
        title=escaped_title,
        css=CSS,
        generated=generated,
        total=total,
        pending=pending,
        overdue=overdue,
        done=done,
        tbody=tbody,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():  # type: () -> None
    ap = argparse.ArgumentParser(
        description="Convert Omi action-item JSON exports to an HTML dashboard."
    )
    ap.add_argument("inputs", nargs="+", type=Path,
                    help="One or more JSON files from `omi --json action-item list`")
    ap.add_argument("--output", "-o", type=Path, default=Path("action_items_report.html"),
                    help="Output HTML file (default: action_items_report.html)")
    ap.add_argument("--utc-offset", default="+00:00",
                    help="Local UTC offset, e.g. +09:00 or -05:00 (default: +00:00)")
    ap.add_argument("--title", default="Omi Action Items Dashboard",
                    help="Dashboard heading")
    args = ap.parse_args()

    tz = parse_utc_offset(args.utc_offset)
    now = datetime.now(tz=timezone.utc).astimezone(tz)

    missing = [p for p in args.inputs if not p.exists()]
    if missing:
        for p in missing:
            print("error: file not found: {}".format(p), file=sys.stderr)
        sys.exit(1)

    items = load_items(args.inputs)
    html_out = render_html(items, args.title, tz, now)

    try:
        with args.output.open("xb") as fh:
            fh.write(html_out.encode("utf-8"))
    except FileExistsError:
        print(
            "error: '{}' already exists. Remove it or choose a different --output.".format(args.output),
            file=sys.stderr,
        )
        sys.exit(1)

    print("\u2713 Wrote {} task(s) \u2192 {}".format(len(items), args.output))


if __name__ == "__main__":
    main()
```

## Step 3 — Run it

```bash
# Single export file, default UTC offset:
python action_items_html.py action_items_p1.json --output report.html

# Multiple pages merged + Tokyo timezone:
python action_items_html.py action_items_p1.json action_items_p2.json \
    --utc-offset +09:00 --output report.html

# Custom heading:
python action_items_html.py action_items_open.json \
    --title "Sprint 24 Board" --output sprint24.html
```

Open `report.html` in any browser. Use **File → Print → Save as PDF** for a
printable copy — `@media print` styles keep it clean.

## Output columns

| Column | Source field |
|---|---|
| ✅ / ⬜ | `completed` / `done` |
| Task | `content` or `text` |
| Status | derived: Completed / Pending / Overdue |
| Due | `due_date` or `due`, normalized to your `--utc-offset` |
| Conversation | `memory_id` or `conversation_id` |

## Deduplication

When you pass multiple page files the script deduplicates by `id` /
`action_item_id`. Running the same page twice is safe.

## Overwrite safety

The script opens the output file with `xb` mode (exclusive create). If the
file already exists it exits with an error instead of silently clobbering it.

## Related recipes

- [Agent Quickstart](agent_quickstart.md)
