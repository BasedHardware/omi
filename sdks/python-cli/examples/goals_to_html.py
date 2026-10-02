#!/usr/bin/env python3
"""Convert Omi goal JSON exports into a self-contained responsive HTML dashboard."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple
import uuid

PRODID = "-//omi-cli examples//goals_to_html//EN"
DEFAULT_TITLE = "Omi Goals & Progress Dashboard"

CSS_STYLES = """
:root {
  --bg: #f8fafc;
  --card-bg: #ffffff;
  --text: #0f172a;
  --muted: #64748b;
  --border: #e2e8f0;
  --bar-bg: #e2e8f0;
  --bar-fill: #2563eb;
  --bar-fill-done: #16a34a;
  --tag-bg: #f1f5f9;
  --tag-text: #475569;
  --badge-active-bg: #eff6ff;
  --badge-active-text: #1d4ed8;
  --badge-done-bg: #f0fdf4;
  --badge-done-text: #15803d;
  --badge-inactive-bg: #f8fafc;
  --badge-inactive-text: #64748b;
  --table-header: #f1f5f9;
  --row-hover: #f8fafc;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0b0f19;
    --card-bg: #111827;
    --text: #f8fafc;
    --muted: #94a3b8;
    --border: #1f2937;
    --bar-bg: #1f2937;
    --bar-fill: #3b82f6;
    --bar-fill-done: #22c55e;
    --tag-bg: #1f2937;
    --tag-text: #cbd5e1;
    --badge-active-bg: #1e3a8a;
    --badge-active-text: #93c5fd;
    --badge-done-bg: #14532d;
    --badge-done-text: #86efac;
    --badge-inactive-bg: #1f2937;
    --badge-inactive-text: #94a3b8;
    --table-header: #1f2937;
    --row-hover: #161f30;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0 auto;
  max-width: 1040px;
  padding: 2rem 1.5rem 4rem;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.5;
}
h1 { font-size: 1.85rem; font-weight: 700; margin: 0 0 0.25rem; }
h2 {
  font-size: 1.25rem;
  font-weight: 600;
  margin: 2.25rem 0 1rem;
  padding-bottom: 0.4rem;
  border-bottom: 1px solid var(--border);
}
p.summary { color: var(--muted); margin: 0 0 1.75rem; font-size: 0.95rem; }
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 1rem;
  margin-bottom: 2.5rem;
}
.stat-card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  padding: 1rem;
  text-align: center;
}
.stat-card .num { font-size: 1.75rem; font-weight: 700; color: var(--text); }
.stat-card .lbl { font-size: 0.75rem; text-transform: uppercase; color: var(--muted); letter-spacing: 0.05em; }
.goal-card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  padding: 1.25rem;
  margin-bottom: 1rem;
}
.goal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.5rem;
  gap: 0.75rem;
}
.goal-title { font-size: 1.05rem; font-weight: 600; margin: 0; }
.badge {
  display: inline-block;
  padding: 0.15rem 0.55rem;
  border-radius: 0.25rem;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.badge-active { background: var(--badge-active-bg); color: var(--badge-active-text); }
.badge-completed { background: var(--badge-done-bg); color: var(--badge-done-text); }
.badge-inactive { background: var(--badge-inactive-bg); color: var(--badge-inactive-text); }
.type-tag {
  display: inline-block;
  padding: 0.15rem 0.45rem;
  border-radius: 0.25rem;
  font-size: 0.75rem;
  background: var(--tag-bg);
  color: var(--tag-text);
  margin-left: 0.4rem;
}
.progress-container {
  background: var(--bar-bg);
  border-radius: 9999px;
  height: 0.65rem;
  width: 100%;
  overflow: hidden;
  margin: 0.75rem 0;
}
.progress-bar {
  background: var(--bar-fill);
  height: 100%;
  border-radius: 9999px;
  transition: width 0.3s ease;
}
.progress-bar.done { background: var(--bar-fill-done); }
.goal-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 0.85rem;
  color: var(--muted);
}
.goal-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.75rem;
}
@media print {
  body { margin: 0; max-width: none; padding: 0; }
  h2 { page-break-after: avoid; }
  .goal-card { break-inside: avoid; border: 1px solid #ccc; }
  .stats-grid { break-inside: avoid; }
}
"""


def text(value: Any) -> str:
    """Render a field as safe text, dropping C0 controls, surrogates, and noncharacters."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    collapsed = " ".join(value.split())
    return "".join(
        ch for ch in collapsed
        if (ch >= " " or ch in "\n\t") and not ("\ud800" <= ch <= "\udfff") and ch not in ("\ufffe", "\uffff")
    )


def parse_float(value: Any) -> Optional[float]:
    """Parse a float value safely, rejecting non-finite numbers."""
    if value is None:
        return None
    try:
        val = float(value)
        import math
        if not math.isfinite(val):
            return None
        return val
    except (ValueError, TypeError):
        return None


def derive_status(goal: Dict[str, Any]) -> str:
    """Derive status strictly: inactive first, then completed/achieved, then active."""
    is_active = goal.get("is_active")
    if is_active is False or is_active == 0 or str(is_active).strip().lower() in ("false", "0", "no"):
        return "inactive"
    is_achieved = goal.get("is_achieved") or goal.get("is_completed")
    if is_achieved is True or is_achieved == 1 or str(is_achieved).strip().lower() in ("true", "1", "yes"):
        return "completed"
    return "active"


def calc_progress(goal: Dict[str, Any]) -> Tuple[float, str, bool]:
    """Compute (bar_fraction [0.0..1.0], display_percentage_string, is_completed_flag)."""
    status = derive_status(goal)
    is_done = (status == "completed")

    goal_type = str(goal.get("goal_type") or "").strip().lower()
    if goal_type == "boolean":
        if is_done:
            return 1.0, "100.0%", True
        c = parse_float(goal.get("current_value"))
        if c is not None and c >= 1.0:
            return 1.0, "100.0%", True
        return 0.0, "0.0%", False

    curr = parse_float(goal.get("current_value"))
    target = parse_float(goal.get("target_value"))
    min_v = parse_float(goal.get("min_value"))
    max_v = parse_float(goal.get("max_value"))

    if is_done and target is None and max_v is None:
        return 1.0, "100.0%", True

    if curr is None:
        return (1.0 if is_done else 0.0), ("100.0%" if is_done else "—"), is_done

    # Scale or numeric calculation
    base = min_v if min_v is not None else 0.0
    denominator = None
    if target is not None and target != base:
        denominator = target - base
    elif max_v is not None and max_v != base:
        denominator = max_v - base

    if denominator is not None and denominator > 0:
        ratio = (curr - base) / denominator
        clamped = max(0.0, min(1.0, ratio))
        disp = f"{ratio * 100.0:.1f}%"
        completed = is_done or (ratio >= 1.0)
        return clamped, disp, completed

    # Fallback when target == base or target is 0
    if target == 0.0 and curr == 0.0:
        return 1.0, "100.0%", True
    if is_done:
        return 1.0, "100.0%", True
    return 0.0, "—", False


def unwrap_goals(raw: Any, source_label: str) -> List[Dict[str, Any]]:
    """Unwrap goals from standard response envelopes or bare lists."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("goals", "items", "data", "results"):
            candidate = raw.get(key)
            if isinstance(candidate, list):
                return candidate
        # Single goal dictionary
        if "title" in raw or "id" in raw or "goal_type" in raw:
            return [raw]
        return []
    raise ValueError(f"{source_label}: root JSON must be a list or an object with a goals array")


def load(sources: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """Load and deduplicate goals from files or stdin ('-')."""
    goals_by_id: Dict[str, Dict[str, Any]] = {}

    for source in sources:
        source_label = "stdin" if source == "-" else source
        if source == "-":
            content = sys.stdin.buffer.read()
        else:
            path = Path(source)
            if not path.is_file():
                raise FileNotFoundError(f"Input file not found: {source}")
            content = path.read_bytes()

        if not content.strip():
            continue

        raw = json.loads(content.decode("utf-8-sig"))
        items = unwrap_goals(raw, source_label)
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"{source_label} item {idx}: each goal must be an object")
            item_id = item.get("id")
            sanitized_id = text(item_id).strip()
            if sanitized_id:
                clean_id = sanitized_id
            else:
                clean_id = f"auto_{uuid.uuid4().hex}"
                while clean_id in goals_by_id:
                    clean_id = f"auto_{uuid.uuid4().hex}"
            item["id"] = clean_id
            goals_by_id[clean_id] = item
    return goals_by_id


def generate_html_dashboard(
    goals_by_id: Dict[str, Dict[str, Any]],
    report_title: str = DEFAULT_TITLE,
    status_filter: str = "all",
) -> str:
    """Render a self-contained HTML dashboard from loaded goals."""
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    norm_filter = status_filter.strip().lower() if status_filter else "all"

    all_goals = list(goals_by_id.values())
    filtered_goals: List[Dict[str, Any]] = []

    for g in all_goals:
        st = derive_status(g)
        if norm_filter == "all" or st == norm_filter:
            filtered_goals.append(g)

    # Sort goals: active first, then completed, then inactive; then by title
    def sort_key(item: Dict[str, Any]) -> Tuple[int, str]:
        st = derive_status(item)
        order = 0 if st == "active" else (1 if st == "completed" else 2)
        return order, text(item.get("title") or "")

    filtered_goals.sort(key=sort_key)

    total_count = len(all_goals)
    active_count = sum(1 for g in all_goals if derive_status(g) == "active")
    completed_count = sum(1 for g in all_goals if derive_status(g) == "completed")

    progress_vals: List[float] = []
    for g in all_goals:
        ratio, _, _ = calc_progress(g)
        progress_vals.append(ratio)
    avg_progress = (sum(progress_vals) / len(progress_vals) * 100.0) if progress_vals else 0.0

    cards_html: List[str] = []
    for g in filtered_goals:
        st = derive_status(g)
        bar_ratio, disp_pct, is_done = calc_progress(g)
        bar_pct = round(bar_ratio * 100.0, 1)

        goal_id = text(g.get("id"))
        raw_title = text(g.get("title")) or "(untitled goal)"
        g_title = html.escape(raw_title, quote=True)
        g_type = text(g.get("goal_type") or "goal")
        unit = text(g.get("unit") or "")

        curr_v = parse_float(g.get("current_value"))
        target_v = parse_float(g.get("target_value"))

        curr_str = f"{curr_v:g}" if curr_v is not None else "—"
        target_str = f"{target_v:g}" if target_v is not None else "—"
        c_esc = html.escape(curr_str, quote=True)
        t_esc = html.escape(target_str, quote=True)
        u_esc = f" {html.escape(unit, quote=True)}" if unit else ""
        metric_info = f"{c_esc} / {t_esc}{u_esc}"

        badge_class = f"badge-{st}"
        bar_done_class = " done" if is_done else ""

        cards_html.append(f"""    <div class="goal-card">
      <div class="goal-header">
        <div class="goal-title">{g_title}<span class="type-tag">{html.escape(g_type, quote=True)}</span></div>
        <span class="badge {badge_class}">{html.escape(st, quote=True)}</span>
      </div>
      <div class="progress-container">
        <div class="progress-bar{bar_done_class}" style="width: {bar_pct}%"></div>
      </div>
      <div class="goal-meta">
        <span>Progress: <strong>{html.escape(disp_pct, quote=True)}</strong> ({metric_info})</span>
        <span class="goal-id">{html.escape(goal_id, quote=True)}</span>
      </div>
    </div>""")

    body_cards = "\n".join(cards_html) if cards_html else "    <p class=\"summary\">No goals found matching filter.</p>"

    doc_title = html.escape(text(report_title) or DEFAULT_TITLE, quote=True)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{doc_title}</title>
  <style>{CSS_STYLES}</style>
</head>
<body>
  <h1>{doc_title}</h1>
  <p class="summary">Generated on {now_utc}. Tracking {len(filtered_goals)} goals.</p>

  <div class="stats-grid">
    <div class="stat-card">
      <div class="num">{total_count}</div>
      <div class="lbl">Total Goals</div>
    </div>
    <div class="stat-card">
      <div class="num">{active_count}</div>
      <div class="lbl">Active</div>
    </div>
    <div class="stat-card">
      <div class="num">{completed_count}</div>
      <div class="lbl">Completed</div>
    </div>
    <div class="stat-card">
      <div class="num">{avg_progress:.1f}%</div>
      <div class="lbl">Avg Progress</div>
    </div>
  </div>

  <h2>Goal Tracking</h2>
{body_cards}
</body>
</html>
"""


def convert(
    sources: Sequence[str],
    destination: Optional[str] = None,
    report_title: str = DEFAULT_TITLE,
    status_filter: str = "all",
    overwrite: bool = False,
) -> int:
    """Load goals, generate HTML report, and write to destination or stdout."""
    goals = load(sources)
    html_content = generate_html_dashboard(
        goals,
        report_title=report_title,
        status_filter=status_filter,
    )
    payload = html_content.encode("utf-8")

    if not destination or destination == "-":
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
        return len(goals)

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
            with output:
                output.write(payload)
        except OSError:
            output_path.unlink(missing_ok=True)
            raise
    else:
        tmp_name = f".tmp_goals_html_{uuid.uuid4().hex}.html"
        tmp_path = parent_dir / tmp_name
        try:
            with tmp_path.open("xb") as tmp_file:
                tmp_file.write(payload)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            tmp_path.replace(output_path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

    return len(goals)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi goals JSON exports into a self-contained responsive HTML dashboard."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="One or more goal JSON export files, or '-' for stdin",
    )
    parser.add_argument("-o", "--output", help="Destination HTML file path (defaults to stdout)")
    parser.add_argument(
        "--title",
        default=DEFAULT_TITLE,
        help=f"HTML dashboard title (default: '{DEFAULT_TITLE}')",
    )
    parser.add_argument(
        "--status",
        choices=["all", "active", "completed", "inactive"],
        default="all",
        help="Filter goals by status: all, active, completed, or inactive (default: all)",
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
            report_title=args.title,
            status_filter=args.status,
            overwrite=args.overwrite,
        )
        if args.output and args.output != "-":
            print(f"HTML dashboard written to {args.output} ({count} goals loaded)")
        return 0
    except BrokenPipeError:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        os.close(devnull)
        return 1
    except (OSError, ValueError) as exc:
        sys.exit(f"HTML dashboard generation failed: {exc}")


if __name__ == "__main__":
    sys.exit(main())
