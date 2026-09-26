"""Convert an omi action-item export to Taskwarrior import JSON.

Usage: python action_items_to_taskwarrior.py action_items.json omi_tasks.json
       task import omi_tasks.json

See action_items_taskwarrior.md for the full recipe.
"""

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

DONE_WORDS = {"true", "yes", "1", "done", "completed"}
# Fixed namespace, so the same Omi item always maps to the same Taskwarrior UUID.
OMI_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://omi.me/action-items")


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


def is_done(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return isinstance(value, str) and value.strip().lower() in DONE_WORDS


def tw_date(value):
    """Convert an ISO-8601 timestamp to Taskwarrior's UTC form, or None if unusable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def to_task(item):
    task = {"description": one_line(item.get("description")) or "(no description)"}
    omi_id = one_line(item.get("id"))
    if omi_id:
        task["uuid"] = str(uuid.uuid5(OMI_NAMESPACE, omi_id))
    done = is_done(item.get("completed"))
    task["status"] = "completed" if done else "pending"
    for key, field in (("entry", "created_at"), ("modified", "updated_at"), ("due", "due_at")):
        stamp = tw_date(item.get(field))
        if stamp:
            task[key] = stamp
    end = tw_date(item.get("completed_at")) if done else None
    if end:
        task["end"] = end
    task["tags"] = ["omi"]
    if omi_id:
        task["omiid"] = omi_id
    return task


def convert(source, destination):
    items = json.loads(Path(source).read_bytes())
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json action-item list")
    tasks = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each action item must be an object")
        tasks.append(to_task(item))
    # Build the whole file before touching the filesystem, so a conversion
    # failure cannot leave a truncated import file behind.
    payload = (json.dumps(tasks, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
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
    pending = sum(1 for task in tasks if task["status"] == "pending")
    without_id = sum(1 for task in tasks if "uuid" not in task)
    return pending, len(tasks) - pending, without_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert an omi action-item export to Taskwarrior import JSON.")
    parser.add_argument("source", help="JSON from omi --json action-item list")
    parser.add_argument("destination", help="new .json file to create for task import")
    args = parser.parse_args()
    try:
        pending, completed, without_id = convert(args.source, args.destination)
    except (OSError, ValueError) as exc:
        sys.exit(f"Taskwarrior export failed: {exc}")
    print(f"{pending} pending and {completed} completed task(s) written, {without_id} without an Omi id")
