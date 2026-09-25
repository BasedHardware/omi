#!/usr/bin/env python3
"""action_items_html.py — Render Omi action-item JSON exports to a
self-contained HTML dashboard.

Usage:
    python action_items_html.py [--utc-offset +09:00] \\
        action_items_page1.json [action_items_page2.json ...] \\
        --output dashboard.html

Options:
    --output FILE       Destination HTML file (must not already exist).
    --utc-offset STR    UTC offset for due-date display, e.g. +09:00 or -05:00.
                        Defaults to UTC (+00:00).

Requires Python 3.9+. Zero third-party dependencies.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OFFSET_RE = re.compile(r'^([+-])(\d{2}):(\d{2})$')


def parse_utc_offset(raw: str) -> timezone:
    """Parse a UTC offset string like +09:00 or -05:30 into a timezone."""
    m = _OFFSET_RE.match(raw)
    if not m:
        raise ValueError(
            f"Invalid UTC offset {raw!r}. Expected format: +HH:MM or -HH:MM"
        )
    sign = 1 if m.group(1) == '+' else -1
    delta = timedelta(hours=int(m.group(2)), minutes=int(m.group(3)))
    return timezone(sign * delta)


def load_items(paths: list[Path]) -> list[dict]:
    """Load and deduplicate action items from one or more JSON files."""
    seen: dict[str, dict] = {}
    for p in paths:
        raw = json.loads(p.read_text(encoding='utf-8'))
        items: list[dict] = raw if isinstance(raw, list) else raw.get('items', [])
        for item in items:
            key = item.get('id') or item.get('conversation_id', '') + item.get('text', '')
            seen.setdefault(key, item)
    return list(seen.values())


def classify(item: dict, now: datetime) -> str:
    """Return 'completed', 'overdue', or 'pending'."""
    if item.get('completed'):
        return 'completed'
    due_raw = item.get('due_date') or item.get('due_at')
    if due_raw:
        try:
            due = datetime.fromisoformat(due_raw.replace('Z', '+00:00'))
            if due < now:
                return 'overdue'
        except ValueError:
            pass
    return 'pending'


def fmt_date(raw: str | None, tz: timezone) -> str:
    if not raw:
        return '\u2014'
    try:
        dt = datetime.fromisoformat(raw.replace('Z', '+00:00')).astimezone(tz)
        return dt.strftime('%Y-%m-%d %H:%M')
    except ValueError:
        return html.escape(raw)


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

_CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
  background: #f5f7fa;
  color: #1a1a2e;
  padding: 2rem;
}
h1 { font-size: 1.6rem; margin-bottom: 0.25rem; }
.meta { color: #555; font-size: 0.85rem; margin-bottom: 2rem; }

.cards { display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 2.5rem; }
.card {
  flex: 1 1 140px;
  background: #fff;
  border-radius: 10px;
  padding: 1.2rem 1.4rem;
  box-shadow: 0 1px 4px rgba(0,0,0,.08);
  text-align: center;
}
.card .num { font-size: 2rem; font-weight: 700; line-height: 1.1; }
.card .label { font-size: 0.78rem; color: #666; margin-top: 0.3rem; text-transform: uppercase; letter-spacing: .04em; }
.card.total .num  { color: #3a3af4; }
.card.pending .num { color: #e67e22; }
.card.overdue .num { color: #e74c3c; }
.card.done .num   { color: #27ae60; }

table {
  width: 100%;
  border-collapse: collapse;
  background: #fff;
  border-radius: 10px;
  overflow: hidden;
  box-shadow: 0 1px 4px rgba(0,0,0,.08);
  font-size: 0.88rem;
}
thead th {
  background: #3a3af4;
  color: #fff;
  padding: .65rem 1rem;
  text-align: left;
  font-weight: 600;
  letter-spacing: .03em;
}
tbody tr:nth-child(even) { background: #f9f9ff; }
tbody td { padding: .6rem 1rem; border-bottom: 1px solid #eee; vertical-align: top; }
tbody tr:last-child td { border-bottom: none; }

.badge {
  display: inline-block;
  padding: .18em .6em;
  border-radius: 99px;
  font-size: .75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .04em;
}
.badge-pending  { background: #fef3e2; color: #b7590a; }
.badge-overdue  { background: #fdecea; color: #c0392b; }
.badge-completed { background: #eafaf1; color: #1e8449; }

.check { color: #27ae60; font-size: 1.1rem; }
.cross { color: #bbb; font-size: 1.1rem; }
.conv-id { font-family: monospace; font-size: .78rem; color: #888; }

@media print {
  body { background: #fff; padding: .5rem; }
  .card { box-shadow: none; border: 1px solid #ddd; }
  table { box-shadow: none; font-size: .8rem; }
  thead th { background: #3a3af4 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .badge { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
}
"""


def build_html(items: list[dict], tz: timezone, generated_at: datetime) -> str:
    now = generated_at
    statuses = [classify(it, now) for it in items]

    total      = len(items)
    n_pending  = statuses.count('pending')
    n_overdue  = statuses.count('overdue')
    n_completed = statuses.count('completed')

    tz_label = str(tz)

    rows_html = []
    for item, status in zip(items, statuses):
        text    = html.escape(item.get('text') or item.get('content') or '')
        conv_id = html.escape(item.get('conversation_id') or '')
        due     = fmt_date(item.get('due_date') or item.get('due_at'), tz)
        created = fmt_date(item.get('created_at'), tz)
        done_mark = '<span class="check">&#10003;</span>' if status == 'completed' else '<span class="cross">&#9675;</span>'
        badge_cls   = f'badge-{status}'
        badge_label = status.upper()
        rows_html.append(
            f'<tr>'
            f'<td>{done_mark}</td>'
            f'<td>{text}</td>'
            f'<td><span class="badge {badge_cls}">{badge_label}</span></td>'
            f'<td>{due}</td>'
            f'<td>{created}</td>'
            f'<td><span class="conv-id">{conv_id}</span></td>'
            f'</tr>'
        )

    rows    = '\n'.join(rows_html)
    gen_str = html.escape(now.astimezone(tz).strftime('%Y-%m-%d %H:%M') + f' ({tz_label})')

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Omi Action Items Dashboard</title>
<style>{_CSS}</style>
</head>
<body>
<h1>&#9989; Omi Action Items Dashboard</h1>
<p class="meta">Generated: {gen_str} &mdash; {total} task(s) across all sources</p>

<div class="cards">
  <div class="card total"><div class="num">{total}</div><div class="label">Total</div></div>
  <div class="card pending"><div class="num">{n_pending}</div><div class="label">Pending</div></div>
  <div class="card overdue"><div class="num">{n_overdue}</div><div class="label">Overdue</div></div>
  <div class="card done"><div class="num">{n_completed}</div><div class="label">Completed</div></div>
</div>

<table>
  <thead>
    <tr>
      <th>Done</th>
      <th>Task</th>
      <th>Status</th>
      <th>Due</th>
      <th>Created</th>
      <th>Conversation ID</th>
    </tr>
  </thead>
  <tbody>
{rows}
  </tbody>
</table>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Render Omi action-item JSON exports to a self-contained HTML dashboard.',
    )
    parser.add_argument(
        'inputs',
        metavar='FILE',
        nargs='+',
        type=Path,
        help='One or more JSON files produced by `omi --json action-item list`.',
    )
    parser.add_argument(
        '--output',
        metavar='FILE',
        type=Path,
        default=Path('action_items_dashboard.html'),
        help='Destination HTML file (default: action_items_dashboard.html). Must not already exist.',
    )
    parser.add_argument(
        '--utc-offset',
        metavar='OFFSET',
        default='+00:00',
        help='UTC offset for date display, e.g. +09:00 or -05:00 (default: +00:00).',
    )
    args = parser.parse_args()

    try:
        tz = parse_utc_offset(args.utc_offset)
    except ValueError as exc:
        parser.error(str(exc))

    for p in args.inputs:
        if not p.exists():
            parser.error(f'Input file not found: {p}')

    items = load_items(args.inputs)
    if not items:
        print('No action items found in the provided files.', file=sys.stderr)
        sys.exit(1)

    now  = datetime.now(tz=timezone.utc)
    page = build_html(items, tz, now)

    try:
        with args.output.open('xb') as fh:
            fh.write(page.encode('utf-8'))
    except FileExistsError:
        print(
            f'Error: {args.output} already exists. '
            'Delete it or choose a different --output path.',
            file=sys.stderr,
        )
        sys.exit(1)

    n_overdue = sum(1 for it in items if classify(it, now) == 'overdue')
    print(f'Wrote {args.output}  ({len(items)} tasks, {n_overdue} overdue)')


if __name__ == '__main__':
    main()
