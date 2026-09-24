# Sync Omi action items to Todoist tasks

Use this recipe to convert Omi action items into standard Todoist REST API payloads. You can pipe the output directly into Todoist or batch-create tasks with due dates, labels, and conversation metadata.

## Prerequisites

- Python 3.10+ (standard library only)
- An authenticated `omi-cli` installation
- Optional: A Todoist API token from [Todoist Developer Console](https://developer.todoist.com/appconsole.html)

## Usage

Generate Todoist task payloads for all open action items:

```sh
omi --json action-item list --limit 50 | python action_items_to_todoist.py - --label omi -o todoist_tasks.json
```

Or process a local export:

```sh
python action_items_to_todoist.py action_items.json --label work --project-id "2203306147" -o todoist_tasks.json
```

Output:
```
Generated 18 Todoist task payload(s) at todoist_tasks.json
```

## Syncing via Python or curl

Sync tasks directly to Todoist with a short Python script:

```python
import json
import urllib.request

TODOIST_TOKEN = "your_todoist_api_token"
tasks = json.loads(open("todoist_tasks.json").read())

for task in tasks:
    req = urllib.request.Request(
        "https://api.todoist.com/rest/v2/tasks",
        data=json.dumps(task).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {TODOIST_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        print(f"Created: {task['content']}")
```

## Features

- **Open Tasks Only by Default**: Automatically skips closed or completed tasks (pass `--all` to include them).
- **Due Date Mapping**: Converts ISO dates to Todoist-compatible `due_date` format (`YYYY-MM-DD`).
- **Context Preservation**: Appends conversation ID and creation timestamp in task description.
- **Pure Standard Library**: Zero external dependencies required.
