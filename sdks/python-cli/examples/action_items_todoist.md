# Export action items to Todoist tasks payload

Use this recipe to convert Omi conversational action items into Todoist REST API payloads with priority detection and natural language due date parsing.

Export action items:

```sh
omi --json action-item list --open > action_items.json
```

Convert to Todoist:

```sh
python action_items_to_todoist.py action_items.json todoist_tasks.json
```
