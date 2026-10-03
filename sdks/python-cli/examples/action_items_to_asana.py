import csv
import io
import json
import sys
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path


def clean_text(value):
    """Normalize text whitespace and return cleaned string or empty string."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return " ".join(value.split())


def parse_time(value):
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None if unusable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_offset(value):
    """Turn '+09:00' / '-05:30' into a timedelta for local timezone display."""
    if len(value) != 6 or value[0] not in "+-" or value[3] != ":" or not (value[1:3] + value[4:]).isdigit():
        raise ValueError(f"UTC offset must look like +09:00 or -05:00, got {value!r}")
    delta = timedelta(hours=int(value[1:3]), minutes=int(value[4:]))
    if int(value[4:]) > 59 or delta > timedelta(hours=14):
        raise ValueError(f"UTC offset must be between -14:00 and +14:00, got {value!r}")
    return -delta if value[0] == "-" else delta


def load_action_items(sources):
    """Load and deduplicate action items from multiple JSON source files."""
    items_map = OrderedDict()
    for source in sources:
        path = Path(source)
        payload = json.loads(path.read_bytes())
        # Handle bare array or wrapped {"items": [...]}
        if isinstance(payload, dict):
            for key in ("items", "action_items", "data"):
                if isinstance(payload.get(key), list):
                    payload = payload[key]
                    break
        if not isinstance(payload, list):
            raise ValueError(f"{source}: expected JSON array from 'omi --json action-item list'")
        for raw in payload:
            if not isinstance(raw, dict):
                raise ValueError(f"{source}: each action item must be a JSON object")
            item_id = raw.get("id")
            if not isinstance(item_id, str) or not item_id:
                raise ValueError(f"{source}: action item missing non-empty string 'id'")
            items_map[item_id] = raw
    return list(items_map.values())


def format_asana_row(raw, offset=timedelta(0), default_section="To Do", extra_tags=None):
    """Map a single Omi action item into standard Asana CSV columns."""
    name = clean_text(raw.get("description") or raw.get("title") or "Untitled Task")
    if not name:
        name = "Untitled Task"

    # Completed status: TRUE or FALSE
    is_completed = bool(raw.get("completed"))
    completed_str = "TRUE" if is_completed else "FALSE"

    # Section / Column
    section = "Done" if is_completed else default_section

    # Due date
    due_dt = parse_time(raw.get("due_at") or raw.get("due_date"))
    due_str = (due_dt + offset).strftime("%Y-%m-%d") if due_dt else ""

    # Priority
    priority = clean_text(raw.get("priority") or "Med").capitalize()
    if priority not in ("Low", "Med", "High"):
        priority = "Med"

    # Description with metadata
    desc_lines = []
    desc_val = raw.get("notes") or raw.get("details") or ""
    if desc_val:
        desc_lines.append(clean_text(desc_val))

    desc_lines.append(f"Omi Action Item ID: {raw.get('id', '')}")
    if raw.get("conversation_id"):
        desc_lines.append(f"Source Conversation: {raw.get('conversation_id')}")

    created_dt = parse_time(raw.get("created_at"))
    if created_dt:
        desc_lines.append(f"Captured: {(created_dt + offset).strftime('%Y-%m-%d %H:%M:%S UTC')}")

    full_description = "\n".join(desc_lines)

    # Tags
    tags = ["omi"]
    category = clean_text(raw.get("category"))
    if category:
        tags.append(category)
    if extra_tags:
        tags.extend(extra_tags)
    tags_str = ", ".join(dict.fromkeys(tags))

    return {
        "Name": name,
        "Description": full_description,
        "Due Date": due_str,
        "Section/Column": section,
        "Priority": priority,
        "Completed": completed_str,
        "Tags": tags_str,
    }


def export_asana_csv(items, offset=timedelta(0), default_section="To Do", status_filter=None):
    """Generate RFC 4180 CSV string for Asana import."""
    fieldnames = [
        "Name",
        "Description",
        "Due Date",
        "Section/Column",
        "Priority",
        "Completed",
        "Tags",
    ]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames, lineterminator="\r\n")
    writer.writeheader()

    written_count = 0
    for item in items:
        is_completed = bool(item.get("completed"))
        if status_filter == "completed" and not is_completed:
            continue
        if status_filter == "open" and is_completed:
            continue

        row = format_asana_row(item, offset=offset, default_section=default_section)
        writer.writerow(row)
        written_count += 1

    return out.getvalue(), written_count


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description="Convert Omi action items to Asana CSV format.")
    parser.add_argument("inputs", nargs="+", help="One or more JSON files exported from omi action-item list")
    parser.add_argument("-o", "--output", default="action_items_asana.csv", help="Output CSV path")
    parser.add_argument("--tz-offset", default="+00:00", help="Timezone offset (+HH:MM or -HH:MM)")
    parser.add_argument("--section", default="To Do", help="Default Asana section for open tasks")
    parser.add_argument("--filter-status", choices=["open", "completed"], default=None, help="Filter by status")
    parser.add_argument("--force", action="store_true", help="Overwrite existing output file")

    args = parser.parse_args(argv)

    out_path = Path(args.output)
    if ".." in out_path.parts:
        sys.stderr.write("Error: Path traversal ('..') is not allowed in output path.\n")
        return 2

    if out_path.exists() and not args.force:
        sys.stderr.write(f"Error: Output file already exists: {out_path}. Use --force to overwrite.\n")
        return 1

    try:
        offset = parse_offset(args.tz_offset)
    except ValueError as e:
        sys.stderr.write(f"Error: {e}\n")
        return 1

    try:
        items = load_action_items(args.inputs)
        csv_text, count = export_asana_csv(
            items, offset=offset, default_section=args.section, status_filter=args.filter_status
        )
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(csv_text.encode("utf-8-sig"))
    print(f"Exported {count} action items to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
