"""Convert Omi memories JSON exports into a clean, self-contained HTML report.

Usage:
    # Basic export from saved JSON
    python memories_to_html.py memories.html memories.json

    # With local timezone offset and custom title
    python memories_to_html.py --utc-offset +09:00 --title "Brain Knowledge Base" memories.html memories.json
    python memories_to_html.py --utc-offset=-05:00 memories.html memories.json

    # Filter specific category
    python memories_to_html.py --category work memories.html memories.json

    # From stdin pipeline
    omi --json memory list --limit 200 | python memories_to_html.py memories.html -
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html import escape
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple
import uuid

CATEGORY_META: Dict[str, Dict[str, str]] = {
    "work": {"label": "Work", "emoji": "💼"},
    "personal": {"label": "Personal", "emoji": "👤"},
    "learnings": {"label": "Learnings", "emoji": "🧠"},
    "interests": {"label": "Interests", "emoji": "💡"},
    "habits": {"label": "Habits", "emoji": "⚡"},
    "lifestyle": {"label": "Lifestyle", "emoji": "🌿"},
    "hobbies": {"label": "Hobbies", "emoji": "🎨"},
    "core": {"label": "Core Facts", "emoji": "📌"},
    "interesting": {"label": "Interesting", "emoji": "✨"},
    "manual": {"label": "Manual Notes", "emoji": "✍️"},
    "workflow": {"label": "Workflow", "emoji": "🔄"},
    "system": {"label": "System", "emoji": "⚙️"},
    "other": {"label": "Other Facts", "emoji": "📝"},
}

STYLE = """
:root {
  --bg: #ffffff;
  --text: #1f2937;
  --muted: #4b5563;
  --border: #e5e7eb;
  --card-bg: #f9fafb;
  --row-hover: #f3f4f6;
  --badge-cat-bg: #eff6ff;
  --badge-cat-text: #1d4ed8;
  --badge-tag-bg: #f3f4f6;
  --badge-tag-text: #374151;
  --badge-priv-bg: #fef2f2;
  --badge-priv-text: #b91c1c;
}
body {
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  margin: 2rem auto;
  max-width: 72rem;
  padding: 0 1.25rem;
  color: var(--text);
  background: var(--bg);
  line-height: 1.5;
}
h1 { font-size: 1.75rem; font-weight: 700; margin-bottom: 0.5rem; }
h2 {
  font-size: 1.25rem;
  font-weight: 600;
  margin-top: 2rem;
  margin-bottom: 0.75rem;
  border-bottom: 2px solid var(--border);
  padding-bottom: 0.3rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
p.summary { color: var(--muted); font-size: 0.95rem; margin-bottom: 1.5rem; }
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}
.stat-card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  padding: 0.75rem 1rem;
  text-align: center;
}
.stat-card .num { font-size: 1.5rem; font-weight: 700; }
.stat-card .lbl { font-size: 0.75rem; text-transform: uppercase; color: var(--muted); letter-spacing: 0.05em; }
.memory-card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  padding: 1rem 1.25rem;
  margin-bottom: 0.85rem;
  transition: background 0.15s ease;
}
.memory-card:hover { background: var(--row-hover); }
.memory-content {
  font-size: 0.95rem;
  margin-bottom: 0.5rem;
  word-break: break-word;
}
.memory-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8rem;
  color: var(--muted);
}
.badge {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  font-size: 0.75rem;
  font-weight: 600;
  border-radius: 0.25rem;
  text-transform: capitalize;
}
.badge-category { background: var(--badge-cat-bg); color: var(--badge-cat-text); }
.badge-tag { background: var(--badge-tag-bg); color: var(--badge-tag-text); font-family: ui-monospace, monospace; }
.badge-private { background: var(--badge-priv-bg); color: var(--badge-priv-text); }
.memory-id { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 0.75rem; color: var(--muted); }
@media print {
  body { margin: 0; padding: 0; max-width: 100%; color: #000; background: #fff; }
  .memory-card { page-break-inside: avoid; border: 1px solid #ccc; margin-bottom: 0.5rem; }
  h2 { page-break-after: avoid; }
}
"""


def parse_time(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None if unusable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def parse_offset(value: str) -> timedelta:
    """Turn '+09:00' / '-05:30' into a timedelta for local calendar dates and times."""
    if len(value) != 6 or value[0] not in "+-" or value[3] != ":" or not (value[1:3] + value[4:]).isdigit():
        raise ValueError(f"UTC offset must look like +09:00 or -05:00, got {value!r}")
    delta = timedelta(hours=int(value[1:3]), minutes=int(value[4:]))
    if int(value[4:]) > 59 or delta > timedelta(hours=14):
        raise ValueError(f"UTC offset must be between -14:00 and +14:00, got {value!r}")
    return -delta if value[0] == "-" else delta


def format_time(dt: Optional[datetime], offset: timedelta) -> str:
    """Format a datetime adjusted by offset into 'YYYY-MM-DD HH:MM' or empty string."""
    if dt is None:
        return ""
    try:
        local_dt = dt + offset
        return local_dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, OverflowError):
        return ""


def unwrap_memories(raw: Any, source_name: str = "") -> List[Dict[str, Any]]:
    """Unwrap an array of memories, an envelope dict, or a single memory object."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("memories", "items", "data", "results"):
            candidate = raw.get(key)
            if isinstance(candidate, list):
                return candidate
        if "id" in raw or "content" in raw:
            return [raw]
    raise ValueError(f"{source_name}: expected a JSON array or envelope of memories")


def load(sources: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """Load and deduplicate memories from multiple files or stdin."""
    items_by_id: Dict[str, Dict[str, Any]] = {}
    for source in sources:
        if source == "-":
            content = sys.stdin.buffer.read()
            source_label = "stdin"
        else:
            source_label = source
            content = Path(source).read_bytes()

        if not content.strip():
            continue

        raw = json.loads(content.decode("utf-8-sig"))
        items = unwrap_memories(raw, source_label)
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"{source_label} item {idx}: each memory must be an object")
            item_id = item.get("id")
            if isinstance(item_id, str) and item_id.strip():
                clean_id = item_id.strip()
            else:
                clean_id = f"auto_{uuid.uuid4().hex}"
                while clean_id in items_by_id:
                    clean_id = f"auto_{uuid.uuid4().hex}"
            items_by_id[clean_id] = item
    return items_by_id


def report(
    items_by_id: Dict[str, Dict[str, Any]],
    offset: timedelta,
    offset_label: str,
    title: str = "Omi Memories Report",
    category_filter: Optional[str] = None,
    now: Optional[datetime] = None,
) -> str:
    """Generate self-contained HTML document for the loaded memories."""
    # Filter memories if category_filter is supplied
    filtered_items: List[Dict[str, Any]] = []
    for item_id, item in items_by_id.items():
        cat = str(item.get("category") or "other").strip().lower()
        if category_filter and cat != category_filter.strip().lower():
            continue
        filtered_items.append({"_id": item_id, **item})

    # Sort memories reverse-chronologically by created_at
    def sort_key(m: Dict[str, Any]) -> Tuple[datetime, str]:
        parsed = parse_time(m.get("created_at"))
        dt = parsed if parsed is not None else datetime.min.replace(tzinfo=timezone.utc)
        return (dt, str(m.get("_id") or ""))

    filtered_items.sort(key=sort_key, reverse=True)

    # Collect statistics
    total_count = len(filtered_items)
    categories = set()
    tagged_count = 0
    private_count = 0

    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for m in filtered_items:
        cat = str(m.get("category") or "other").strip().lower()
        categories.add(cat)
        grouped[cat].append(m)

        tags = m.get("tags")
        if isinstance(tags, list) and len(tags) > 0:
            tagged_count += 1
        elif isinstance(tags, str) and tags.strip():
            tagged_count += 1

        vis = str(m.get("visibility") or "").strip().lower()
        if vis == "private" or m.get("private") is True:
            private_count += 1

    parts: List[str] = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="utf-8">',
        '  <meta name="viewport" content="width=device-width, initial-scale=1">',
        f"  <title>{escape(title)}</title>",
        f"  <style>{STYLE}</style>",
        "</head>",
        "<body>",
        f"  <h1>{escape(title)}</h1>",
    ]

    tz_note = f" Times shown in UTC{offset_label}." if offset_label else " Times shown in UTC."
    summary_text = (
        f"Total: {total_count} · Categories: {len(categories)} · Tagged: {tagged_count} · Private: {private_count}."
        + tz_note
    )
    parts.append(f'  <p class="summary">{escape(summary_text)}</p>')

    # Stats Grid
    parts += [
        '  <div class="stats-grid">',
        f'    <div class="stat-card"><div class="num">{total_count}</div><div class="lbl">Total Memories</div></div>',
        f'    <div class="stat-card"><div class="num" style="color:var(--badge-cat-text);">{len(categories)}</div><div class="lbl">Categories</div></div>',
        f'    <div class="stat-card"><div class="num">{tagged_count}</div><div class="lbl">Tagged</div></div>',
        f'    <div class="stat-card"><div class="num" style="color:var(--badge-priv-text);">{private_count}</div><div class="lbl">Private</div></div>',
        "  </div>",
    ]

    if not filtered_items:
        parts.append('  <p class="summary"><em>No memories found matching the export criteria.</em></p>')
        parts += ["</body>", "</html>\n"]
        return "\n".join(parts)

    # Grouped display
    sorted_cats = sorted(grouped.keys())
    for cat in sorted_cats:
        meta = CATEGORY_META.get(cat, {"label": cat.replace("_", " ").title(), "emoji": "📁"})
        cat_heading = f"{meta['emoji']} {meta['label']} ({len(grouped[cat])})"
        parts.append(f"  <h2>{escape(cat_heading)}</h2>")

        for item in grouped[cat]:
            item_id = str(item.get("_id") or "")
            content = str(item.get("content") or "").strip()
            if not content:
                content = "Untitled memory"

            created_str = format_time(parse_time(item.get("created_at")), offset)
            vis = str(item.get("visibility") or "").strip().lower()
            is_priv = vis == "private" or item.get("private") is True

            card_lines = [
                '  <div class="memory-card">',
                f'    <div class="memory-content">{escape(content)}</div>',
                '    <div class="memory-meta">',
            ]

            if created_str:
                card_lines.append(f"      <span>🕒 {escape(created_str)}</span>")

            card_lines.append(f'      <span class="badge badge-category">{escape(meta["label"])}</span>')

            tags = item.get("tags")
            if isinstance(tags, list):
                for t in tags:
                    if t:
                        clean_t = re.sub(r"[^\w-]", "", str(t)).strip()
                        if clean_t:
                            card_lines.append(f'      <span class="badge badge-tag">#{escape(clean_t)}</span>')
            elif isinstance(tags, str) and tags.strip():
                clean_t = re.sub(r"[^\w-]", "", tags).strip()
                if clean_t:
                    card_lines.append(f'      <span class="badge badge-tag">#{escape(clean_t)}</span>')

            if is_priv:
                card_lines.append('      <span class="badge badge-private">🔒 Private</span>')

            if item_id:
                card_lines.append(f'      <span class="memory-id">id: {escape(item_id)}</span>')

            card_lines += ["    </div>", "  </div>"]
            parts.extend(card_lines)

    parts += ["</body>", "</html>\n"]
    return "\n".join(parts)


def convert(
    sources: Sequence[str],
    destination: str,
    offset: timedelta = timedelta(0),
    offset_label: str = "",
    title: str = "Omi Memories Report",
    category_filter: Optional[str] = None,
    overwrite: bool = False,
    now: Optional[datetime] = None,
) -> int:
    """Generate the HTML report and write it safely."""
    items = load(sources)
    html_content = report(
        items,
        offset,
        offset_label,
        title=title,
        category_filter=category_filter,
        now=now,
    ).encode("utf-8")
    output_path = Path(destination)
    parent_dir = output_path.parent
    parent_dir.mkdir(parents=True, exist_ok=True)

    if not overwrite:
        try:
            with output_path.open("xb") as output:
                output.write(html_content)
        except FileExistsError:
            raise FileExistsError(f"Refusing to overwrite existing {output_path} (use --overwrite to replace)") from None
    else:
        # Atomic write to temporary file in same directory, then replace destination
        with tempfile.NamedTemporaryFile("wb", dir=parent_dir, delete=False, prefix=".tmp_memories_") as tmp_file:
            tmp_path = Path(tmp_file.name)
            try:
                tmp_file.write(html_content)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            except BaseException:
                tmp_path.unlink(missing_ok=True)
                raise
        tmp_path.replace(output_path)

    return len(items)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi memories JSON exports into a self-contained HTML report."
    )
    parser.add_argument("output", help="Destination HTML file path")
    parser.add_argument("inputs", nargs="+", help="One or more memory JSON export files, or '-' for stdin")
    parser.add_argument(
        "--utc-offset",
        default="",
        help="Local UTC offset, e.g. +09:00 or --utc-offset=-05:00",
    )
    parser.add_argument("--category", default=None, help="Filter memories by category (e.g. work, learnings)")
    parser.add_argument("--title", default="Omi Memories Report", help="Report document title")
    parser.add_argument("--overwrite", action="store_true", help="Allow overwriting existing destination file")

    args = parser.parse_args(argv)

    offset = timedelta(0)
    offset_label = ""
    if args.utc_offset:
        try:
            offset = parse_offset(args.utc_offset)
            offset_label = args.utc_offset
        except ValueError as exc:
            sys.exit(f"Report failed: {exc}")

    try:
        count = convert(
            args.inputs,
            args.output,
            offset=offset,
            offset_label=offset_label,
            title=args.title,
            category_filter=args.category,
            overwrite=args.overwrite,
        )
        print(f"Report written to {args.output} ({count} memories)")
        return 0
    except (OSError, ValueError) as exc:
        sys.exit(f"Report failed: {exc}")


if __name__ == "__main__":
    sys.exit(main())
