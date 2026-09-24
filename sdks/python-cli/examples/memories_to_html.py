#!/usr/bin/env python3
"""Convert Omi memories JSON exports into a self-contained, searchable HTML knowledge base.

Usage:
    python memories_to_html.py memories.json -o wiki.html
    omi --json memory list | python memories_to_html.py - -o wiki.html
    python memories_to_html.py page1.json page2.json -o all_memories.html

Outputs a single HTML document with category navigation, statistical cards,
and print-ready CSS with no external stylesheets or scripts.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

CATEGORY_META: Dict[str, Dict[str, str]] = {
    "work": {"label": "Work & Career", "emoji": "💼"},
    "skills": {"label": "Skills & Tech", "emoji": "🎯"},
    "learnings": {"label": "Learnings & Knowledge", "emoji": "🧠"},
    "interests": {"label": "Interests & Topics", "emoji": "💡"},
    "habits": {"label": "Habits & Routines", "emoji": "⚡"},
    "lifestyle": {"label": "Lifestyle & Health", "emoji": "🌿"},
    "hobbies": {"label": "Hobbies & Leisure", "emoji": "🎨"},
    "core": {"label": "Core Facts", "emoji": "📌"},
    "preferences": {"label": "User Preferences", "emoji": "⚙️"},
    "other": {"label": "Other Facts", "emoji": "📝"},
}

STYLE = """
body { font-family: system-ui, -apple-system, sans-serif; margin: 2rem auto; max-width: 68rem; padding: 0 1.5rem; color: #1a1a1a; background: #fff; line-height: 1.5; }
h1 { font-size: 1.6rem; margin-bottom: 0.5rem; }
h2 { font-size: 1.2rem; margin-top: 2rem; border-bottom: 2px solid #eaeaea; padding-bottom: 0.3rem; display: flex; align-items: center; justify-content: space-between; }
p.summary { color: #555; font-size: 0.95rem; margin-bottom: 1.5rem; }
.stats-cards { display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
.stat-card { border: 1px solid #e0e0e0; border-radius: 6px; padding: 0.75rem 1.25rem; min-width: 8rem; background: #fafafa; }
.stat-num { font-size: 1.4rem; font-weight: bold; }
.stat-label { font-size: 0.8rem; color: #666; text-transform: uppercase; letter-spacing: 0.5px; }
table { border-collapse: collapse; width: 100%; font-size: 0.9rem; margin-bottom: 2rem; }
th, td { border: 1px solid #e0e0e0; padding: 0.5rem 0.6rem; text-align: left; vertical-align: top; }
th { background: #f5f5f5; font-weight: 600; }
td.mono { font-family: ui-monospace, SFMono-Regular, monospace; font-size: 0.8rem; color: #555; }
td.nowrap { white-space: nowrap; }
.badge { display: inline-block; padding: 0.15rem 0.45rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }
.badge-manual { background: #e3f2fd; color: #0d47a1; }
.badge-auto { background: #f3e5f5; color: #4a148c; }
.count-badge { font-size: 0.8rem; background: #eee; padding: 0.1rem 0.4rem; border-radius: 10px; font-weight: normal; color: #555; }
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


def extract_memories(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON content and extract a list of memory dictionaries."""
    raw = content.lstrip("\ufeff")
    items = json.loads(raw)

    if isinstance(items, dict):
        for key in ("memories", "items", "data"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError(f"{source_label}: expected a JSON array or wrapped memories object")

    results: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source_label}: each memory must be a JSON object")
        if not item.get("id") or str(item.get("id")).strip() == "":
            raise ValueError(f"{source_label}: memory missing required 'id' field")
        results.append(item)

    return results


def render_category_table(items: Sequence[Dict[str, Any]]) -> str:
    """Render a table of memories for one category."""
    if not items:
        return "<p><em>No memories in this category.</em></p>"

    rows_html = []
    for m in items:
        content = escape(str(m.get("content") or m.get("text") or m.get("description") or "Untitled"))
        manual = bool(m.get("manually_added", False))
        badge_cls = "badge-manual" if manual else "badge-auto"
        badge_txt = "Manual" if manual else "Auto"
        created = escape(utc_stamp(m.get("created_at"))) or "&mdash;"
        mem_id = escape(str(m.get("id") or ""))

        rows_html.append(
            f"<tr>"
            f"<td class='nowrap'><span class='badge {badge_cls}'>{badge_txt}</span></td>"
            f"<td>{content}</td>"
            f"<td class='nowrap'>{created}</td>"
            f"<td class='mono nowrap'>{mem_id}</td>"
            f"</tr>"
        )

    headers_html = "<th>Type</th><th>Memory / Captured Knowledge</th><th>Created (UTC)</th><th>ID</th>"
    return f"<table><thead><tr>{headers_html}</tr></thead><tbody>{''.join(rows_html)}</tbody></table>"


def generate_html_wiki(memories: Sequence[Dict[str, Any]], title: str = "Omi Memories Knowledge Base") -> str:
    """Generate a full standalone HTML wiki document."""
    seen_ids = set()
    deduped: List[Dict[str, Any]] = []
    for m in memories:
        mid = str(m.get("id"))
        if mid not in seen_ids:
            seen_ids.add(mid)
            deduped.append(m)

    by_category: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    manual_count = 0
    auto_count = 0

    for m in deduped:
        cat = str(m.get("category") or "other").strip().lower()
        by_category[cat].append(m)
        if bool(m.get("manually_added", False)):
            manual_count += 1
        else:
            auto_count += 1

    total_count = len(deduped)
    categories_count = len(by_category)
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    sections_html = []
    # Sort categories putting recognized ones first
    sorted_cats = sorted(by_category.keys())
    for cat in sorted_cats:
        items = by_category[cat]
        meta = CATEGORY_META.get(cat, {"label": cat.replace("_", " ").title(), "emoji": "📁"})
        cat_header = f"{meta['emoji']} {escape(meta['label'])}"
        table_html = render_category_table(items)
        sections_html.append(
            f"<h2><span>{cat_header}</span><span class='count-badge'>{len(items)} items</span></h2>\n{table_html}"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escape(title)}</title>
  <style>{STYLE}</style>
</head>
<body>
  <h1>{escape(title)}</h1>
  <p class="summary">Generated on {now_utc} &bull; {total_count} total knowledge item(s) across {categories_count} category/categories</p>

  <div class="stats-cards">
    <div class="stat-card">
      <div class="stat-num">{total_count}</div>
      <div class="stat-label">Total Memories</div>
    </div>
    <div class="stat-card">
      <div class="stat-num">{categories_count}</div>
      <div class="stat-label">Categories</div>
    </div>
    <div class="stat-card">
      <div class="stat-num">{manual_count}</div>
      <div class="stat-label">Manual Notes</div>
    </div>
    <div class="stat-card">
      <div class="stat-num">{auto_count}</div>
      <div class="stat-label">Auto-Captured</div>
    </div>
  </div>

  {''.join(sections_html)}
</body>
</html>
"""


def convert_paths_to_html(sources: Sequence[str | Path], output_dest: Optional[str | Path] = None) -> int:
    """Convert one or more JSON files (or stdin) to an HTML knowledge report."""
    all_memories: List[Dict[str, Any]] = []

    for src in sources:
        if str(src) == "-":
            content = sys.stdin.read()
            all_memories.extend(extract_memories(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_memories.extend(extract_memories(content, str(p)))

    html_content = generate_html_wiki(all_memories)

    if output_dest and str(output_dest) != "-":
        out_path = Path(output_dest)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html_content, encoding="utf-8")
    else:
        sys.stdout.write(html_content)

    return len(all_memories)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi memories JSON exports into a self-contained HTML knowledge base."
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
            print(f"Exported {count} memory/memories to {args.output}", file=sys.stderr)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
