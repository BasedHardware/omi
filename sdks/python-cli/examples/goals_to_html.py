"""
Convert Omi goals JSON exports to a standalone, interactive HTML goal achievement & OKR dashboard.

Usage:
    # Direct pipeline export (stdin to HTML)
    omi --json goal list --include-inactive | python goals_to_html.py - goals_dashboard.html

    # Convert from saved JSON file
    python goals_to_html.py goals.json goals_dashboard.html

    # Filter only active goals
    python goals_to_html.py goals.json active_goals.html --status active
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional

STYLE = """
:root {
  --bg-color: #0f172a;
  --card-bg: #1e293b;
  --card-border: #334155;
  --text-main: #f8fafc;
  --text-muted: #94a3b8;
  --primary: #38bdf8;
  --primary-glow: rgba(56, 189, 248, 0.15);
  --success: #10b981;
  --warning: #f59e0b;
  --badge-active-bg: #064e3b;
  --badge-active-text: #6ee7b7;
  --badge-done-bg: #1e3a8a;
  --badge-done-text: #93c5fd;
  --progress-track: #334155;
  --progress-fill: linear-gradient(90deg, #38bdf8, #818cf8);
  --progress-done: #10b981;
}
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  margin: 2rem auto;
  max-width: 68rem;
  padding: 0 1.5rem;
  color: var(--text-main);
  background: var(--bg-color);
  line-height: 1.6;
}
header {
  margin-bottom: 2rem;
  border-bottom: 1px solid var(--card-border);
  padding-bottom: 1.5rem;
}
h1 { font-size: 2rem; margin: 0 0 0.5rem 0; font-weight: 700; color: #fff; }
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1rem;
  margin: 1.5rem 0;
}
.stat-card {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 0.75rem;
  padding: 1.25rem;
  text-align: center;
}
.stat-value { font-size: 1.8rem; font-weight: 700; color: var(--primary); }
.stat-label { font-size: 0.85rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }

.controls {
  margin-bottom: 2rem;
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  align-items: center;
}
.search-box {
  flex: 1;
  min-width: 240px;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 0.5rem;
  padding: 0.65rem 1rem;
  color: #fff;
  font-size: 0.95rem;
}
.search-box:focus { outline: 2px solid var(--primary); }

.goals-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1.25rem;
}
.goal-card {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 0.75rem;
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  transition: transform 0.15s ease, border-color 0.15s ease;
}
.goal-card:hover {
  transform: translateY(-2px);
  border-color: var(--primary);
  box-shadow: 0 8px 24px var(--primary-glow);
}
.goal-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}
.goal-title {
  font-size: 1.05rem;
  font-weight: 600;
  color: #fff;
  margin: 0;
  word-break: break-word;
}
.badge {
  display: inline-block;
  font-size: 0.75rem;
  font-weight: 600;
  padding: 0.2rem 0.55rem;
  border-radius: 9999px;
  text-transform: uppercase;
  white-space: nowrap;
}
.badge-active { background: var(--badge-active-bg); color: var(--badge-active-text); }
.badge-done { background: var(--badge-done-bg); color: var(--badge-done-text); }

.progress-container {
  margin: 1rem 0;
}
.progress-meta {
  display: flex;
  justify-content: space-between;
  font-size: 0.85rem;
  margin-bottom: 0.4rem;
  color: var(--text-muted);
}
.progress-bar-bg {
  width: 100%;
  height: 0.5rem;
  background: var(--progress-track);
  border-radius: 9999px;
  overflow: hidden;
}
.progress-bar-fill {
  height: 100%;
  background: var(--progress-fill);
  border-radius: 9999px;
  transition: width 0.3s ease;
}
.progress-bar-fill.done {
  background: var(--progress-done);
}

.goal-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
  font-size: 0.8rem;
  border-top: 1px solid #334155;
  padding-top: 0.75rem;
  color: var(--text-muted);
}
.type-badge {
  background: #0f172a;
  color: #94a3b8;
  padding: 0.15rem 0.5rem;
  border-radius: 0.25rem;
  font-size: 0.75rem;
  text-transform: capitalize;
}
.date-str {
  margin-left: auto;
  font-size: 0.75rem;
}

@media print {
  body { background: #fff; color: #000; margin: 0; padding: 0; }
  .goal-card { background: #fff; border: 1px solid #ccc; break-inside: avoid; box-shadow: none; }
  .goal-title { color: #000; }
  .search-box { display: none; }
}
"""

SCRIPT_JS = """
function filterGoals() {
  const query = document.getElementById('search').value.toLowerCase();
  const cards = document.querySelectorAll('.goal-card');
  let visibleCount = 0;
  cards.forEach(card => {
    const text = card.textContent.toLowerCase();
    if (text.includes(query)) {
      card.style.display = '';
      visibleCount++;
    } else {
      card.style.display = 'none';
    }
  });
  document.getElementById('visible-counter').textContent = visibleCount;
}
"""


def sanitize_text(text: Optional[str]) -> str:
    """Normalize whitespace and remove control characters."""
    if not text:
        return ""
    if not isinstance(text, str):
        text = str(text)
    cleaned = re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", "", text)
    return " ".join(cleaned.split())


def calculate_progress(goal: Dict[str, Any]) -> tuple[Optional[float], str]:
    """Calculate progress percentage and text label."""
    goal_type = goal.get("goal_type")
    is_active = goal.get("is_active", True)
    unit = sanitize_text(goal.get("unit"))
    unit_str = f" {unit}" if unit else ""

    if not goal_type or goal_type == "qualitative":
        if not is_active:
            return 100.0, "Completed"
        return None, "Qualitative Goal"

    if goal_type == "boolean":
        cur = goal.get("current_value") or 0
        target = goal.get("target_value") or 1
        if not is_active or cur >= target:
            return 100.0, "Achieved (1/1)"
        return 0.0, "In Progress (0/1)"

    target = goal.get("target_value")
    cur = goal.get("current_value") or 0
    min_val = goal.get("min_value") or 0

    if target is None:
        target = goal.get("max_value")

    if target is None or target == min_val:
        return (100.0 if not is_active else 0.0), f"{cur}{unit_str}"

    pct = max(0.0, min(100.0, ((cur - min_val) / (target - min_val)) * 100.0))
    label = f"{pct:.1f}% ({cur:g}/{target:g}{unit_str})"
    return pct, label


def render_html(goals: List[Dict[str, Any]], title: str = "Omi Goals & OKR Dashboard") -> str:
    """Generate self-contained, interactive HTML goal achievement dashboard."""
    total = len(goals)
    active_goals = [g for g in goals if g.get("is_active", True)]
    completed_goals = [g for g in goals if not g.get("is_active", True)]
    completion_rate = f"{(len(completed_goals) / total * 100):.1f}%" if total > 0 else "0.0%"

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    cards: List[str] = []
    for g in goals:
        g_title = escape(sanitize_text(g.get("title") or "Untitled Goal"))
        is_active = g.get("is_active", True)
        goal_type = escape(sanitize_text(g.get("goal_type") or "qualitative"))
        created_at = sanitize_text(g.get("created_at"))
        date_display = escape(created_at[:10]) if created_at else ""

        status_badge = (
            '<span class="badge badge-active">Active</span>'
            if is_active
            else '<span class="badge badge-done">Completed</span>'
        )

        pct, progress_label = calculate_progress(g)
        progress_label_esc = escape(progress_label)

        if pct is not None:
            fill_class = "progress-bar-fill done" if pct >= 100.0 or not is_active else "progress-bar-fill"
            progress_html = f"""
            <div class="progress-container">
              <div class="progress-meta">
                <span>Progress</span>
                <span><strong>{progress_label_esc}</strong></span>
              </div>
              <div class="progress-bar-bg">
                <div class="{fill_class}" style="width: {pct:.1f}%;"></div>
              </div>
            </div>
            """
        else:
            progress_html = f"""
            <div class="progress-container">
              <div class="progress-meta">
                <span>Status</span>
                <span style="color: var(--primary);"><strong>{progress_label_esc}</strong></span>
              </div>
            </div>
            """

        cards.append(f"""
        <div class="goal-card">
          <div>
            <div class="goal-header">
              <h3 class="goal-title">{g_title}</h3>
              {status_badge}
            </div>
            {progress_html}
          </div>
          <div class="goal-meta">
            <span class="type-badge">{goal_type}</span>
            <span class="date-str">{date_display}</span>
          </div>
        </div>
        """)

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
      <div class="stat-label">Total Goals</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" style="color: #38bdf8;">{len(active_goals)}</div>
      <div class="stat-label">Active / In Progress</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" style="color: #10b981;">{len(completed_goals)}</div>
      <div class="stat-label">Completed</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" style="color: #818cf8;">{completion_rate}</div>
      <div class="stat-label">Completion Rate</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" style="color: #f59e0b;" id="visible-counter">{total}</div>
      <div class="stat-label">Visible Goals</div>
    </div>
  </div>

  <div class="controls">
    <input type="text" id="search" class="search-box" placeholder="Search goals by title, metric, or type..." oninput="filterGoals()">
  </div>

  <div class="goals-grid">
    {''.join(cards)}
  </div>

  <script>
{SCRIPT_JS}
  </script>
</body>
</html>
"""
    return html


def load_goals(source: str) -> List[Dict[str, Any]]:
    """Load goals list from file or stdin."""
    if source == "-":
        content = sys.stdin.read()
    else:
        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(f"Input file not found: {source}")
        content = path.read_text(encoding="utf-8")

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {source}: {exc}") from None

    if isinstance(data, dict):
        if "goals" in data and isinstance(data["goals"], list):
            data = data["goals"]
        elif "items" in data and isinstance(data["items"], list):
            data = data["items"]

    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list of goals from {source}")

    goals: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()

    for item in data:
        if not isinstance(item, dict):
            continue
        goal_id = item.get("id")
        if goal_id and isinstance(goal_id, str):
            if goal_id in seen_ids:
                continue
            seen_ids.add(goal_id)
        goals.append(item)

    return goals


def convert(
    source: str,
    destination: str,
    status_filter: str = "all",
    title: str = "Omi Goals & OKR Dashboard",
    overwrite: bool = True,
) -> int:
    """Convert input goals JSON to standalone HTML dashboard."""
    goals = load_goals(source)

    if status_filter == "active":
        goals = [g for g in goals if g.get("is_active", True)]
    elif status_filter == "completed":
        goals = [g for g in goals if not g.get("is_active", True)]

    payload = render_html(goals, title=title)
    output_path = Path(destination)
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing {output_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(payload, encoding="utf-8")
    return len(goals)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi goals JSON exports to an interactive, standalone HTML dashboard."
    )
    parser.add_argument("source", help="Path to input JSON file or '-' for stdin.")
    parser.add_argument("destination", help="Path to output HTML file.")
    parser.add_argument(
        "--status",
        choices=["all", "active", "completed"],
        default="all",
        help="Filter goals by status: all (default), active, or completed.",
    )
    parser.add_argument("--title", default="Omi Goals & OKR Dashboard", help="Custom dashboard page title.")
    parser.add_argument("--no-overwrite", action="store_true", help="Prevent overwriting existing output file.")

    args = parser.parse_args()

    try:
        count = convert(
            source=args.source,
            destination=args.destination,
            status_filter=args.status,
            title=args.title,
            overwrite=not args.no_overwrite,
        )
    except (ValueError, FileNotFoundError, FileExistsError, OSError) as exc:
        sys.exit(f"Error: {exc}")

    print(f"Successfully rendered {count} goal{'s' if count != 1 else ''} to {args.destination}")


if __name__ == "__main__":
    main()
