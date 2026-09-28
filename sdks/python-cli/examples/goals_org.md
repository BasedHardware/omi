# Track goals and progress metrics in Org mode

Use this recipe to work through Omi's tracked goals and progress metrics in Emacs Org mode, or in an Org app such as Orgzly or beorg. It reads a saved JSON export, makes no network requests, and writes structured `.org` files: every goal becomes a `TODO` or `DONE` heading with Org progress cookies (e.g. `[50%] [5/10]`), a visual progress bar, and metadata properties (`:OMI_ID:`, `:GOAL_TYPE:`, `:CURRENT_VALUE:`, `:TARGET_VALUE:`, `:UNIT:`, `:IS_ACTIVE:`). You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export tracked goals:

```sh
omi --json goal list --limit 100 --include-inactive > goals.json
```

Or pipe directly into the converter:

```sh
omi --json goal list | python goals_to_org.py -
```

Check that the command succeeded before converting the file. Add `--active-only` to export only active in-progress goals.

Save the following as `goals_to_org.py` (the same script is kept next to this recipe as [`goals_to_org.py`](goals_to_org.py) and covered by `tests/test_goals_to_org.py`):

```python
"""Convert Omi tracked goals JSON exports to Emacs Org-mode outline notes.

See goals_org.md for the full recipe.

Usage:
    # Pipe directly from omi CLI
    omi --json goal list | python goals_to_org.py -

    # Export to a specific Org-mode file
    python goals_to_org.py goals.json omi_goals.org --utc-offset +09:00

    # Export into status-specific or type-specific Org files in a directory
    python goals_to_org.py goals.json --output-dir ./org_goals/ --group-by status

    # Filter active numeric goals only
    python goals_to_org.py goals.json --active-only --goal-type numeric
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple, Union

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
ZWSP = "​"  # zero-width space, Org's documented escape character

GOAL_TYPE_META: Dict[str, Dict[str, str]] = {
    "numeric": {"label": "Numeric Goals", "emoji": "📊"},
    "scale": {"label": "Scale Goals", "emoji": "⚖️"},
    "boolean": {"label": "Boolean Goals", "emoji": "☑️"},
}


def one_line(value: Any) -> str:
    """Render one exported field as single-line text safely coercing non-strings."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(value.split())


def heading_text(value: Any) -> str:
    """Keep goal title from being parsed as Org syntax inside a heading."""
    text = one_line(value) or "(Untitled goal)"
    if text.startswith("[#"):
        text = ZWSP + text  # prevent priority cookie
    text = re.sub(r"([<\[])(?=\d{4}-\d{2}-\d{2})", "\\1" + ZWSP, text)  # prevent stray agenda timestamps
    if re.search(r":[\w@#%:]+:\s*$", text):
        text = text.rstrip() + ZWSP  # prevent stray heading tags
    return text


def clean_org_tag(tag: Any) -> str:
    """Sanitize arbitrary strings into valid Org-mode tags."""
    if not tag:
        return ""
    clean = re.sub(r"[^\w@#%]", "_", str(tag)).strip("_")
    return clean


def parse_offset(text: Optional[str]) -> timezone:
    """Parse time zone offset in +HH:MM or -HH:MM format."""
    match = re.fullmatch(r"([+-])(\d{2}):(\d{2})", text or "")
    if not match or int(match.group(2)) > 14 or int(match.group(3)) > 59:
        raise argparse.ArgumentTypeError("use +HH:MM or -HH:MM between -14:00 and +14:00")
    delta = timedelta(hours=int(match.group(2)), minutes=int(match.group(3)))
    if delta > timedelta(hours=14):
        raise argparse.ArgumentTypeError("use +HH:MM or -HH:MM between -14:00 and +14:00")
    return timezone(delta if match.group(1) == "+" else -delta)


def local_time(value: Any, zone: timezone) -> Optional[datetime]:
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
    """Format a datetime into an Org inactive [YYYY-MM-DD Day HH:MM] or active timestamp."""
    body = f"{dt:%Y-%m-%d} {WEEKDAYS[dt.weekday()]} {dt:%H:%M}"
    return f"<{body}>" if active else f"[{body}]"


def extract_goals(data: Any) -> List[Dict[str, Any]]:
    """Unwrap goal records from bare arrays, wrapped envelopes, or single objects.

    Supports:
    - Bare arrays: [ {...}, {...} ]
    - Wrapped dicts: {"goals": [...]}, {"items": [...]}, {"data": [...]}
    - Single goal dict: { "id": "...", "title": "..." }

    Ensures that empty envelopes like {"goals": []} return an empty list
    without creating phantom untitled goals.
    """
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("goals", "items", "data"):
            val = data.get(key)
            if isinstance(val, list):
                return [item for item in val if isinstance(item, dict)]
        if any(key in data for key in ("title", "goal_type", "target_value", "id")):
            return [data]
        return []
    return []


def is_goal_completed(goal: Dict[str, Any]) -> bool:
    """Determine whether a goal has reached completion."""
    if not goal.get("is_active", True):
        return True
    try:
        current = float(goal.get("current_value", 0))
        target = float(goal.get("target_value", 0))
        return current >= target
    except (TypeError, ValueError):
        return False


def calculate_progress_pct(goal: Dict[str, Any]) -> float:
    """Compute normalized progress percentage between 0.0 and 100.0."""
    try:
        current = float(goal.get("current_value", 0))
        target = float(goal.get("target_value", 0))
        min_val = float(goal.get("min_value", 0))

        if math.isclose(target, min_val):
            return 100.0 if current >= target else 0.0

        pct = ((current - min_val) / (target - min_val)) * 100.0
        return max(0.0, min(100.0, pct))
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def render_ascii_progress_bar(pct: float, width: int = 20) -> str:
    """Render a clean text-based progress bar."""
    filled_len = int(round(width * (pct / 100.0)))
    if filled_len >= width:
        bar = "=" * width
    elif filled_len > 0:
        bar = "=" * (filled_len - 1) + ">" + " " * (width - filled_len)
    else:
        bar = " " * width
    return f"[{bar}] {pct:.1f}%"


def filter_goals(
    items: List[Dict[str, Any]],
    goal_type_filter: Optional[str] = None,
    active_only: bool = False,
) -> List[Dict[str, Any]]:
    """Filter goals by goal_type and active status."""
    filtered = items

    if active_only:
        filtered = [it for it in filtered if bool(it.get("is_active", True))]

    if goal_type_filter:
        target_types = {t.strip().lower() for t in goal_type_filter.split(",") if t.strip()}
        filtered = [
            it for it in filtered
            if str(it.get("goal_type") or "").strip().lower() in target_types
        ]

    return filtered


def format_goal_entry(goal: Dict[str, Any], zone: timezone, level: int = 1) -> str:
    """Format a single goal as an Org-mode subtree node."""
    goal_id = goal.get("id") or "unknown"
    title = str(goal.get("title") or "").strip() or "(Untitled Goal)"
    goal_type = str(goal.get("goal_type") or "").strip().lower() or "scale"
    is_active = bool(goal.get("is_active", True))
    unit = str(goal.get("unit") or "").strip()

    current_val = goal.get("current_value", 0)
    target_val = goal.get("target_value", 0)
    min_val = goal.get("min_value", 0)
    max_val = goal.get("max_value", 0)

    completed = is_goal_completed(goal)
    pct = calculate_progress_pct(goal)

    todo_state = "DONE" if completed else "TODO"
    prefix = "*" * level

    # Org progress cookies in heading: e.g. [50%] [5/10]
    curr_fmt = f"{current_val:g}" if isinstance(current_val, (int, float)) else str(current_val)
    targ_fmt = f"{target_val:g}" if isinstance(target_val, (int, float)) else str(target_val)
    cookie = f" [{pct:.0f}%] [{curr_fmt}/{targ_fmt}]" if goal_type != "boolean" else f" [{pct:.0f}%]"

    tag = clean_org_tag(goal_type)
    tag_part = f" :{tag}:" if tag else ""

    lines = [f"{prefix} {todo_state} {heading_text(title)}{cookie}{tag_part}"]

    # Properties Drawer
    lines.append(":PROPERTIES:")
    lines.append(f":OMI_ID: {one_line(goal_id)}")
    lines.append(f":GOAL_TYPE: {one_line(goal_type)}")
    lines.append(f":CURRENT_VALUE: {curr_fmt}")
    lines.append(f":TARGET_VALUE: {targ_fmt}")
    if min_val is not None:
        lines.append(f":MIN_VALUE: {min_val:g}" if isinstance(min_val, (int, float)) else f":MIN_VALUE: {min_val}")
    if max_val is not None:
        lines.append(f":MAX_VALUE: {max_val:g}" if isinstance(max_val, (int, float)) else f":MAX_VALUE: {max_val}")
    if unit:
        lines.append(f":UNIT: {one_line(unit)}")
    lines.append(f":IS_ACTIVE: {'true' if is_active else 'false'}")

    created_dt = local_time(goal.get("created_at"), zone)
    if created_dt:
        lines.append(f":DATE: {org_stamp(created_dt, active=False)}")
        lines.append(f":CREATED: {org_stamp(created_dt, active=False)}")

    updated_dt = local_time(goal.get("updated_at"), zone)
    if updated_dt:
        lines.append(f":UPDATED: {org_stamp(updated_dt, active=False)}")

    lines.append(":END:")

    # Body section with visual progress indicator and metric detail
    unit_suffix = f" {unit}" if unit else ""
    bar = render_ascii_progress_bar(pct, width=20)
    lines.append(f"- Progress: {bar} ({curr_fmt} / {targ_fmt}{unit_suffix})")
    lines.append(f"- State: {'Active' if is_active else 'Archived / Inactive'}")

    description = str(goal.get("description") or "").strip()
    if description:
        lines.append("")
        lines.append(description)

    return "\n".join(lines)


def export_single_file(
    goals: List[Dict[str, Any]],
    destination: Path,
    zone: timezone,
    group_by: str = "status",
    title: str = "Omi Goals & Metrics Tracking",
    overwrite: bool = False,
) -> int:
    """Export all goals into one consolidated Org-mode file."""
    now_dt = datetime.now(zone)
    lines = [
        "# -*- mode: org; coding: utf-8 -*-",
        f"#+TITLE: {title}",
        "#+AUTHOR: Omi",
        f"#+DATE: {org_stamp(now_dt, active=False)}",
        "",
    ]

    if not goals:
        lines.append("* Empty Goals Registry")
        lines.append("No tracked goals found matching criteria.")
        lines.append("")
    elif group_by == "status":
        active_goals = [g for g in goals if bool(g.get("is_active", True)) and not is_goal_completed(g)]
        done_goals = [g for g in goals if not bool(g.get("is_active", True)) or is_goal_completed(g)]

        if active_goals:
            lines.append("* 🎯 Active Goals :active:")
            for g in active_goals:
                lines.append(format_goal_entry(g, zone, level=2))
            lines.append("")

        if done_goals:
            lines.append("* ✅ Completed & Archived Goals :completed:")
            for g in done_goals:
                lines.append(format_goal_entry(g, zone, level=2))
            lines.append("")

    elif group_by == "type":
        type_groups: Dict[str, List[Dict[str, Any]]] = {}
        for g in goals:
            t = str(g.get("goal_type") or "").strip().lower() or "scale"
            type_groups.setdefault(t, []).append(g)

        for type_key in sorted(type_groups.keys()):
            group_items = type_groups[type_key]
            meta = GOAL_TYPE_META.get(type_key, {"label": f"{type_key.title()} Goals", "emoji": "🎯"})
            tag = clean_org_tag(type_key)
            lines.append(f"* {meta['emoji']} {meta['label']} :{tag}:")
            for g in group_items:
                lines.append(format_goal_entry(g, zone, level=2))
            lines.append("")

    else:  # group_by == "none"
        for g in goals:
            lines.append(format_goal_entry(g, zone, level=1))
        lines.append("")

    payload = ("\n".join(lines).rstrip() + "\n").encode("utf-8")
    if not overwrite:
        try:
            output = destination.open("xb")
        except FileExistsError:
            raise FileExistsError(f"Refusing to overwrite existing {destination}") from None
    else:
        output = destination.open("wb")

    try:
        with output:
            output.write(payload)
    except OSError:
        destination.unlink(missing_ok=True)
        raise

    return len(goals)


def _sanitize_group_key(group_key: str) -> str:
    """Turn a group key into a filesystem-safe slug."""
    return re.sub(r"[^\w-]", "_", group_key).strip("_") or "goals"


def _allocate_unique_filenames(safe_keys: Dict[str, str]) -> Dict[str, str]:
    """Map every group key to its own <slug>_goals.org filename with deterministic collision handling."""
    natural_names = {f"{safe_key}_goals.org".casefold() for safe_key in safe_keys.values()}
    used_names: Set[str] = set()
    filenames: Dict[str, str] = {}

    for group_key in sorted(safe_keys):
        safe_key = safe_keys[group_key]
        filename = f"{safe_key}_goals.org"
        if filename.casefold() in used_names:
            counter = 2
            while True:
                candidate = f"{safe_key}_{counter}_goals.org"
                folded = candidate.casefold()
                if folded not in used_names and folded not in natural_names:
                    break
                counter += 1
            filename = candidate
        used_names.add(filename.casefold())
        filenames[group_key] = filename

    return filenames


def export_directory(
    goals: List[Dict[str, Any]],
    output_dir: Path,
    zone: timezone,
    group_by: str = "status",
    title_prefix: str = "Omi Goals",
    overwrite: bool = False,
) -> List[Path]:
    """Export goals into individual .org files in output_dir grouped by status or type."""
    output_dir.mkdir(parents=True, exist_ok=True)
    resolved_dir = output_dir.resolve()
    written_files: List[Path] = []

    groups: Dict[str, List[Dict[str, Any]]] = {}
    if group_by == "type":
        for g in goals:
            t = str(g.get("goal_type") or "").strip().lower() or "scale"
            groups.setdefault(t, []).append(g)
    else:
        for g in goals:
            status_key = "completed" if (not bool(g.get("is_active", True)) or is_goal_completed(g)) else "active"
            groups.setdefault(status_key, []).append(g)

    filenames = _allocate_unique_filenames({gk: _sanitize_group_key(gk) for gk in groups})

    for group_key, group_items in sorted(groups.items()):
        filename = filenames[group_key]
        target_path = (output_dir / filename).resolve()

        if not str(target_path).startswith(str(resolved_dir)):
            continue

        doc_title = f"{title_prefix} — {group_key.replace('_', ' ').title()}"
        export_single_file(
            group_items,
            target_path,
            zone,
            group_by="none",
            title=doc_title,
            overwrite=overwrite,
        )
        written_files.append(target_path)

    return written_files


def convert(
    source: Union[str, Path],
    destination: Union[str, Path],
    zone: timezone,
    output_dir: Optional[Union[str, Path]] = None,
    group_by: str = "status",
    goal_type_filter: Optional[str] = None,
    active_only: bool = False,
    overwrite: bool = False,
) -> int:
    """High-level conversion entrypoint."""
    if str(source) == "-":
        stream = getattr(sys.stdin, "buffer", sys.stdin)
        data = stream.read()
        raw_content = data.decode("utf-8-sig") if isinstance(data, bytes) else data
    else:
        source_path = Path(source)
        raw_content = source_path.read_bytes().decode("utf-8-sig")

    if not raw_content.strip():
        items: List[Dict[str, Any]] = []
    else:
        raw_json = json.loads(raw_content)
        items = extract_goals(raw_json)

    filtered = filter_goals(items, goal_type_filter=goal_type_filter, active_only=active_only)

    if output_dir:
        dest_dir = Path(output_dir)
        exported = export_directory(filtered, dest_dir, zone, group_by=group_by, overwrite=overwrite)
        return len(exported)

    dest_path = Path(destination)
    if dest_path.is_dir() or str(destination).endswith(("/", "\\")):
        exported = export_directory(filtered, dest_path, zone, group_by=group_by, overwrite=overwrite)
        return len(exported)

    return export_single_file(filtered, dest_path, zone, group_by=group_by, overwrite=overwrite)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert an Omi goals export to Emacs Org-mode outline notes.")
    parser.add_argument("source", help="JSON from omi --json goal list, or '-' for stdin pipe")
    parser.add_argument("destination", nargs="?", default="omi_goals.org",
                        help="new .org file to create, or directory (default: omi_goals.org)")
    parser.add_argument("--output-dir", help="export individual .org files into this directory")
    parser.add_argument("--group-by", choices=["status", "type", "none"], default="status",
                        help="group goals by 'status' (default: active vs completed), 'type', or 'none'")
    parser.add_argument("--goal-type", help="filter by goal types (comma-separated, e.g. numeric,scale)")
    parser.add_argument("--active-only", action="store_true", help="export active goals only")
    parser.add_argument("--utc-offset", type=parse_offset, default=None,
                        help="format times at this offset (e.g. +09:00); default: computer's local time zone")
    parser.add_argument("--force", action="store_true", help="overwrite existing file(s)")
    args = parser.parse_args()

    zone = args.utc_offset or datetime.now().astimezone().tzinfo
    try:
        count = convert(
            args.source,
            args.destination,
            zone,
            output_dir=args.output_dir,
            group_by=args.group_by,
            goal_type_filter=args.goal_type,
            active_only=args.active_only,
            overwrite=args.force,
        )
        print(f"Successfully exported {count} goal group(s)/file to Org-mode.")
    except (OSError, ValueError) as exc:
        sys.exit(f"Org export failed: {exc}")
```

Run the converter:

```sh
# Export into a single Org-mode master file
python goals_to_org.py goals.json omi_goals.org

# Export status-specific notes into a folder (active_goals.org, completed_goals.org)
python goals_to_org.py goals.json --output-dir ./org_goals/ --group-by status

# Filter active numeric goals only
python goals_to_org.py goals.json omi_active_goals.org --active-only --goal-type numeric
```

## Org-mode Structure & Properties

Each goal is formatted as an Org outline node with dynamic progress cookies and metadata:

```org
* 🎯 Active Goals :active:
** DONE Drink 2L Water Daily [100%] [2/2] :numeric:
:PROPERTIES:
:OMI_ID: goal_001
:GOAL_TYPE: numeric
:CURRENT_VALUE: 2
:TARGET_VALUE: 2
:MIN_VALUE: 0
:MAX_VALUE: 3
:UNIT: liters
:IS_ACTIVE: true
:DATE: [2026-09-28 Mon 07:00]
:CREATED: [2026-09-28 Mon 07:00]
:UPDATED: [2026-09-28 Mon 11:00]
:END:
- Progress: [====================] 100.0% (2 / 2 liters)
- State: Completed

Track daily water consumption with Omi.
```

### Key Capabilities

1. **Native Org TODO/DONE & Progress Tracking**:
   - Computes completion status based on `current_value >= target_value` or `is_active`.
   - Embeds Org progress cookies (`[75%]` and `[1.5/2]`) for instant visibility in Emacs agenda views.
   - Generates clean visual text progress bars (`[=======>      ]`).

2. **Properties Drawer Schema**:
   - Retains full metric telemetry: `:OMI_ID:`, `:GOAL_TYPE:`, `:CURRENT_VALUE:`, `:TARGET_VALUE:`, `:MIN_VALUE:`, `:MAX_VALUE:`, `:UNIT:`, `:IS_ACTIVE:`, `:CREATED:`, `:UPDATED:`.

3. **Grouping & Filtering**:
   - `--group-by status` (default): Separates active in-progress goals from completed/archived milestones.
   - `--group-by type`: Groups by metric category (`numeric`, `scale`, `boolean`).
   - `--group-by none`: Flat outline structure.
   - Filter by type (`--goal-type numeric,scale`) or active state (`--active-only`).

4. **Defensive Parsing & Edge Cases**:
   - Unwraps wrapped payloads (`goals`, `items`, `data`) and single objects.
   - Guards against phantom records on empty lists (`{"goals": []}`).
   - Injects zero-width space (ZWSP `\u200b`) to prevent priority cookie or heading tag syntax conflicts.
