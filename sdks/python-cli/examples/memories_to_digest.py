#!/usr/bin/env python3
"""
Convert Omi memory list JSON exports into a periodic Markdown digest.

Analyzes captured facts, learnings, and second-brain memories to produce
an executive summary: daily totals, category distribution, top knowledge tags,
and recent highlight quotes.

Usage:
    # Direct pipeline export (stdin to Markdown digest)
    omi --json memory list --limit 200 | python memories_to_digest.py - digest.md

    # From one or more exported JSON files
    python memories_to_digest.py memories_w1.json memories_w2.json weekly_digest.md

    # With local timezone offset and date filter
    python memories_to_digest.py memories.json digest.md --utc-offset +08:00 --since 2026-09-01
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def text(value: Any) -> str:
    """Render a loosely typed field as a single sanitized string line."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    else:
        value = str(value)
    return " ".join(value.split())


def parse_time(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp string into an aware UTC datetime."""
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_offset(value: str) -> timedelta:
    """Turn '+08:00' / '-05:30' into a timedelta for local calendar day grouping."""
    v = value.strip()
    if (
        len(v) != 6
        or v[0] not in "+-"
        or v[3] != ":"
        or not (v[1:3] + v[4:]).isdigit()
    ):
        raise ValueError(f"UTC offset must match '+HH:MM' or '-HH:MM', got {value!r}")
    hours = int(v[1:3])
    minutes = int(v[4:])
    delta = timedelta(hours=hours, minutes=minutes)
    return -delta if v[0] == "-" else delta


def load(sources: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Load memory items from multiple JSON file paths or stdin ('-').
    Deduplicates items by their 'id'.
    """
    memories: Dict[str, Dict[str, Any]] = {}

    for src in sources:
        if src == "-":
            raw = sys.stdin.read()
            display_name = "<stdin>"
        else:
            p = Path(src)
            if not p.is_file():
                raise FileNotFoundError(f"Input file not found: {src}")
            raw = p.read_text(encoding="utf-8")
            display_name = src

        try:
            items = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{display_name}: invalid JSON ({exc})") from exc

        if not isinstance(items, list):
            raise ValueError(f"{display_name}: expected a JSON array of memories from 'omi --json memory list'")

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"{display_name}[{idx}]: each memory must be a JSON object")
            item_id = item.get("id")
            if not item_id or not isinstance(item_id, str):
                raise ValueError(f"{display_name}[{idx}]: missing or invalid string 'id'")
            memories[item_id] = item

    return memories


def generate_digest(
    memories: Dict[str, Dict[str, Any]],
    offset: timedelta = timedelta(0),
    title: str = "Omi Memory Digest",
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    top_tags_limit: int = 10,
) -> str:
    """
    Compile a dictionary of memories into a formatted Markdown digest.
    """
    filtered_items: List[Dict[str, Any]] = []
    undated = 0

    for item in memories.values():
        created_dt = parse_time(item.get("created_at"))
        if created_dt is None:
            undated += 1
            # If no time filters, include undated memories
            if since is None and until is None:
                filtered_items.append(item)
            continue

        if since is not None and created_dt < since:
            continue
        if until is not None and created_dt > until:
            continue
        filtered_items.append(item)

    total_memories = len(filtered_items)

    # Aggregations
    per_day: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    per_category: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    tag_counter: Counter[str] = Counter()
    dated_times: List[datetime] = []

    for item in filtered_items:
        created_dt = parse_time(item.get("created_at"))
        if created_dt:
            local_dt = created_dt + offset
            day_str = local_dt.strftime("%Y-%m-%d")
            per_day[day_str].append(item)
            dated_times.append(created_dt)

        cat_raw = text(item.get("category")).lower()
        cat = cat_raw if cat_raw else "(uncategorized)"
        per_category[cat].append(item)

        tags = item.get("tags")
        if isinstance(tags, list):
            for t in tags:
                tag_str = text(t).strip().lstrip("#")
                if tag_str:
                    tag_counter[tag_str] += 1

    # Date range string
    if dated_times:
        min_dt = min(dated_times) + offset
        max_dt = max(dated_times) + offset
        time_span = f"{min_dt.strftime('%Y-%m-%d')} to {max_dt.strftime('%Y-%m-%d')}"
    else:
        time_span = "No date recorded"

    # Assemble Markdown lines
    lines: List[str] = [
        f"# {title}",
        "",
        f"**Total Memories**: {total_memories} · **Active Days**: {len(per_day)} · **Timeframe**: {time_span}",
    ]
    if undated > 0:
        lines.append(f"- *Undated items included*: {undated}")
    lines.append("")

    if total_memories == 0:
        lines.append("_No memories found matching the specified criteria._")
        return "\n".join(lines) + "\n"

    # 1. Per-day Breakdown
    lines.extend([
        "## Daily Activity",
        "",
        "| Date | Memories Added | Primary Categories |",
        "|:---|---:|:---|",
    ])
    for day in sorted(per_day.keys(), reverse=True):
        items_that_day = per_day[day]
        cat_counts = Counter(
            text(m.get("category")).lower() or "(uncategorized)" for m in items_that_day
        )
        top_cats = ", ".join(f"`{c}` ({cnt})" for c, cnt in cat_counts.most_common(3))
        lines.append(f"| {day} | {len(items_that_day)} | {top_cats} |")
    lines.append("")

    # 2. Category Distribution
    lines.extend([
        "## Category Distribution",
        "",
        "| Category | Count | Share | Key Tags |",
        "|:---|---:|---:|:---|",
    ])
    sorted_categories = sorted(
        per_category.items(), key=lambda entry: (-len(entry[1]), entry[0])
    )
    for cat, items_in_cat in sorted_categories:
        count = len(items_in_cat)
        pct = (count / total_memories * 100.0) if total_memories else 0.0
        cat_tags: Counter[str] = Counter()
        for m in items_in_cat:
            for t in m.get("tags") or []:
                clean_t = text(t).strip().lstrip("#")
                if clean_t:
                    cat_tags[clean_t] += 1
        tags_preview = ", ".join(f"#{t}" for t, _ in cat_tags.most_common(3)) or "—"
        lines.append(f"| `{cat}` | {count} | {pct:.1f}% | {tags_preview} |")
    lines.append("")

    # 3. Top Knowledge Tags
    if tag_counter:
        lines.extend([
            "## Top Knowledge Tags & Themes",
            "",
            "| Tag | Mentions |",
            "|:---|---:|",
        ])
        for tag, count in tag_counter.most_common(top_tags_limit):
            lines.append(f"| `#{tag}` | {count} |")
        lines.append("")

    # 4. Recent Highlights
    lines.extend([
        "## Recent Knowledge Highlights",
        "",
    ])

    # Sort all filtered items by created_at descending (undated last)
    def sort_key(it: Dict[str, Any]) -> Tuple[int, datetime]:
        t = parse_time(it.get("created_at"))
        if t is None:
            return (0, datetime.min.replace(tzinfo=timezone.utc))
        return (1, t)

    recent_sample = sorted(filtered_items, key=sort_key, reverse=True)[:8]
    for m in recent_sample:
        body = text(m.get("content") or m.get("text") or m.get("memory") or "(empty memory)")
        cat = text(m.get("category")).lower() or "general"
        t = parse_time(m.get("created_at"))
        date_str = (t + offset).strftime("%Y-%m-%d") if t else "undated"
        m_id = text(m.get("id"))
        tags = [f"#{text(tag).strip().lstrip('#')}" for tag in (m.get("tags") or []) if text(tag).strip()]
        tags_str = f" {' '.join(tags)}" if tags else ""
        lines.append(f"- **[{cat}]** {body}{tags_str} `({date_str}, ID: {m_id[:8]})`")

    lines.append("")
    return "\n".join(lines)


def convert(
    sources: List[str],
    destination: str,
    offset: timedelta = timedelta(0),
    title: str = "Omi Memory Digest",
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    top_tags_limit: int = 10,
    force: bool = False,
) -> None:
    """Load sources, compile digest, and write to destination."""
    dest_path = Path(destination)
    if dest_path.exists() and not force:
        raise FileExistsError(
            f"Destination file already exists: {destination}. Use --force to overwrite."
        )

    memories = load(sources)
    digest_text = generate_digest(
        memories=memories,
        offset=offset,
        title=title,
        since=since,
        until=until,
        top_tags_limit=top_tags_limit,
    )

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(digest_text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile Omi memory exports into an executive Markdown digest.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  omi --json memory list | python memories_to_digest.py - digest.md
  python memories_to_digest.py memories.json weekly_digest.md --utc-offset +08:00
  python memories_to_digest.py m1.json m2.json all.md --since 2026-09-01 --force
""",
    )
    parser.add_argument(
        "sources",
        nargs="+",
        metavar="SOURCE",
        help="One or more JSON files exported from 'omi --json memory list', or '-' for stdin.",
    )
    parser.add_argument(
        "destination",
        metavar="DESTINATION",
        help="Path to output Markdown file (e.g. memories_digest.md).",
    )
    parser.add_argument(
        "--utc-offset",
        default="+00:00",
        help="UTC offset for local day grouping, formatted as '+HH:MM' or '-HH:MM' (default: +00:00).",
    )
    parser.add_argument(
        "--title",
        default="Omi Memory Digest",
        help="Header title for the generated digest.",
    )
    parser.add_argument(
        "--since",
        help="Optional ISO-8601 start timestamp filter (e.g. '2026-09-01T00:00:00Z').",
    )
    parser.add_argument(
        "--until",
        help="Optional ISO-8601 end timestamp filter (e.g. '2026-09-30T23:59:59Z').",
    )
    parser.add_argument(
        "--top-tags",
        type=int,
        default=10,
        help="Number of top knowledge tags to display (default: 10).",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite destination file if it already exists.",
    )

    args = parser.parse_args()

    try:
        offset = parse_offset(args.utc_offset)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    since_dt = parse_time(args.since) if args.since else None
    if args.since and since_dt is None:
        print(f"Error: Invalid --since timestamp: {args.since!r}", file=sys.stderr)
        sys.exit(2)

    until_dt = parse_time(args.until) if args.until else None
    if args.until and until_dt is None:
        print(f"Error: Invalid --until timestamp: {args.until!r}", file=sys.stderr)
        sys.exit(2)

    try:
        convert(
            sources=args.sources,
            destination=args.destination,
            offset=offset,
            title=args.title,
            since=since_dt,
            until=until_dt,
            top_tags_limit=args.top_tags,
            force=args.force,
        )
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
