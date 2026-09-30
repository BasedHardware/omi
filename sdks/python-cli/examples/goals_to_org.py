"""Convert an Omi goal export to an Org-mode file with progress cookies and tracking drawers.

See goals_org.md for the full recipe.

Usage:
    omi --json goal list > goals.json
    python goals_to_org.py goals.json omi_goals.org --utc-offset +09:00
    omi --json goal list | python goals_to_org.py - omi_goals.org
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
DONE_WORDS = {"true", "yes", "1", "done", "completed"}
ZWSP = "\u200b"  # zero-width space, Org's documented escape character


def one_line(value) -> str:
    """Render one exported field as single-line text."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(value.split())


def heading_text(value) -> str:
    """Escape text so it cannot be misparsed as Org syntax inside a heading."""
    text = one_line(value) or "(no title)"
    if text.startswith("[#"):
        text = ZWSP + text  # would otherwise become a priority cookie
    text = re.sub(r"([<\[])(?=\d{4}-\d{2}-\d{2})", "\\1" + ZWSP, text)  # no stray agenda timestamps
    if re.search(r":[\w@#%:]+:\s*$", text):
        text = text.rstrip() + ZWSP  # would otherwise become heading tags
    return text


def parse_offset(text: str | None) -> timezone:
    match = re.fullmatch(r"([+-])(\d{2}):(\d{2})", text or "")
    if not match:
        raise argparse.ArgumentTypeError("use +HH:MM or -HH:MM between -14:00 and +14:00")
    hours, minutes = int(match.group(2)), int(match.group(3))
    if hours > 14 or minutes > 59 or (hours == 14 and minutes > 0):
        raise argparse.ArgumentTypeError("use +HH:MM or -HH:MM between -14:00 and +14:00")
    delta = timedelta(hours=hours, minutes=minutes)
    return timezone(delta if match.group(1) == "+" else -delta)


def local_time(value, zone: timezone) -> datetime | None:
    """Parse an ISO-8601 timestamp into local wall-clock time, or None if unusable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(zone)


def org_stamp(dt: datetime, active: bool = False) -> str:
    body = f"{dt:%Y-%m-%d} {WEEKDAYS[dt.weekday()]} {dt:%H:%M}"
    return f"<{body}>" if active else f"[{body}]"


def format_num(val: float | int | None) -> str:
    if val is None:
        return "0"
    if isinstance(val, (int, float)):
        if math.isnan(val) or math.isinf(val):
            return "0"
        if isinstance(val, int) or val.is_integer():
            return str(int(val))
        return f"{val:.2f}".rstrip("0").rstrip(".")
    return str(val)


def is_qualitative_goal(goal: dict) -> bool:
    """Return True if goal is qualitative (no user metric defined or degenerate bounds)."""
    if "metric" in goal and goal.get("metric") is None:
        return True
    target = goal.get("target_value")
    min_v = goal.get("min_value")
    max_v = goal.get("max_value")
    try:
        target_f = float(target) if target is not None else 0.0
        min_f = float(min_v) if min_v is not None else 0.0
        max_f = float(max_v) if max_v is not None else target_f
    except (ValueError, TypeError):
        return True

    # Degenerate bounds: max <= min, or zero/negative target without explicit unit
    if max_f <= min_f:
        return True
    if target_f <= 0 and not goal.get("unit"):
        return True
    return False


def compute_progress(goal: dict) -> tuple[int | None, str, str]:
    """Return (percentage, progress_cookie, 20_cell_bar). For qualitative goals, return (None, '', '')."""
    if is_qualitative_goal(goal):
        return None, "", ""

    goal_type = str(goal.get("goal_type", "numeric")).lower()
    curr = goal.get("current_value")
    target = goal.get("target_value")
    min_v = goal.get("min_value", 0.0)
    max_v = goal.get("max_value", target or 1.0)

    try:
        curr_f = float(curr) if curr is not None else 0.0
    except (ValueError, TypeError):
        curr_f = 0.0

    try:
        target_f = float(target) if target is not None else 1.0
    except (ValueError, TypeError):
        target_f = 1.0

    try:
        min_f = float(min_v) if min_v is not None else 0.0
    except (ValueError, TypeError):
        min_f = 0.0

    if goal_type == "boolean":
        is_true = curr_f >= 1.0 or bool(goal.get("completed")) or str(curr).lower() in DONE_WORDS
        pct = 100 if is_true else 0
        cookie = f"[{pct}%] [{'1/1' if is_true else '0/1'}]"
    else:
        span = target_f - min_f
        if span > 0:
            ratio = (curr_f - min_f) / span
            pct = max(0, min(100, int(round(ratio * 100))))
        else:
            pct = 100 if curr_f >= target_f else 0
        cookie = f"[{pct}%] [{format_num(curr_f)}/{format_num(target_f)}]"

    filled = max(0, min(20, int(round(pct / 5))))
    bar = "[" + "=" * filled + "-" * (20 - filled) + f"] {pct}%"
    return pct, cookie, bar


def is_goal_done(goal: dict, pct: int | None) -> bool:
    is_active = goal.get("is_active")
    if is_active is False or str(is_active).lower() in ("false", "0", "no"):
        return True
    status = str(goal.get("status", "")).lower()
    if status in ("completed", "done", "achieved", "inactive", "closed", "abandoned"):
        return True
    if pct is not None and pct >= 100:
        return True
    return False


def extract_goals(data) -> list[dict] | None:
    """Unwrap goals from bare lists, wrapped envelopes, or single goal dictionaries."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("goals", "items", "data"):
            if isinstance(data.get(key), list):
                return data[key]
        if "title" in data or "id" in data or "goal_id" in data:
            return [data]
    return None


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', "", name)
    cleaned = "_".join(cleaned.split()).strip("._")
    return cleaned[:80] or "goal"


def render_goal_entry(goal: dict, zone: timezone, level: int = 1) -> list[str]:
    stars = "*" * level
    pct, cookie, bar = compute_progress(goal)
    done = is_goal_done(goal, pct)
    title = heading_text(goal.get("title") or goal.get("description"))

    cookie_str = f" {cookie}" if cookie else ""
    lines = [f"{stars} {'DONE' if done else 'TODO'} {title}{cookie_str}"]

    # Planning line: DEADLINE from horizon_at, CLOSED from ended_at / updated_at
    deadline_dt = local_time(goal.get("horizon_at"), zone)
    planning = []
    if done:
        closed_dt = local_time(goal.get("ended_at") or goal.get("updated_at"), zone)
        if closed_dt:
            planning.append("CLOSED: " + org_stamp(closed_dt, active=False))
    if deadline_dt:
        planning.append("DEADLINE: " + org_stamp(deadline_dt, active=True))
    if planning:
        lines.append(" ".join(planning))

    # Properties
    lines.append(":PROPERTIES:")
    omi_id = one_line(goal.get("id") or goal.get("goal_id"))
    if omi_id:
        lines.append(f":OMI_ID: {omi_id}")
    lines.append(f":GOAL_TYPE: {one_line(goal.get('goal_type', 'scale' if is_qualitative_goal(goal) else 'numeric'))}")
    if not is_qualitative_goal(goal):
        lines.append(f":CURRENT_VALUE: {format_num(goal.get('current_value', 0))}")
        lines.append(f":TARGET_VALUE: {format_num(goal.get('target_value', 0))}")
        lines.append(f":MIN_VALUE: {format_num(goal.get('min_value', 0))}")
        lines.append(f":MAX_VALUE: {format_num(goal.get('max_value', 0))}")
    unit = one_line(goal.get("unit"))
    if unit:
        lines.append(f":UNIT: {unit}")
    lines.append(f":IS_ACTIVE: {str(goal.get('is_active', True))}")
    status = one_line(goal.get("status"))
    if status:
        lines.append(f":STATUS: {status}")

    created = local_time(goal.get("created_at"), zone)
    if created:
        lines.append(f":CREATED: {org_stamp(created, active=False)}")
    updated = local_time(goal.get("updated_at"), zone)
    if updated:
        lines.append(f":UPDATED: {org_stamp(updated, active=False)}")
    ended = local_time(goal.get("ended_at"), zone)
    if ended:
        lines.append(f":ENDED: {org_stamp(ended, active=False)}")
    lines.append(":END:")

    # Body with progress bar and details
    if bar:
        lines.append(f"Progress: {bar}")
    if unit:
        lines.append(f"Unit: {unit}")

    desired_outcome = one_line(goal.get("desired_outcome"))
    if desired_outcome:
        lines.append(f"\nDesired Outcome: {desired_outcome}")

    why = one_line(goal.get("why_it_matters"))
    if why:
        lines.append(f"\nWhy it matters: {why}")

    criteria = goal.get("success_criteria")
    if isinstance(criteria, list) and criteria:
        lines.append("\nSuccess Criteria:")
        for c in criteria:
            c_text = one_line(c)
            if c_text:
                lines.append(f"- [ ] {c_text}")

    return lines


def write_file_exclusive(path: Path, content: str, force: bool = False) -> None:
    payload = content.encode("utf-8")
    if force:
        path.unlink(missing_ok=True)
    try:
        out = path.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {path}") from None
    try:
        with out:
            out.write(payload)
    except OSError:
        path.unlink(missing_ok=True)
        raise


def convert(
    source: str | Path,
    destination: str | Path | None = None,
    zone: timezone | None = None,
    group_by: str = "none",
    active_only: bool = False,
    goal_types: list[str] | None = None,
    output_dir: str | Path | None = None,
    force: bool = False,
) -> tuple[int, int]:
    """Convert goals JSON into Org format. Returns (total_written, completed_count)."""
    if zone is None:
        zone = datetime.now().astimezone().tzinfo or timezone.utc

    # Read JSON source (supports stdin via "-")
    if str(source) == "-":
        raw_bytes = sys.stdin.buffer.read()
    else:
        raw_bytes = Path(source).read_bytes()

    text = raw_bytes.decode("utf-8-sig")
    data = json.loads(text)
    items = extract_goals(data)
    if items is None or not isinstance(items, list):
        raise ValueError("Expected a JSON array of goals or an envelope containing goals")

    filtered = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each goal must be a JSON object")

        if active_only:
            is_active = item.get("is_active", True)
            if is_active is False or str(is_active).lower() in ("false", "0", "no"):
                continue

        if goal_types:
            g_type = str(item.get("goal_type", "")).lower()
            if g_type not in goal_types:
                continue

        filtered.append(item)

    # Multi-file output mode
    if output_dir:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        used_names: dict[str, int] = {}
        written_count = 0
        done_count = 0

        for goal in filtered:
            pct, _, _ = compute_progress(goal)
            done = is_goal_done(goal, pct)
            if done:
                done_count += 1

            base_name = sanitize_filename(goal.get("title") or goal.get("id") or "goal")
            count = used_names.get(base_name, 0)
            used_names[base_name] = count + 1
            filename = f"{base_name}.org" if count == 0 else f"{base_name}-{count + 1}.org"

            goal_lines = [
                "# -*- mode: org; coding: utf-8 -*-",
                f"#+TITLE: {heading_text(goal.get('title'))}",
                "",
            ]
            goal_lines.extend(render_goal_entry(goal, zone, level=1))
            write_file_exclusive(out_dir / filename, "\n".join(goal_lines) + "\n", force=force)
            written_count += 1

        return written_count, done_count

    # Single-file output mode
    if not destination:
        raise ValueError("Destination file path is required when --output-dir is not specified")

    lines = [
        "# -*- mode: org; coding: utf-8 -*-",
        "#+TITLE: Omi Goals",
        "",
    ]

    done_count = 0
    if group_by == "status":
        open_goals = []
        done_goals = []
        for g in filtered:
            pct, _, _ = compute_progress(g)
            if is_goal_done(g, pct):
                done_goals.append(g)
                done_count += 1
            else:
                open_goals.append(g)

        if open_goals:
            lines.append(f"* Active Goals [{len(open_goals)}]")
            for g in open_goals:
                lines.extend(render_goal_entry(g, zone, level=2))
                lines.append("")

        if done_goals:
            lines.append(f"* Completed / Inactive Goals [{len(done_goals)}]")
            for g in done_goals:
                lines.extend(render_goal_entry(g, zone, level=2))
                lines.append("")

    elif group_by == "type":
        types_map: dict[str, list[dict]] = {}
        for g in filtered:
            g_type = str(g.get("goal_type", "numeric")).lower()
            types_map.setdefault(g_type, []).append(g)
            pct, _, _ = compute_progress(g)
            if is_goal_done(g, pct):
                done_count += 1

        for g_type, g_list in sorted(types_map.items()):
            lines.append(f"* {g_type.capitalize()} Goals [{len(g_list)}]")
            for g in g_list:
                lines.extend(render_goal_entry(g, zone, level=2))
                lines.append("")

    else:  # none
        for g in filtered:
            pct, _, _ = compute_progress(g)
            if is_goal_done(g, pct):
                done_count += 1
            lines.extend(render_goal_entry(g, zone, level=1))
            lines.append("")

    content = "\n".join(lines).strip() + "\n"
    write_file_exclusive(Path(destination), content, force=force)
    return len(filtered), done_count


def main():
    parser = argparse.ArgumentParser(description="Convert an Omi goal export to an Org-mode file.")
    parser.add_argument("source", help="JSON file or '-' for stdin")
    parser.add_argument("destination", nargs="?", default=None, help="Output .org file (when not using --output-dir)")
    parser.add_argument(
        "--utc-offset", type=parse_offset, default=None, help="Offset like +09:00; default: local time zone"
    )
    parser.add_argument(
        "--group-by", choices=["none", "status", "type"], default="none", help="Group goals into top-level Org sections"
    )
    parser.add_argument("--active-only", action="store_true", help="Filter out inactive or archived goals")
    parser.add_argument(
        "--goal-type", type=str, default=None, help="Filter by goal types (comma-separated: numeric,scale,boolean)"
    )
    parser.add_argument(
        "--output-dir", type=str, default=None, help="Export each goal to an individual .org file in this directory"
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing destination files")

    args = parser.parse_args()
    zone = args.utc_offset or datetime.now().astimezone().tzinfo or timezone.utc

    goal_types = [t.strip().lower() for t in args.goal_type.split(",")] if args.goal_type else None

    try:
        written, completed = convert(
            source=args.source,
            destination=args.destination,
            zone=zone,
            group_by=args.group_by,
            active_only=args.active_only,
            goal_types=goal_types,
            output_dir=args.output_dir,
            force=args.force,
        )
    except (OSError, ValueError) as exc:
        sys.exit(f"Org export failed: {exc}")

    print(f"{written} goal(s) exported ({completed} completed/inactive).")


if __name__ == "__main__":
    main()
