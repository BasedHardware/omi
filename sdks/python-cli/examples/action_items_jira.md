# Export action items to Jira (CSV)

Use this recipe to export Omi action items and tasks into Jira-compatible CSV
format for direct bulk import into Atlassian [Jira](https://www.atlassian.com/software/jira).
It maps task descriptions to Jira `Summary`, includes origin Conversation IDs
and Omi Item IDs in the `Description`, maps completion state to Jira's
`Done`/`To Do` statuses, sets issue types to `Task`, formats due dates as
`YYYY-MM-DD`, and attaches `omi` labels. It reads saved JSON exports, makes zero
network requests, and refuses to overwrite existing files unless `--force` is
given. You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export up to 200 action items:

```sh
omi --json action-item list --limit 200 --offset 0 > action_items_0.json
```

Check that the export succeeded before converting. To include more records,
increment `--offset` by 200 into separate files (`action_items_200.json`, etc.).
Multiple export files can be passed together to merge and deduplicate by item ID.

Save the following as `action_items_to_jira.py` (the same script is kept
next to this recipe as [`action_items_to_jira.py`](action_items_to_jira.py)
and covered by `tests/test_action_items_to_jira.py`):

```python
"""Convert Omi action-item JSON exports to Atlassian Jira CSV format.

See action_items_jira.md for the full recipe and Jira import instructions.

Usage:
    omi --json action-item list --limit 200 > action_items.json
    python action_items_to_jira.py jira_tasks.csv action_items.json
    python action_items_to_jira.py --status pending --priority High jira_urgent.csv action_items.json
"""

import argparse
import csv
import io
import json
import sys
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path

DONE_WORDS = {"true", "yes", "1", "done", "completed"}


def clean_text(value):
    """Normalize text whitespace and return cleaned string or empty string."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(value.split())


def is_done(value):
    """Normalize completed status into a boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in DONE_WORDS
    return False


def parse_time(value):
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None if unusable."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_offset(value):
    """Turn '+09:00' / '-05:30' into a timedelta for local timezone display."""
    if not isinstance(value, str):
        raise ValueError("UTC offset must be a string")
    value = value.strip()
    if len(value) != 6 or value[0] not in "+-" or value[3] != ":" or not (value[1:3] + value[4:]).isdigit():
        raise ValueError(f"UTC offset must look like +09:00 or -05:00, got {value!r}")
    hours = int(value[1:3])
    minutes = int(value[4:])
    if minutes > 59 or hours > 14:
        raise ValueError(f"UTC offset must be between -14:00 and +14:00, got {value!r}")
    delta = timedelta(hours=hours, minutes=minutes)
    if delta > timedelta(hours=14):
        raise ValueError(f"UTC offset must be between -14:00 and +14:00, got {value!r}")
    return -delta if value[0] == "-" else delta


def load_action_items(sources):
    """Load and deduplicate action items from multiple JSON sources or envelopes."""
    items_map = OrderedDict()
    for source in sources:
        path = Path(source)
        content = path.read_bytes().decode("utf-8-sig")
        payload = json.loads(content)

        if isinstance(payload, dict):
            found_key = None
            for key in ("action_items", "items", "data"):
                if key in payload:
                    found_key = key
                    break
            if found_key is not None:
                items = payload[found_key]
            elif "id" in payload:
                items = [payload]
            else:
                raise ValueError(f"{source}: expected JSON array or object containing action items")
        elif isinstance(payload, list):
            items = payload
        else:
            raise ValueError(f"{source}: expected JSON array or object containing action items")

        if not isinstance(items, list):
            raise ValueError(f"{source}: action items payload must be a JSON array")

        for raw in items:
            if not isinstance(raw, dict):
                raise ValueError(f"{source}: each action item must be a JSON object")
            item_id = raw.get("id")
            if item_id is None or str(item_id).strip() == "":
                raise ValueError(f"{source}: action item missing non-empty string 'id'")
            items_map[str(item_id)] = raw

    return list(items_map.values())


def format_jira_row(raw, offset=timedelta(0), default_status="To Do", default_priority="Medium", issue_type="Task", extra_labels=None):
    """Format single action item into Jira CSV compatible dictionary."""
    summary = clean_text(raw.get("description") or raw.get("title")) or "Untitled action item"
    completed = is_done(raw.get("completed"))
    status = "Done" if completed else default_status

    due_dt = parse_time(raw.get("due_at"))
    due_str = (due_dt + offset).strftime("%Y-%m-%d") if due_dt else ""

    created_dt = parse_time(raw.get("created_at"))
    created_str = (created_dt + offset).strftime("%Y-%m-%d %H:%M:%S") if created_dt else ""

    item_id = clean_text(raw.get("id"))
    conv_id = clean_text(raw.get("conversation_id"))

    description_lines = [f"Imported from Omi AI wearable (Item ID: {item_id})."]
    if conv_id:
        description_lines.append(f"Origin Conversation ID: {conv_id}.")

    labels = ["omi", "action-item"]
    if extra_labels:
        for lbl in extra_labels:
            cl = clean_text(lbl).replace(" ", "-")
            if cl and cl not in labels:
                labels.append(cl)

    return {
        "Summary": summary,
        "Description": " ".join(description_lines),
        "Issue Type": issue_type,
        "Status": status,
        "Priority": default_priority,
        "Due Date": due_str,
        "Labels": " ".join(labels),
        "Created": created_str,
    }


def convert(sources, destination, offset=timedelta(0), default_status="To Do", default_priority="Medium", issue_type="Task", extra_labels=None, status_filter=None, force=False):
    """Convert action items JSON exports into Jira-compatible CSV."""
    items = load_action_items(sources)

    if status_filter and status_filter.lower() != "all":
        want_completed = (status_filter.lower() == "completed")
        items = [it for it in items if is_done(it.get("completed")) == want_completed]

    output_path = Path(destination)
    if not force:
        try:
            output_file = output_path.open("xb")
        except FileExistsError:
            raise FileExistsError(f"Refusing to overwrite existing {output_path} (use --force to overwrite)") from None
    else:
        output_file = output_path.open("wb")

    fieldnames = ["Summary", "Description", "Issue Type", "Status", "Priority", "Due Date", "Labels", "Created"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()

    for it in items:
        row = format_jira_row(
            it,
            offset=offset,
            default_status=default_status,
            default_priority=default_priority,
            issue_type=issue_type,
            extra_labels=extra_labels,
        )
        writer.writerow(row)

    payload = buffer.getvalue().encode("utf-8")
    try:
        with output_file:
            output_file.write(payload)
    except OSError:
        if not force:
            output_path.unlink(missing_ok=True)
        raise
    return len(items)


def build_parser():
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Export Omi action items to Atlassian Jira CSV format."
    )
    parser.add_argument("destination", help="destination CSV file to create")
    parser.add_argument("sources", nargs="+", help="one or more JSON action item export files")
    parser.add_argument(
        "--utc-offset",
        type=parse_offset,
        default=timedelta(0),
        help="UTC offset for dates, e.g. +09:00 or -05:00 (default: +00:00)",
    )
    parser.add_argument(
        "--status",
        choices=["all", "pending", "completed"],
        default="all",
        help="filter action items by completion status (default: all)",
    )
    parser.add_argument(
        "--priority",
        default="Medium",
        help="default Jira priority for exported tasks (default: Medium)",
    )
    parser.add_argument(
        "--issue-type",
        default="Task",
        help="default Jira issue type (default: Task)",
    )
    parser.add_argument(
        "--label",
        action="append",
        dest="labels",
        default=[],
        help="additional label to attach to each Jira issue (repeatable)",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="overwrite destination file if it already exists",
    )
    return parser


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()

    try:
        count = convert(
            sources=args.sources,
            destination=args.destination,
            offset=args.utc_offset,
            default_status="To Do",
            default_priority=args.priority,
            issue_type=args.issue_type,
            extra_labels=args.labels,
            status_filter=args.status,
            force=args.force,
        )
        print(f"Exported {count} action item(s) to Jira CSV: {args.destination}")
    except (OSError, ValueError) as exc:
        sys.exit(f"Export failed: {exc}")
```

Run it (the output file comes first, then one or more JSON export files):

```sh
# Export all action items to Jira CSV
python action_items_to_jira.py jira_tasks.csv action_items_0.json

# Export pending items with custom priority and tags
python action_items_to_jira.py --status pending --priority High --label sprint-q4 --utc-offset +09:00 jira_urgent.csv action_items_0.json

# Merge multiple paginated exports and overwrite existing CSV
python action_items_to_jira.py --force all_tasks.csv action_items_0.json action_items_200.json
```

## Importing into Jira

1. In Jira, navigate to **Settings -> System -> External System Import -> CSV** (or Jira Administration > Import and Export).
2. Select your exported `jira_tasks.csv` file.
3. Select your target Jira Project.
4. Verify field mappings:

| CSV Field | Jira Field | Description |
|---|---|---|
| `Summary` | `Summary` | Action item task description or title |
| `Description` | `Description` | Origin metadata (item ID and conversation ID) |
| `Issue Type` | `Issue Type` | Defaults to `Task` |
| `Status` | `Status` | `Done` (for completed) or `To Do` |
| `Priority` | `Priority` | Defaults to `Medium` (or specified) |
| `Due Date` | `Due Date` | Localized due date (`YYYY-MM-DD`) |
| `Labels` | `Labels` | Space-delimited tags (`omi`, `action-item`, etc.) |
| `Created` | `Date Created` | Localized creation timestamp |

5. Under Date Format settings, ensure the format matches `yyyy-MM-dd` or `yyyy-MM-dd HH:mm:ss`.
6. Click **Begin Import**.
