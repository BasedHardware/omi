#!/usr/bin/env python3
"""Convert Omi goals JSON export into an RFC 5545 VTODO task feed (.ics).

Usage:
    python goals_to_vtodo.py goals.json -o goals_tasks.ics
    omi --json goal list | python goals_to_vtodo.py - -o milestones.ics

Converts goals into standard VTODO components for CalDAV task managers,
Apple Reminders, OmniFocus, and Things 3. Tracks progress percentages,
completion statuses, and target due dates.
Requires only the Python standard library.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List


def extract_goals(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON and extract list of goal items."""
    raw = content.lstrip("\ufeff")
    if not raw.strip():
        raise ValueError(f"{source_label}: empty JSON input")
    try:
        items = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{source_label}: invalid JSON ({exc.msg} at line {exc.lineno} column {exc.colno})") from exc

    if isinstance(items, dict):
        for key in ("goals", "items", "data"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError(f"{source_label}: expected a JSON array or wrapped goals object")

    results = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("name") or "").strip()
        gid = str(item.get("id") or "").strip()
        if title and gid:
            results.append(item)

    return results


def escape_ics(text: str) -> str:
    """Escape text for RFC 5545 text value grammar."""
    if not text:
        return ""
    text = text.replace("\\", "\\\\")
    text = text.replace(";", "\\;")
    text = text.replace(",", "\\,")
    text = text.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
    return text


def format_dt(iso_str: str | None) -> str | None:
    """Format ISO timestamp into RFC 5545 UTC timestamp (YYYYMMDDTHHMMSSZ)."""
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    except Exception:
        return None


def generate_vcalendar(goals: List[Dict[str, Any]], cal_name: str = "Omi Goals & Milestones") -> str:
    """Generate VCALENDAR string with VTODO components."""
    now_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Omi//Goal VTODO Exporter//EN",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{escape_ics(cal_name)}",
    ]

    for goal in goals:
        gid = str(goal.get("id"))
        title = str(goal.get("title") or goal.get("name") or f"Goal {gid}").strip()
        goal_type = str(goal.get("goal_type") or "").strip()
        unit = str(goal.get("unit") or "").strip()
        raw_status = str(goal.get("status") or "").strip().lower()
        curr_val = goal.get("current_value")
        target_val = goal.get("target_value")

        # Derive progress & status from real Omi goal fields
        progress = 0
        if goal_type == "boolean":
            if curr_val in (True, 1, "1", "true", "True") or raw_status == "achieved":
                progress = 100
        else:
            try:
                if curr_val is not None and target_val is not None:
                    c_num = float(curr_val)
                    t_num = float(target_val)
                    if t_num > 0:
                        progress = max(0, min(100, int(round((c_num / t_num) * 100))))
                    elif raw_status == "achieved":
                        progress = 100
            except (ValueError, TypeError):
                if raw_status == "achieved":
                    progress = 100

        if raw_status == "achieved" or progress >= 100:
            status = "COMPLETED"
            progress = 100
        elif raw_status == "abandoned":
            status = "CANCELLED"
        elif progress > 0 or raw_status == "focused":
            status = "IN-PROCESS"
        else:
            status = "NEEDS-ACTION"

        # Build descriptive context from real fields
        desc_parts = []
        if goal_type:
            desc_parts.append(f"Type: {goal_type}")
        if curr_val is not None and target_val is not None:
            u_str = f" {unit}" if unit else ""
            desc_parts.append(f"Progress: {curr_val} / {target_val}{u_str}")
        elif unit:
            desc_parts.append(f"Unit: {unit}")
        if raw_status:
            desc_parts.append(f"Omi status: {raw_status}")
        desc = " | ".join(desc_parts)

        lines.append("BEGIN:VTODO")
        lines.append(f"UID:goal-{gid}@omi.me")
        lines.append(f"DTSTAMP:{now_stamp}")
        lines.append(f"SUMMARY:{escape_ics(title)}")
        if desc:
            lines.append(f"DESCRIPTION:{escape_ics(desc)}")
        lines.append(f"PERCENT-COMPLETE:{progress}")
        lines.append(f"STATUS:{status}")

        created_stamp = format_dt(goal.get("created_at"))
        if created_stamp:
            lines.append(f"CREATED:{created_stamp}")

        if status == "COMPLETED":
            completed_stamp = format_dt(goal.get("updated_at")) or now_stamp
            lines.append(f"COMPLETED:{completed_stamp}")

        lines.append("END:VTODO")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi goals JSON export into an RFC 5545 VTODO task feed (.ics)."
    )
    parser.add_argument("inputs", nargs="*", help="Input JSON files or '-' for stdin")
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Destination .ics file (defaults to stdout)",
    )
    parser.add_argument(
        "--cal-name",
        default="Omi Goals & Milestones",
        help="Custom calendar name header",
    )
    args = parser.parse_args()

    if not args.inputs:
        parser.print_help()
        sys.exit(1)

    all_goals: List[Dict[str, Any]] = []
    try:
        for src in args.inputs:
            if str(src) == "-":
                content = sys.stdin.read()
                all_goals.extend(extract_goals(content, "<stdin>"))
            else:
                p = Path(src)
                content = p.read_text(encoding="utf-8")
                all_goals.extend(extract_goals(content, str(p)))
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    ics_output = generate_vcalendar(all_goals, args.cal_name)

    if args.output != "-":
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(ics_output, encoding="utf-8")
        print(f"Generated VTODO task feed with {len(all_goals)} goal(s) at {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(ics_output)


if __name__ == "__main__":
    main()
