# Export action items to Jira (CSV)

Use this recipe to export Omi action items and tasks into Jira-compatible CSV
format for direct bulk import into Atlassian [Jira](https://www.atlassian.com/software/jira).
It maps task descriptions to Jira `Summary`, includes origin Conversation IDs
and Omi Item IDs in the `Description`, maps completion state to Jira's
`Done`/`To Do` statuses, sets issue types to `Task`, formats due dates as
`YYYY-MM-DD`, and attaches `omi` labels. It reads saved JSON exports, makes zero
network requests, and refuses to overwrite existing files. You need Python 3.10+
and an authenticated `omi-cli` for the initial export.

Export up to 200 action items:

```sh
omi --json action-item list --limit 200 --offset 0 > action_items_0.json
```

Check that the export succeeded before converting. To include more records,
increment `--offset` by 200 into separate files (`action_items_200.json`, etc.).

Save the following as `action_items_to_jira.py`:

```python
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


def format_jira_row(raw, offset=timedelta(0), default_status="To Do", default_priority="Medium", extra_labels=None):
    """Format single action item into Jira CSV compatible dictionary."""
    summary = clean_text(raw.get("description")) or "Untitled action item"
    is_completed = bool(raw.get("completed"))
    status = "Done" if is_completed else default_status

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
        "Issue Type": "Task",
        "Status": status,
        "Priority": default_priority,
        "Due Date": due_str,
        "Labels": " ".join(labels),
        "Created": created_str
    }


def convert(sources, destination, offset=timedelta(0), default_status="To Do", default_priority="Medium", extra_labels=None, status_filter=None):
    """Convert action items JSON exports into Jira-compatible CSV."""
    items = load_action_items(sources)

    if status_filter:
        want_completed = (status_filter.lower() == "completed")
        items = [it for it in items if bool(it.get("completed")) == want_completed]

    output_path = Path(destination)
    try:
        output_file = output_path.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {output_path}") from None

    fieldnames = ["Summary", "Description", "Issue Type", "Status", "Priority", "Due Date", "Labels", "Created"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()

    for it in items:
        row = format_jira_row(it, offset=offset, default_status=default_status, default_priority=default_priority, extra_labels=extra_labels)
        writer.writerow(row)

    payload = buffer.getvalue().encode("utf-8")
    try:
        with output_file:
            output_file.write(payload)
    except OSError:
        output_path.unlink(missing_ok=True)
        raise
    return len(items)


if __name__ == "__main__":
    args = sys.argv[1:]
    offset = timedelta(0)
    default_status = "To Do"
    default_priority = "Medium"
    status_filter = None
    extra_labels = []

    while args and args[0].startswith("--"):
        if args[0] == "--utc-offset":
            if len(args) < 2:
                sys.exit("Error: --utc-offset requires an argument (e.g. +09:00)")
            try:
                offset = parse_offset(args[1])
            except ValueError as exc:
                sys.exit(f"Conversion failed: {exc}")
            args = args[2:]
        elif args[0] == "--status":
            if len(args) < 2 or args[1].lower() not in ("all", "pending", "completed"):
                sys.exit("Error: --status must be one of: all, pending, completed")
            if args[1].lower() != "all":
                status_filter = args[1].lower()
            args = args[2:]
        elif args[0] == "--priority":
            if len(args) < 2:
                sys.exit("Error: --priority requires a priority name (e.g. High, Medium, Low)")
            default_priority = args[1]
            args = args[2:]
        elif args[0] == "--label":
            if len(args) < 2:
                sys.exit("Error: --label requires a label name")
            extra_labels.append(args[1])
            args = args[2:]
        else:
            sys.exit(f"Unknown option: {args[0]}")

    if len(args) < 2:
        sys.exit("Usage: python action_items_to_jira.py [--utc-offset +09:00] [--status pending|completed] [--priority High] [--label tag] OUTPUT.csv INPUT.json [INPUT.json ...]")

    dest = args[0]
    srcs = args[1:]
    try:
        count = convert(srcs, dest, offset=offset, default_status=default_status, default_priority=default_priority, extra_labels=extra_labels, status_filter=status_filter)
        print(f"Exported {count} action items to Jira CSV: {dest}")
    except (OSError, ValueError) as exc:
        sys.exit(f"Export failed: {exc}")
```

Run it (the output file comes first, then one or more exports):

```sh
# Export all action items to Jira CSV
python action_items_to_jira.py jira_tasks.csv action_items_0.json

# Export pending items with custom priority and tags
python action_items_to_jira.py --status pending --priority High --label sprint-q4 --utc-offset +09:00 jira_urgent.csv action_items_0.json
```

Importing into Jira:
1. In Jira, navigate to **Settings -> System -> External System Import -> CSV**.
2. Select `jira_tasks.csv`.
3. Choose your target project.
4. Verify field mappings (Summary -> Summary, Description -> Description, Issue Type -> Issue Type, Due Date -> Due Date, Labels -> Labels).
5. Click **Begin Import**.
