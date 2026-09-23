# Export action items to Todoist REST API tasks

Use this recipe to convert action items extracted by Omi into structured JSON payloads ready for batch import into Todoist via the Todoist REST API.

Each task is automatically tagged with the `omi` and `ai-wearable` labels and preserves original timestamps and source action item IDs.

## Requirements

- Python 3.10+ (standard library only)
- Todoist API token (from Todoist Settings > Integrations > Developer)

## Workflow

### 1. Export action items from Omi

```sh
omi --json action-item list --open > action_items.json
```

### 2. Convert to Todoist task format

```sh
# Using -o / --output flag
python sdks/python-cli/examples/action_items_to_todoist.py action_items.json -o todoist_tasks.json

# Or using positional arguments
python sdks/python-cli/examples/action_items_to_todoist.py action_items.json todoist_tasks.json
```

### 3. Upload to Todoist REST API

You can batch-upload the generated tasks using `curl` or Python:

#### Using curl and jq:

```sh
export TODOIST_API_TOKEN="your_todoist_api_token"

jq -c '.[]' todoist_tasks.json | while read -r task; do
  curl -s -X POST "https://api.todoist.com/rest/v2/tasks" \
    -H "Authorization: Bearer $TODOIST_API_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$task"
  sleep 0.2
done
```

#### Using Python:

```python
import json
import os
import time
import urllib.request

TOKEN = os.environ.get("TODOIST_API_TOKEN")
with open("todoist_tasks.json", "r", encoding="utf-8") as f:
    tasks = json.load(f)

for task in tasks:
    req = urllib.request.Request(
        "https://api.todoist.com/rest/v2/tasks",
        data=json.dumps(task).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json"
        }
    )
    with urllib.request.urlopen(req) as resp:
        print(f"Created task: {task['content']}")
    time.sleep(0.2)
```

## Output Schema

The output JSON contains an array of tasks formatted for the Todoist `/rest/v2/tasks` endpoint:

```json
[
  {
    "content": "Follow up with design team on prototype feedback",
    "labels": ["omi", "ai-wearable"],
    "due_string": "2026-09-25T15:00:00Z",
    "description": "Imported from Omi (ID: act_98765)"
  }
]
```
