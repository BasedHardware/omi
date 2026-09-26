# Put tracked goals and milestones on your calendar (.ics)

Use this recipe to see your Omi tracked goals, habits, and progress milestones
directly inside **Google Calendar**, **Apple Calendar**, **Outlook**, or
**Thunderbird**. It reads saved JSON exports, makes no network requests, and
writes an RFC 5545 compliant `.ics` calendar file with start and end times,
progress summaries, and unique UIDs. It operates with 100% Python standard
library and writes safely using exclusive file creation (`open("xb")`). You
need Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export your goals (up to 100 per page, including inactive/completed milestones):

```sh
omi --json goal list --limit 100 --include-inactive > goals_0.json
```

Save the following as `goals_to_ics.py`:

```python
#!/usr/bin/env python3
"""Convert Omi goals into an RFC 5545 compliant iCalendar (.ics) timeline file."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from typing import Any, Iterable

EVENT_DURATION = timedelta(minutes=30)


def ics_text(value: Any) -> str:
    """Escape text for an iCalendar property value (RFC 5545 §3.3.11)."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    clean = " ".join(value.split())
    clean = clean.replace("\\", "\\\\")
    clean = clean.replace(";", "\\;")
    clean = clean.replace(",", "\\,")
    clean = clean.replace("\n", "\\n")
    return clean


def fold_line(line: str) -> str:
    """Fold lines longer than 75 octets per RFC 5545 §3.1 without breaking UTF-8 bytes."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    chunks: list[bytes] = []
    current_chunk = bytearray()
    max_len = 75

    for byte in encoded:
        if len(current_chunk) == max_len:
            chunks.append(bytes(current_chunk))
            current_chunk = bytearray(b" ")  # Continuation line starts with space
            max_len = 74  # 75 octets minus leading space
        current_chunk.append(byte)

    if current_chunk:
        chunks.append(bytes(current_chunk))

    return b"\r\n".join(chunks).decode("utf-8")


def parse_time(value: Any) -> datetime | None:
    """Parse ISO-8601 timestamp string into UTC datetime."""
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_bool(value: Any) -> bool:
    """Normalize boolean or string flag."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "active")
    return False


def load(sources: Iterable[str | Path]) -> list[dict[str, Any]]:
    """Load and deduplicate goals across multiple export files."""
    items_by_id: dict[str, dict[str, Any]] = {}
    for source in sources:
        path = Path(source)
        content = path.read_bytes().decode("utf-8-sig")
        data = json.loads(content)
        raw_items = data.get("goals") or data.get("items") or data.get("data") or [data] if isinstance(data, dict) else data
        if not isinstance(raw_items, list):
            raise ValueError(f"{source}: expected JSON array or wrapped object containing goals")
        for item in raw_items:
            if not isinstance(item, dict):
                raise ValueError(f"{source}: each goal must be a JSON object")
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id.strip():
                raise ValueError(f"{source}: goal missing valid string id")
            clean_id = item_id.strip()
            existing = items_by_id.get(clean_id)
            if existing is not None:
                new_dt = parse_time(item.get("updated_at") or item.get("created_at"))
                old_dt = parse_time(existing.get("updated_at") or existing.get("created_at"))
                if new_dt and old_dt:
                    if new_dt > old_dt:
                        items_by_id[clean_id] = item
                elif new_dt and not old_dt:
                    items_by_id[clean_id] = item
            else:
                items_by_id[clean_id] = item
    return list(items_by_id.values())


def make_vevent(g: dict[str, Any], dt_stamp_str: str) -> list[str]:
    """Build VEVENT lines for a single goal."""
    gid = g["id"].strip()
    title = str(g.get("title") or "(untitled goal)").strip()
    gtype = str(g.get("goal_type") or "qualitative").strip()
    is_act = to_bool(g.get("is_active", True))
    status_label = "ACTIVE" if is_act else "COMPLETED"

    event_dt = parse_time(g.get("updated_at")) or parse_time(g.get("created_at")) or datetime.now(timezone.utc)
    start_str = event_dt.strftime("%Y%m%dT%H%M%SZ")
    end_str = (event_dt + EVENT_DURATION).strftime("%Y%m%dT%H%M%SZ")

    cur = g.get("current_value")
    tgt = g.get("target_value")
    unit = str(g.get("unit") or "").strip()

    progress_summary = ""
    if tgt is not None and isinstance(tgt, (int, float)) and tgt > 0 and cur is not None and isinstance(cur, (int, float)):
        pct = (cur / tgt) * 100.0
        progress_summary = f" - Progress: {cur:g}/{tgt:g} {unit} ({pct:.0f}%)"
    elif cur is not None and isinstance(cur, (int, float)):
        progress_summary = f" - Current: {cur:g} {unit}"

    summary_text = f"Goal [{status_label}]: {title}{progress_summary}"
    desc_lines = [
        f"Goal: {title}",
        f"Status: {status_label}",
        f"Type: {gtype}",
    ]
    if cur is not None:
        desc_lines.append(f"Current Value: {cur} {unit}".strip())
    if tgt is not None:
        desc_lines.append(f"Target Value: {tgt} {unit}".strip())
    desc_lines.append(f"Omi Goal ID: {gid}")
    desc_text = "\n".join(desc_lines)

    lines = [
        "BEGIN:VEVENT",
        f"UID:omi-goal-{gid}@omi.me",
        f"DTSTAMP:{dt_stamp_str}",
        f"DTSTART:{start_str}",
        f"DTEND:{end_str}",
        fold_line(f"SUMMARY:{ics_text(summary_text)}"),
        fold_line(f"DESCRIPTION:{ics_text(desc_text)}"),
        f"STATUS:{'CONFIRMED' if is_act else 'CANCELLED'}",
        "END:VEVENT",
    ]
    return lines


def build_ics(goals: list[dict[str, Any]]) -> str:
    """Build complete VCALENDAR content."""
    dt_stamp_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Omi//Goal Tracker//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Omi Goals",
    ]
    for g in goals:
        lines.extend(make_vevent(g, dt_stamp_str))
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def convert(sources: list[str], output_path: str | Path) -> None:
    """Convert goals export into an iCalendar file exclusively."""
    goals = load(sources)
    ics_content = build_ics(goals)

    dest = Path(output_path)
    try:
        out = dest.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {dest}") from None
    try:
        with out:
            out.write(ics_content.encode("utf-8"))
    except OSError:
        dest.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", help="Destination .ics file path")
    parser.add_argument("inputs", nargs="+", help="Input goal JSON export files")
    args = parser.parse_args(argv)

    try:
        convert(args.inputs, args.output)
        print(f"Goals iCalendar file written to {args.output}")
        return 0
    except Exception as exc:
        sys.exit(f"Failed to generate iCalendar file: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
```

Run the converter:

```sh
python goals_to_ics.py goals.ics goals_0.json
```

Import `goals.ics` into your calendar application:
- **Google Calendar**: Settings → Import & Export → Import.
- **Apple Calendar**: File → Import → select `goals.ics`.
- **Outlook**: Add Calendar → Upload from file.

Each goal appears as an event with its title, current progress, target, and
completion status, with folded lines conforming to RFC 5545 line limits.
