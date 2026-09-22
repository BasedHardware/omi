# Export Action Items → Todoist

The **action_items_to_todoist.py** script is a tiny helper that turns a list of
action items (e.g. the output of a meeting‑capture tool) into a JSON payload that
can be sent directly to the Todoist REST API.

## When to use it

* You have a JSON file (or stream) containing tasks you want to import into
  Todoist.
* You need a deterministic mapping from your own priority scheme to Todoist’s
  numeric priority (1 = lowest, 4 = highest).
* You prefer a **pure‑Python** solution that does not require any external
  dependencies.

## Input format

The script expects a JSON **array** where each element is an object with at
least a `content` field:

