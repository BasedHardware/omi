import json
import os
import sys
from pathlib import Path
from datetime import datetime


def format_ical_datetime(dt_str):
    if not dt_str:
        return None
    try:
        clean = dt_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        return dt.strftime("%Y%m%dT%H%M%SZ")
    except Exception:
        return None


def convert(source, destination):
    raw = Path(source).read_bytes()
    data = json.loads(raw)
    items = data if isinstance(data, list) else data.get("action_items", data.get("items", []))
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json action-item list")

    dest = Path(destination)
    if dest.exists():
        raise FileExistsError(f"Destination already exists: {dest}")

    tmp = dest.with_suffix(dest.suffix + ".partial")
    try:
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Omi AI Wearable//Action Items to iCal//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
        ]
        for act in items:
            if not isinstance(act, dict):
                continue
            aid = str(act.get("id", "task"))
            raw_summary = act.get("description") or act.get("title") or "Action Item"
            summary = raw_summary.replace("\r", " ").replace("\n", " ")
            status = "COMPLETED" if act.get("completed") else "NEEDS-ACTION"
            due = format_ical_datetime(act.get("due_date") or act.get("due_at"))

            lines.append("BEGIN:VTODO")
            lines.append(f"UID:{aid}@omi.me")
            lines.append(f"SUMMARY:{summary}")
            lines.append(f"STATUS:{status}")
            if due:
                lines.append(f"DUE:{due}")
            lines.append("END:VTODO")

        lines.append("END:VCALENDAR")

        with open(tmp, "w", encoding="utf-8", newline="\r\n") as f:
            f.write("\r\n".join(lines) + "\r\n")

        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python action_items_to_ics.py <source.json> <destination.ics>", file=sys.stderr)
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
