#!/usr/bin/env python3
"""
Convert Omi action-item list JSON exports into an executive Markdown task velocity digest.

Analyzes captured tasks, follow-ups, and action items to produce an executive
productivity summary: completion rates, task velocity, overdue warnings,
daily creation timelines, and prioritized pending action queues.

Usage:
    # Direct pipeline export (stdin to Markdown digest)
    omi --json action-item list --limit 200 | python action_items_to_digest.py - tasks_digest.md

    # From one or more exported JSON files
    python action_items_to_digest.py tasks_w1.json tasks_w2.json weekly_task_digest.md

    # With local timezone offset and date window
    python action_items_to_digest.py tasks.json digest.md --utc-offset +08:00 --since 2026-09-01
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
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


def is_completed(value: Any) -> bool:
    """Normalize completion status from bool, int, or string."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "completed", "done")
    return False


def load(sources: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Load action item objects from multiple JSON files or stdin ('-').
    Deduplicates items by their 'id'.
    """
    items_map: Dict[str, Dict[str, Any]] = {}

    for src in sources:
        if src == "-":
            raw = sys.stdin.read()
            display_name = "<stdin>"
        else:
            p = Path(src)
            if not p.is_file():
                raise FileNotFoundError(f"Input file not found: {src}")
            raw = p.read_bytes().decode("utf-8-sig")
            display_name = src

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{display_name}: invalid JSON ({exc})") from exc

        if isinstance(parsed, dict):
            items = (
                parsed.get("action_items")
                or parsed.get("items")
                or parsed.get("data")
                or [parsed]
            )
        else:
            items = parsed

        if not isinstance(items, list):
            raise ValueError(f"{display_name}: expected a JSON array from 'omi --json action-item list'")

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"{display_name}[{idx}]: each action item must be an object")
            item_id = item.get("id")
            if not item_id or not isinstance(item_id, str):
                raise ValueError(f"{display_name}[{idx}]: missing or invalid string 'id'")
            items_map[item_id] = item

    return items_map


def generate_digest(
    action_items: Dict[str, Dict[str, Any]],
    offset: timedelta = timedelta(0),
    title: str = "Omi Action Items Digest",
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    now: Optional[datetime] = None,
) -> str:
    """
    Compile action items into an executive Markdown productivity digest.
    """
    ref_now = now or datetime.now(timezone.utc)
    filtered_items: List[Dict[str, Any]] = []
    undated = 0

    for item in action_items.values():
        created_dt = parse_time(item.get("created_at"))
        if created_dt is None:
            undated += 1
            if since is None and until is None:
                filtered_items.append(item)
            continue

        if since is not None and created_dt < since:
            continue
        if until is not None and created_dt > until:
            continue
        filtered_items.append(item)

    total_tasks = len(filtered_items)

    completed_items = [it for it in filtered_items if is_completed(it.get("completed"))]
    pending_items = [it for it in filtered_items if not is_completed(it.get("completed"))]

    completed_count = len(completed_items)
    pending_count = len(pending_items)
    completion_rate = (completed_count / total_tasks * 100.0) if total_tasks > 0 else 0.0

    # Overdue calculation
    overdue_items: List[Dict[str, Any]] = []
    for it in pending_items:
        due_dt = parse_time(it.get("due_at") or it.get("due_date"))
        if due_dt and due_dt < ref_now:
            overdue_items.append(it)

    # Per-day breakdown (by local creation date)
    per_day_created: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    dated_times: List[datetime] = []

    for it in filtered_items:
        created_dt = parse_time(it.get("created_at"))
        if created_dt:
            local_dt = created_dt + offset
            day_str = local_dt.strftime("%Y-%m-%d")
            per_day_created[day_str].append(it)
            dated_times.append(created_dt)

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
        f"**Total Tasks**: {total_tasks} · **Completed**: {completed_count} · **Pending**: {pending_count} · **Completion Rate**: {completion_rate:.1f}%",
    ]
    if overdue_items:
        lines.append(f"> ⚠️ **Overdue Tasks Attention Required**: {len(overdue_items)} pending task(s) are past their due date.")
    if undated > 0:
        lines.append(f"- *Undated items included*: {undated}")
    lines.append("")

    if total_tasks == 0:
        lines.append("_No action items found matching the specified criteria._")
        return "\n".join(lines) + "\n"

    # 1. Executive Summary Table
    lines.extend([
        "## Productivity Summary",
        "",
        "| Metric | Value |",
        "|:---|---:|",
        f"| Total Action Items | {total_tasks} |",
        f"| Completed Items | {completed_count} ({completion_rate:.1f}%) |",
        f"| Pending Items | {pending_count} ({(pending_count / total_tasks * 100.0):.1f}%) |",
        f"| Overdue Items | {len(overdue_items)} |",
        f"| Active Days | {len(per_day_created)} |",
        f"| Timeframe | {time_span} |",
        "",
    ])

    # 2. Daily Task Activity Table
    lines.extend([
        "## Daily Task Timeline",
        "",
        "| Date | Tasks Logged | Completed | Pending | Velocity |",
        "|:---|---:|---:|---:|---:|",
    ])
    for day in sorted(per_day_created.keys(), reverse=True):
        items_day = per_day_created[day]
        day_total = len(items_day)
        day_comp = sum(1 for it in items_day if is_completed(it.get("completed")))
        day_pend = day_total - day_comp
        day_rate = (day_comp / day_total * 100.0) if day_total else 0.0
        lines.append(f"| {day} | {day_total} | {day_comp} | {day_pend} | {day_rate:.0f}% |")
    lines.append("")

    # 3. Overdue Warning List (if any)
    if overdue_items:
        lines.extend([
            "## ⚠️ Overdue Action Items",
            "",
        ])
        for it in overdue_items:
            desc = text(it.get("description") or it.get("title") or "(untitled action item)")
            due_dt = parse_time(it.get("due_at") or it.get("due_date"))
            due_str = (due_dt + offset).strftime("%Y-%m-%d") if due_dt else "past due"
            it_id = text(it.get("id"))
            lines.append(f"- [ ] **[OVERDUE: {due_str}]** {desc} `(ID: {it_id[:8]})`")
        lines.append("")

    # 4. Pending Action Queue (Top Priority)
    lines.extend([
        "## Pending Action Queue",
        "",
    ])
    if pending_items:
        # Sort pending: overdue first, then by due date or created date
        def pending_sort_key(it: Dict[str, Any]) -> Tuple[int, datetime]:
            due_dt = parse_time(it.get("due_at") or it.get("due_date"))
            if due_dt:
                return (0, due_dt)
            created = parse_time(it.get("created_at"))
            return (1, created or datetime.max.replace(tzinfo=timezone.utc))

        for it in sorted(pending_items, key=pending_sort_key)[:15]:
            desc = text(it.get("description") or it.get("title") or "(untitled action item)")
            due_dt = parse_time(it.get("due_at") or it.get("due_date"))
            due_info = f" *(Due: {(due_dt + offset).strftime('%Y-%m-%d')})*" if due_dt else ""
            it_id = text(it.get("id"))
            lines.append(f"- [ ] {desc}{due_info} `(ID: {it_id[:8]})`")
    else:
        lines.append("_All tasks completed! No pending items._")
    lines.append("")

    # 5. Recent Completed Highlights
    lines.extend([
        "## Recently Completed Highlights",
        "",
    ])
    if completed_items:
        def completed_sort_key(it: Dict[str, Any]) -> datetime:
            up_dt = parse_time(it.get("updated_at")) or parse_time(it.get("created_at"))
            return up_dt or datetime.min.replace(tzinfo=timezone.utc)

        for it in sorted(completed_items, key=completed_sort_key, reverse=True)[:10]:
            desc = text(it.get("description") or it.get("title") or "(untitled action item)")
            it_id = text(it.get("id"))
            lines.append(f"- [x] ~~{desc}~~ `(ID: {it_id[:8]})`")
    else:
        lines.append("_No completed tasks recorded in this period._")
    lines.append("")

    return "\n".join(lines)


def convert(
    sources: List[str],
    destination: str,
    offset: timedelta = timedelta(0),
    title: str = "Omi Action Items Digest",
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    force: bool = False,
) -> None:
    """Load sources, compile digest, and write to destination."""
    dest_path = Path(destination)
    if dest_path.exists() and not force:
        raise FileExistsError(
            f"Destination file already exists: {destination}. Use --force to overwrite."
        )

    action_items = load(sources)
    digest_text = generate_digest(
        action_items=action_items,
        offset=offset,
        title=title,
        since=since,
        until=until,
    )

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(digest_text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile Omi action items into an executive Markdown task velocity digest.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  omi --json action-item list | python action_items_to_digest.py - digest.md
  python action_items_to_digest.py tasks.json weekly_digest.md --utc-offset +08:00
  python action_items_to_digest.py t1.json t2.json all.md --since 2026-09-01 --force
""",
    )
    parser.add_argument(
        "sources",
        nargs="+",
        metavar="SOURCE",
        help="One or more JSON files exported from 'omi --json action-item list', or '-' for stdin.",
    )
    parser.add_argument(
        "destination",
        metavar="DESTINATION",
        help="Path to output Markdown file (e.g. action_items_digest.md).",
    )
    parser.add_argument(
        "--utc-offset",
        default="+00:00",
        help="UTC offset for local day grouping, formatted as '+HH:MM' or '-HH:MM' (default: +00:00).",
    )
    parser.add_argument(
        "--title",
        default="Omi Action Items Digest",
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
            force=args.force,
        )
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
