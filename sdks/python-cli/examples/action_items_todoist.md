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


## Uploading to Todoist API
To import the converted tasks into Todoist via the REST API:

```sh
export TODOIST_TOKEN="your_token_here"

jq -c '.[]' todoist_tasks.json | while read -r task; do
  curl -s -X POST "https://api.todoist.com/rest/v2/tasks" \
    -H "Authorization: Bearer $TODOIST_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$task"
done
```
