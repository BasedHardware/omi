#!/usr/bin/env python3
"""Convert Omi goals JSON exports to a self-contained, responsive HTML dashboard.

Usage:
    python goals_to_html.py goals.json -o goals.html
    omi --json goal list | python goals_to_html.py - -o goals.html
    python goals_to_html.py page1.json page2.json -o all_goals.html

Outputs a single HTML document with visual CSS progress bars, metric summary cards,
active and completed goal sections, and print-ready CSS with no external dependencies.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

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
th, td { border: 1px solid #e0e0e0; padding: 0.5rem 0.6rem; text-align: left; vertical-align: middle; }
th { background: #f5f5f5; font-weight: 600; }
td.mono { font-family: ui-monospace, SFMono-Regular, monospace; font-size: 0.8rem; color: #555; }
td.nowrap { white-space: nowrap; }
.badge { display: inline-block; padding: 0.15rem 0.45rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }
.badge-active { background: #e8f5e9; color: #1b5e20; }
.badge-done { background: #e3f2fd; color: #0d47a1; }
.badge-inactive { background: #f5f5f5; color: #616161; }
.progress-container { display: flex; align-items: center; gap: 0.5rem; min-width: 12rem; }
.progress-bar-bg { flex-grow: 1; height: 10px; background: #eee; border-radius: 5px; overflow: hidden; }
.progress-bar-fill { height: 100%; background: #4caf50; border-radius: 5px; }
.progress-text { font-size: 0.8rem; font-weight: 600; color: #444; width: 3.2rem; text-align: right; }
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


def calculate_progress_pct(current: Any, target: Any) -> float:
    """Calculate progress percentage as a bounded float [0.0, 100.0]."""
    if current is None or target is None:
        return 0.0
    try:
        c = float(current)
        t = float(target)
        if t <= 0:
            return 0.0
        return round((c / t) * 100.0, 1)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0.0


def extract_goals(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON content and extract a list of goal dictionaries."""
    raw = content.lstrip("\ufeff")
    items = json.loads(raw)

    if isinstance(items, dict):
        for key in ("goals", "items", "data"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError(f"{source_label}: expected a JSON array or wrapped goals object")

    results: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source_label}: each goal must be a JSON object")
        if not item.get("id") or str(item.get("id")).strip() == "":
            raise ValueError(f"{source_label}: goal missing required 'id' field")
        results.append(item)

    return results


def render_goals_table(items: Sequence[Dict[str, Any]]) -> str:
    """Render a sequence of goal items into an HTML table with CSS progress bars."""
    if not items:
        return "<p><em>No goals in this section.</em></p>"

    rows_html = []
    for g in items:
        title = escape(str(g.get("title") or g.get("name") or g.get("description") or "Untitled Goal"))
        goal_type = escape(str(g.get("goal_type") or "general"))
        unit = escape(str(g.get("unit") or ""))
        curr = g.get("current_value")
        target = g.get("target_value")
        pct = calculate_progress_pct(curr, target)
        bounded_fill = min(max(pct, 0.0), 100.0)

        # Status determination
        is_active = g.get("is_active") in (True, 1, "true", "1", "yes", "active")
        is_completed = False
        try:
            if curr is not None and target is not None and float(target) > 0 and float(curr) >= float(target):
                is_completed = True
        except (ValueError, TypeError):
            pass

        if is_completed:
            badge_cls = "badge-done"
            badge_txt = "Completed"
        elif is_active:
            badge_cls = "badge-active"
            badge_txt = "Active"
        else:
            badge_cls = "badge-inactive"
            badge_txt = "Inactive"

        # Metric string
        if curr is not None or target is not None:
            c_disp = escape(str(curr)) if curr is not None else "0"
            t_disp = escape(str(target)) if target is not None else "N/A"
            u_disp = f" {unit}" if unit else ""
            metric_str = f"{c_disp} / {t_disp}{u_disp}"
        else:
            metric_str = "&mdash;"

        goal_id = escape(str(g.get("id") or ""))
        created = escape(utc_stamp(g.get("created_at"))) or "&mdash;"

        rows_html.append(
            f"<tr>"
            f"<td class='nowrap'><span class='badge {badge_cls}'>{badge_txt}</span></td>"
            f"<td><strong>{title}</strong></td>"
            f"<td class='nowrap'><code>{goal_type}</code></td>"
            f"<td class='nowrap'>"
            f"  <div class='progress-container'>"
            f"    <div class='progress-bar-bg'><div class='progress-bar-fill' style='width: {bounded_fill}%;'></div></div>"
            f"    <span class='progress-text'>{pct}%</span>"
            f"  </div>"
            f"</td>"
            f"<td class='nowrap'>{metric_str}</td>"
            f"<td class='nowrap'>{created}</td>"
            f"<td class='mono nowrap'>{goal_id}</td>"
            f"</tr>"
        )

    headers_html = "<th>Status</th><th>Goal Title</th><th>Type</th><th>Progress</th><th>Target Metric</th><th>Created</th><th>ID</th>"
    return f"<table><thead><tr>{headers_html}</tr></thead><tbody>{''.join(rows_html)}</tbody></table>"


def generate_html_dashboard(items: Sequence[Dict[str, Any]], title: str = "Omi Goals Dashboard") -> str:
    """Generate a full standalone HTML dashboard document."""
    seen_ids = set()
    deduped: List[Dict[str, Any]] = []
    for g in items:
        gid = str(g.get("id"))
        if gid not in seen_ids:
            seen_ids.add(gid)
            deduped.append(g)

    active_goals: List[Dict[str, Any]] = []
    completed_goals: List[Dict[str, Any]] = []
    inactive_goals: List[Dict[str, Any]] = []

    for g in deduped:
        curr = g.get("current_value")
        target = g.get("target_value")
        is_active = g.get("is_active") in (True, 1, "true", "1", "yes", "active")
        try:
            if curr is not None and target is not None and float(target) > 0 and float(curr) >= float(target):
                completed_goals.append(g)
                continue
        except (ValueError, TypeError):
            pass

        if is_active:
            active_goals.append(g)
        else:
            inactive_goals.append(g)

    total_count = len(deduped)
    active_count = len(active_goals)
    completed_count = len(completed_goals)
    inactive_count = len(inactive_goals)
    completion_pct = round((completed_count / total_count * 100.0), 1) if total_count > 0 else 0.0

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    active_table = render_goals_table(active_goals)
    completed_table = render_goals_table(completed_goals)
    inactive_table = render_goals_table(inactive_goals)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escape(title)}</title>
  <style>{STYLE}</style>
</head>
<body>
  <h1>{escape(title)}</h1>
  <p class="summary">Generated on {now_utc} &bull; {total_count} total objective(s) tracked</p>

  <div class="stats-cards">
    <div class="stat-card">
      <div class="stat-num">{total_count}</div>
      <div class="stat-label">Total Goals</div>
    </div>
    <div class="stat-card">
      <div class="stat-num">{active_count}</div>
      <div class="stat-label">Active Objectives</div>
    </div>
    <div class="stat-card">
      <div class="stat-num">{completed_count}</div>
      <div class="stat-label">Completed</div>
    </div>
    <div class="stat-card">
      <div class="stat-num">{inactive_count}</div>
      <div class="stat-label">Inactive</div>
    </div>
    <div class="stat-card">
      <div class="stat-num">{completion_pct}%</div>
      <div class="stat-label">Completion Rate</div>
    </div>
  </div>

  <h2>🟢 Active Goals ({active_count})</h2>
  {active_table}

  <h2>🏁 Completed Goals ({completed_count})</h2>
  {completed_table}

  <h2>⚪ Inactive / Archived ({inactive_count})</h2>
  {inactive_table}
</body>
</html>
"""


def convert_paths_to_html(sources: Sequence[str | Path], output_dest: Optional[str | Path] = None) -> int:
    """Convert one or more JSON files (or stdin) to an HTML dashboard."""
    all_goals: List[Dict[str, Any]] = []

    for src in sources:
        if str(src) == "-":
            content = sys.stdin.read()
            all_goals.extend(extract_goals(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_goals.extend(extract_goals(content, str(p)))

    html_content = generate_html_dashboard(all_goals)

    if output_dest and str(output_dest) != "-":
        out_path = Path(output_dest)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html_content, encoding="utf-8")
    else:
        sys.stdout.write(html_content)

    return len(all_goals)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi goals JSON exports to a self-contained HTML dashboard."
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
            print(f"Exported {count} goal(s) to {args.output}", file=sys.stderr)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
