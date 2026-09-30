"""Convert an Omi goals export to Org-mode goal files.

See goals_org.md for the full recipe.

Usage:
    omi --json goal list --include-inactive > goals.json
    python goals_to_org.py goals.json omi_goals.org --utc-offset +09:00
    omi --json goal list | python goals_to_org.py - omi_goals.org
    python goals_to_org.py goals.json "" --output-dir org_goals/
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
ZWSP = "\u200b"  # zero-width space, Org's documented escape character
BAR_WIDTH = 20
GOAL_TYPES = ("numeric", "scale", "boolean")


def one_line(value):
    """Render one exported field as single-line text.

    The dev API is loosely typed, so a field can arrive as a non-string; anything
    non-null is coerced rather than rejected, so one odd row cannot break the file.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(value.split())


def heading_text(value):
    """Keep a goal title from being parsed as Org syntax inside a heading."""
    text = one_line(value) or "(untitled goal)"
    if text.startswith("[#"):
        text = ZWSP + text  # would otherwise become a priority cookie
    text = re.sub(r"([<\[])(?=\d{4}-\d{2}-\d{2})", "\\1" + ZWSP, text)  # no stray agenda timestamps
    if re.search(r":[\w@#%:]+:\s*$", text):
        text = text.rstrip() + ZWSP  # would otherwise become heading tags
    return text


def parse_offset(text):
    match = re.fullmatch(r"([+-])(\d{2}):(\d{2})", text or "")
    if not match or int(match.group(2)) > 14 or int(match.group(3)) > 59:
        raise argparse.ArgumentTypeError("use +HH:MM or -HH:MM between -14:00 and +14:00")
    delta = timedelta(hours=int(match.group(2)), minutes=int(match.group(3)))
    if delta > timedelta(hours=14):
        raise argparse.ArgumentTypeError("use +HH:MM or -HH:MM between -14:00 and +14:00")
    return timezone(delta if match.group(1) == "+" else -delta)


def local_time(value, zone):
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


def org_stamp(dt, active):
    body = f"{dt:%Y-%m-%d} {WEEKDAYS[dt.weekday()]} {dt:%H:%M}"
    return f"<{body}>" if active else f"[{body}]"


def extract_goals(data):
    """Unwrap goals from bare lists or wrapped envelope dictionaries.

    Accepts the documented wrappers (goals, items, data), a bare list, and a single
    goal object (the CLI can emit one goal directly for get-goal calls). An empty
    list is a valid zero-goal export, so wrappers are checked before giving up.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("goals", "items", "data"):
            if isinstance(data.get(key), list):
                return data[key]
        if "goal_type" in data or ("id" in data and "title" in data):
            return [data]
    return None


def _as_float(value):
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _fmt_num(value):
    """5.0 -> 5, 2.5 -> 2.5 (cookie and drawer values stay human-friendly)."""
    if value is None:
        return None
    return str(int(value)) if value == int(value) else str(value)


def goal_fraction(goal):
    """0..1 progress for a metric goal, or None for qualitative goals with no usable metrics."""
    goal_type = str(goal.get("goal_type") or "scale").strip().lower()
    current = _as_float(goal.get("current_value"))
    target = _as_float(goal.get("target_value"))
    minv = _as_float(goal.get("min_value"))
    maxv = _as_float(goal.get("max_value"))
    if goal_type == "boolean":
        return 1.0 if (current or 0.0) >= 1.0 else 0.0
    if current is None or target is None:
        return None
    if maxv is not None and minv is not None and maxv > minv:
        fraction = (current - minv) / (maxv - minv)
    elif target > 0:
        fraction = current / target
    else:
        return None
    return min(1.0, max(0.0, fraction))


def is_done_goal(goal):
    if goal.get("is_active") is False:
        return True
    fraction = goal_fraction(goal)
    return fraction is not None and fraction >= 1.0


def progress_bar(fraction):
    """Render ``[=========>          ] 50.0%`` over a 20-cell bar, or None without metrics."""
    if fraction is None:
        return None
    filled = int(round(fraction * BAR_WIDTH))
    if filled <= 0:
        cells = ">" + " " * (BAR_WIDTH - 1)
    elif filled >= BAR_WIDTH:
        cells = "=" * (BAR_WIDTH - 1) + ">"
    else:
        cells = "=" * (filled - 1) + ">" + " " * (BAR_WIDTH - filled)
    return f"[{cells}] {fraction * 100:.1f}%"


def _cookie(goal, fraction):
    """Progress cookie: [50%] plus [current/target] when both metrics are present."""
    if fraction is None:
        return ""
    cookie = f"[{round(fraction * 100)}%]"
    current = _fmt_num(_as_float(goal.get("current_value")))
    target = _fmt_num(_as_float(goal.get("target_value")))
    if current is not None and target is not None:
        cookie += f" [{current}/{target}]"
    return f" {cookie}"


def _slug(title):
    slug = re.sub(r"[^a-z0-9-]+", "-", (title or "").lower()).strip("-")
    return slug[:40] or "goal"


def goal_output_name(goal, used):
    """Deterministic filename; collisions append -2, -3, ... in sort order."""
    base = _slug(goal.get("title")) or f"goal-{one_line(goal.get('id')) or 'untitled'}"
    name, n = base, 2
    while name in used:
        name = f"{base}-{n}"
        n += 1
    used.add(name)
    return f"{name}.org"


def group_key(goal, group_by):
    if group_by == "status":
        return "Active" if goal.get("is_active") is not False else "Completed & archived"
    if group_by == "type":
        return str(goal.get("goal_type") or "scale").strip().lower()
    return None


def render_goal(goal, zone, level):
    fraction = goal_fraction(goal)
    done = is_done_goal(goal)
    title = heading_text(goal.get("title"))
    cookie = _cookie(goal, fraction)
    goal_type = one_line(goal.get("goal_type")) or "scale"
    lines = [" " * 2 * level + f"* {'DONE' if done else 'TODO'} {title}{cookie} :{goal_type}:"]
    bar = progress_bar(fraction)
    lines.append(f"- Progress: {bar}" if bar else "- Progress: n/a (no metrics)")
    lines.append(":PROPERTIES:")
    for key, value in (
        ("OMI_ID", one_line(goal.get("id"))),
        ("GOAL_TYPE", goal_type),
        ("CURRENT_VALUE", _fmt_num(_as_float(goal.get("current_value")))),
        ("TARGET_VALUE", _fmt_num(_as_float(goal.get("target_value")))),
        ("MIN_VALUE", _fmt_num(_as_float(goal.get("min_value")))),
        ("MAX_VALUE", _fmt_num(_as_float(goal.get("max_value")))),
        ("UNIT", one_line(goal.get("unit"))),
        ("IS_ACTIVE", "true" if goal.get("is_active") is not False else "false"),
    ):
        if value not in (None, ""):
            lines.append(f":{key}: {value}")
    for key, field in (("CREATED", "created_at"), ("UPDATED", "updated_at")):
        stamp = local_time(goal.get(field), zone)
        if stamp is not None:
            lines.append(f":{key}: " + org_stamp(stamp, active=False))
    lines.append(":END:")
    return lines


def select_goals(items, active_only, goal_types):
    wanted = {t.strip().lower() for t in goal_types.split(",") if t.strip()} if goal_types else set()
    out = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each goal must be an object")
        if active_only and item.get("is_active") is False:
            continue
        gtype = str(item.get("goal_type") or "scale").strip().lower()
        if wanted and gtype not in wanted:
            continue
        out.append(item)
    out.sort(
        key=lambda g: (
            g.get("is_active") is False,
            str(g.get("goal_type") or "").lower(),
            one_line(g.get("title")).lower(),
        )
    )
    return out


def build_document(goals, zone, group_by):
    lines = ["# -*- mode: org; coding: utf-8 -*-", "#+TITLE: Omi goals", ""]
    if group_by in ("status", "type") and goals:
        keys = []
        for goal in goals:
            key = group_key(goal, group_by)
            if key not in keys:
                keys.append(key)
        for key in keys:
            lines.append(f"* {key}")
            for goal in goals:
                if group_key(goal, group_by) == key:
                    lines.extend(render_goal(goal, zone, level=1))
                    lines.append("")
    else:
        for goal in goals:
            lines.extend(render_goal(goal, zone, level=0))
            lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def _read_source(source):
    text = Path(source).read_bytes().decode("utf-8-sig") if source != "-" else sys.stdin.read()
    return json.loads(text)


def convert(source, destination, zone, group_by="none", active_only=False, goal_types="", output_dir=None):
    raw = _read_source(source)
    items = extract_goals(raw)
    if items is None:
        raise ValueError("Expected the JSON array from omi --json goal list")
    goals = select_goals(items, active_only, goal_types)

    if output_dir:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        used = set()
        written = 0
        for goal in goals:
            name = goal_output_name(goal, used)
            payload = ("\n".join(build_document([goal], zone, "none")) + "\n").encode("utf-8")
            # Exclusive creation per file; a failed write leaves no partial file.
            try:
                with (out_dir / name).open("xb") as handle:
                    handle.write(payload)
            except OSError:
                (out_dir / name).unlink(missing_ok=True)
                raise
            written += 1
        return written, 0

    lines = build_document(goals, zone, group_by)
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    output_path = Path(destination)
    # Exclusive creation protects an existing file; a failed write leaves no partial file.
    try:
        output = output_path.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {output_path}") from None
    try:
        with output:
            output.write(payload)
    except OSError:
        output_path.unlink(missing_ok=True)
        raise
    done_count = sum(1 for g in goals if is_done_goal(g))
    return len(goals), done_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert an omi goals export to Org-mode.")
    parser.add_argument("source", help="JSON from omi --json goal list, or '-' for stdin")
    parser.add_argument(
        "destination", nargs="?", default="", help="new .org file to create (omit when using --output-dir)"
    )
    parser.add_argument(
        "--output-dir", default=None, help="write one .org file per goal into this directory instead of one master file"
    )
    parser.add_argument(
        "--group-by",
        choices=("none", "status", "type"),
        default="none",
        help="group goals under sections (default: flat)",
    )
    parser.add_argument("--active-only", action="store_true", help="skip completed/archived goals")
    parser.add_argument("--goal-type", default="", help="comma list filter: numeric,scale,boolean (default: all)")
    parser.add_argument(
        "--utc-offset",
        type=parse_offset,
        default=None,
        help="write times at this offset (e.g. +09:00); default: this computer's time zone",
    )
    args = parser.parse_args()
    if bool(args.output_dir) == bool(args.destination):
        parser.error("provide exactly one of destination or --output-dir")
    zone = args.utc_offset or datetime.now().astimezone().tzinfo
    try:
        written, extra = convert(
            args.source,
            args.destination,
            zone,
            group_by=args.group_by,
            active_only=args.active_only,
            goal_types=args.goal_type,
            output_dir=args.output_dir,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        sys.exit(f"Org export failed: {exc}")
    if args.output_dir:
        print(f"{written} goal file(s) written to {args.output_dir}")
    else:
        print(f"{written} goal(s) written, {extra} completed")
