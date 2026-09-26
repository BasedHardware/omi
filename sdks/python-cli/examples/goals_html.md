# Build a self-contained HTML dashboard report of your goals

Use this recipe to browse, review, or print your Omi tracked goals, milestones,
and progress metrics without relying on third-party tools or external websites.
It turns one or more `goal list` JSON exports into a clean, responsive HTML
dashboard featuring metric progress bars, status badges (active vs inactive),
type categorization, and completion percentages. It makes no network requests,
includes no external scripts or remote fonts, and writes safely using
exclusive creation. You need Python 3.10+ and an authenticated `omi-cli` for
the initial export.

Export goals (up to 100 per page, including inactive/completed milestones):

```sh
omi --json goal list --limit 100 --include-inactive > goals_0.json
```

Check that the command succeeded before building the report. To retrieve
subsequent pages, increase `--offset` by 100 into a separate file. The converter
accepts multiple files and merges duplicate IDs seamlessly.

Save the following as `goals_to_html.py`:

```python
#!/usr/bin/env python3
"""Build a self-contained HTML dashboard report of Omi goals."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import sys
from typing import Any, Iterable

STYLE = """
body { font-family: system-ui, -apple-system, sans-serif; margin: 2rem auto; max-width: 70rem; padding: 0 1rem; color: #1a1a1a; background: #fafafa; }
h1 { font-size: 1.6rem; color: #111; margin-bottom: 0.5rem; }
p.summary { color: #555; margin-bottom: 1.5rem; font-size: 0.95rem; }
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr)); gap: 1rem; margin-bottom: 2rem; }
.stat-card { background: #fff; padding: 1rem; border-radius: 6px; border: 1px solid #e0e0e0; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.stat-card .val { font-size: 1.5rem; font-weight: bold; color: #222; }
.stat-card .lbl { font-size: 0.8rem; color: #666; text-transform: uppercase; }
table { border-collapse: collapse; width: 100%; font-size: 0.9rem; background: #fff; border-radius: 6px; overflow: hidden; border: 1px solid #e0e0e0; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
th, td { border: 1px solid #eee; padding: 0.6rem 0.8rem; text-align: left; vertical-align: middle; }
th { background: #f7f7f7; font-weight: 600; color: #333; }
.badge { display: inline-block; padding: 0.2rem 0.5rem; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
.badge-active { background: #e6f4ea; color: #137333; }
.badge-inactive { background: #f1f3f4; color: #5f6368; }
.badge-type { background: #e8f0fe; color: #1a73e8; }
.progress-bar-bg { background: #eee; border-radius: 4px; height: 8px; width: 100%; overflow: hidden; margin-top: 4px; }
.progress-bar-fill { background: #1a73e8; height: 100%; border-radius: 4px; }
.progress-bar-complete { background: #137333; }
td.id { font-family: monospace; font-size: 0.8rem; color: #777; }
@media print { body { margin: 0; max-width: none; background: #fff; } table { box-shadow: none; } tr { page-break-inside: avoid; } }
"""


def parse_time(value: Any) -> datetime | None:
    """Parse ISO-8601 timestamp string into UTC datetime."""
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_offset(value: str) -> timezone:
    """Parse '+09:00' or '-05:00' into a valid timezone."""
    if len(value) != 6 or value[0] not in "+-" or value[3] != ":" or not (value[1:3] + value[4:]).isdigit():
        raise ValueError(f"UTC offset must look like +09:00, got {value!r}")
    from datetime import timedelta
    delta = timedelta(hours=int(value[1:3]), minutes=int(value[4:]))
    if int(value[4:]) > 59 or delta > timedelta(hours=14):
        raise ValueError(f"UTC offset must be between -14:00 and +14:00, got {value!r}")
    return timezone(-delta if value[0] == "-" else delta)


def to_bool(value: Any) -> bool:
    """Normalize boolean or string flag."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "active")
    return False


def load(sources: Iterable[str | Path]) -> list[dict[str, Any]]:
    """Load and deduplicate goals across multiple export files."""
    items_by_id: dict[str, dict[str, Any]] = {}
    for source in sources:
        path = Path(source)
        content = path.read_bytes().decode("utf-8-sig")
        data = json.loads(content)
        raw_items = data.get("goals") or data.get("items") or data.get("data") or [data] if isinstance(data, dict) else data
        if not isinstance(raw_items, list):
            raise ValueError(f"{source}: expected JSON array or wrapped object containing goals")
        for item in raw_items:
            if not isinstance(item, dict):
                raise ValueError(f"{source}: each goal must be a JSON object")
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id.strip():
                raise ValueError(f"{source}: goal missing valid string id")
            clean_id = item_id.strip()
            existing = items_by_id.get(clean_id)
            if existing is not None:
                new_dt = parse_time(item.get("updated_at") or item.get("created_at"))
                old_dt = parse_time(existing.get("updated_at") or existing.get("created_at"))
                if new_dt and old_dt:
                    if new_dt > old_dt:
                        items_by_id[clean_id] = item
                elif new_dt and not old_dt:
                    items_by_id[clean_id] = item
            else:
                items_by_id[clean_id] = item
    return list(items_by_id.values())


def generate_html(goals: list[dict[str, Any]], tz: timezone) -> str:
    """Generate self-contained HTML report from goals list."""
    total = len(goals)
    active = sum(1 for g in goals if to_bool(g.get("is_active", True)))
    inactive = total - active

    # Sort: active first, then newest updated
    def sort_key(g: dict[str, Any]) -> tuple[int, str]:
        is_act = 0 if to_bool(g.get("is_active", True)) else 1
        dt = parse_time(g.get("updated_at") or g.get("created_at"))
        dt_str = dt.isoformat() if dt else ""
        return (is_act, dt_str)

    sorted_goals = sorted(goals, key=sort_key)

    rows_html = []
    for g in sorted_goals:
        gid = escape(str(g.get("id") or ""))
        title = escape(str(g.get("title") or "(untitled)"))
        gtype = escape(str(g.get("goal_type") or "qualitative"))
        unit = escape(str(g.get("unit") or ""))
        is_act = to_bool(g.get("is_active", True))

        cur = g.get("current_value")
        tgt = g.get("target_value")

        progress_display = ""
        if tgt is not None and isinstance(tgt, (int, float)) and tgt > 0 and cur is not None and isinstance(cur, (int, float)):
            pct = min(100.0, max(0.0, (cur / tgt) * 100.0))
            is_done = pct >= 100.0
            fill_class = "progress-bar-fill progress-bar-complete" if is_done else "progress-bar-fill"
            progress_display = f"""
            <div>{cur:g} / {tgt:g} {unit} ({pct:.1f}%)</div>
            <div class="progress-bar-bg"><div class="{fill_class}" style="width: {pct:.1f}%"></div></div>
            """
        elif cur is not None and isinstance(cur, (int, float)):
            progress_display = f"{cur:g} {unit}"
        else:
            progress_display = f"— {unit}".strip()

        status_badge = f'<span class="badge badge-active">Active</span>' if is_act else f'<span class="badge badge-inactive">Inactive</span>'
        type_badge = f'<span class="badge badge-type">{gtype}</span>'

        upd_dt = parse_time(g.get("updated_at") or g.get("created_at"))
        upd_str = upd_dt.astimezone(tz).strftime("%Y-%m-%d %H:%M") if upd_dt else "—"

        rows_html.append(f"""<tr>
            <td><strong>{title}</strong></td>
            <td>{type_badge}</td>
            <td>{progress_display}</td>
            <td>{status_badge}</td>
            <td>{upd_str}</td>
            <td class="id">{gid}</td>
        </tr>""")

    content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Omi Goals Progress Report</title>
<style>{STYLE}</style>
</head>
<body>
<h1>Omi Goals Progress Report</h1>
<p class="summary">Generated {datetime.now(tz).strftime('%Y-%m-%d %H:%M %Z')} from Omi goal export</p>
<div class="stats-grid">
  <div class="stat-card"><div class="val">{total}</div><div class="lbl">Total Goals</div></div>
  <div class="stat-card"><div class="val">{active}</div><div class="lbl">Active Goals</div></div>
  <div class="stat-card"><div class="val">{inactive}</div><div class="lbl">Inactive / Achieved</div></div>
</div>
<table>
<thead>
<tr>
  <th>Goal</th>
  <th>Type</th>
  <th style="min-width: 12rem;">Progress</th>
  <th>Status</th>
  <th>Updated</th>
  <th>ID</th>
</tr>
</thead>
<tbody>
{''.join(rows_html)}
</tbody>
</table>
</body>
</html>
"""
    return content


def build_report(sources: list[str], output_path: str | Path, tz: timezone) -> None:
    """Build report and write exclusively to output path."""
    goals = load(sources)
    html_text = generate_html(goals, tz)
    dest = Path(output_path)
    try:
        out = dest.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {dest}") from None
    try:
        with out:
            out.write(html_text.encode("utf-8"))
    except OSError:
        dest.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", help="Destination HTML file path")
    parser.add_argument("inputs", nargs="+", help="Input goal JSON export files")
    parser.add_argument("--utc-offset", default="+00:00", help="Timezone offset e.g. +09:00 or -05:00")
    args = parser.parse_args(argv)

    try:
        tz = parse_offset(args.utc_offset)
        build_report(args.inputs, args.output, tz)
        print(f"Goals HTML report written to {args.output}")
        return 0
    except Exception as exc:
        sys.exit(f"Failed to generate report: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
```

Run the converter (repeat with new exports at any time):

```sh
python goals_to_html.py goals_report.html goals_0.json
```

To display dates in your local timezone, pass `--utc-offset`:

```sh
python goals_to_html.py goals_report.html goals_0.json --utc-offset -05:00
```

Open `goals_report.html` in any browser or print it (`Ctrl+P` / `Cmd+P`). The
report uses pure CSS with `@media print` rules for clean hard-copy printing,
HTML-escapes all user-provided strings against injection, and refuses to
clobber an existing destination file.
