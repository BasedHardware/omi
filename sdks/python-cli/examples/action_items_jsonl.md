# Export Omi Action Items to JSON Lines (JSONL) for Automations & LLMs

Use this recipe to export tasks and action items captured by your Omi wearable
device into standard JSON Lines (`.jsonl`) format. The output is directly
consumable by workflow automations (Zapier, Make, n8n, Todoist integrations),
task databases, or fine-tuning pipelines for personal executive AI assistants.

It reads saved JSON exports or reads directly from standard input (`-`), makes no
network requests, and writes one clean `.jsonl` file. You need Python 3.10+ and
an authenticated `omi-cli` for the initial export.

---

## Quickstart

### 1. Direct Pipeline Export (Stdout to JSONL)

Stream up to 500 action items directly into a `.jsonl` file:

```sh
omi --json action-item list --limit 500 | python action_items_to_jsonl.py - action_items.jsonl
```

### 2. Export from a Saved JSON File

If you have already saved an export:

```sh
omi --json action-item list --limit 500 > action_items.json
python action_items_to_jsonl.py action_items.json action_items.jsonl
```

### 3. Choose Target Schema Format

The converter provides three specialized output schemas:

- **`standard` (default):** Clean, normalized JSON records containing task IDs, descriptions, completion flags, and due dates.
- **`task`:** Formatted with `{"task_id": "...", "title": "...", "status": "...", "due_date": "..."}` for automation webhooks and task sync APIs.
- **`fine-tune`:** Chat completion format `{"messages": [...]}` tailored for training AI assistants to track commitments and action items.

```sh
# Export for automation pipelines (pending tasks only):
python action_items_to_jsonl.py action_items.json tasks_pending.jsonl --format task --status open

# Export for LLM instruction fine-tuning:
python action_items_to_jsonl.py action_items.json tasks_ft.jsonl --format fine-tune
```

---

## Converter Script

Save the following as `action_items_to_jsonl.py`:

```python
import argparse
import json
import sys
from pathlib import Path


def sanitize_text(value):
    """Render a loosely typed field as clean, single-line text."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(value.split())


def load_items(source):
    """Load action items from stdin or a file path, ensuring valid list structure."""
    if source == "-":
        content = sys.stdin.read()
    else:
        content = Path(source).read_text(encoding="utf-8")

    data = json.loads(content)
    if isinstance(data, dict) and "action_items" in data:
        data = data["action_items"]
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list of action items, got {type(data).__name__}")
    return data


def format_record(item, mode):
    """Format a single action item according to the specified output mode."""
    item_id = item.get("id") or ""
    description = sanitize_text(item.get("description")) or "(untitled task)"
    completed = bool(item.get("completed"))
    due_at = item.get("due_at") or None
    created_at = item.get("created_at") or ""
    updated_at = item.get("updated_at") or ""
    conversation_id = item.get("conversation_id") or ""

    if mode == "task":
        return {
            "task_id": item_id,
            "title": description,
            "status": "completed" if completed else "pending",
            "due_date": due_at[:10] if due_at else None,
            "origin_ref": conversation_id
        }
    elif mode == "fine-tune":
        status_str = "Completed" if completed else "Pending"
        due_str = f", Due: {due_at}" if due_at else ""
        return {
            "messages": [
                {
                    "role": "system",
                    "content": "You are a personal AI executive assistant managing tasks and action items."
                },
                {
                    "role": "user",
                    "content": f"What was the action item recorded from conversation {conversation_id}?"
                },
                {
                    "role": "assistant",
                    "content": f"Task: {description} (Status: {status_str}{due_str})"
                }
            ]
        }
    else:  # standard
        return {
            "id": item_id,
            "description": description,
            "completed": completed,
            "due_at": due_at,
            "created_at": created_at,
            "updated_at": updated_at,
            "conversation_id": conversation_id
        }


def convert(source, destination, mode, status_filter="all", overwrite=False):
    """Convert input action items to a destination JSONL file."""
    items = load_items(source)
    output_path = Path(destination)

    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing {output_path} (use --overwrite to force)")

    lines = []
    seen_ids = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if item_id and item_id in seen_ids:
            continue
        if item_id:
            seen_ids.add(item_id)

        completed = bool(item.get("completed"))
        if status_filter == "open" and completed:
            continue
        if status_filter == "completed" and not completed:
            continue

        record = format_record(item, mode)
        lines.append(json.dumps(record, ensure_ascii=False))

    payload = "\n".join(lines) + ("\n" if lines else "")
    output_path.write_text(payload, encoding="utf-8")
    return len(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Omi action items JSON export to JSON Lines (.jsonl).")
    parser.add_argument("source", help="Path to input JSON file or '-' for stdin.")
    parser.add_argument("destination", help="Path to output .jsonl file.")
    parser.add_argument(
        "--format",
        choices=["standard", "task", "fine-tune"],
        default="standard",
        help="Target JSONL schema: standard (default), task (webhooks/sync), or fine-tune (chat dataset)."
    )
    parser.add_argument(
        "--status",
        choices=["all", "open", "completed"],
        default="all",
        help="Filter action items by status: all (default), open (pending only), or completed."
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite destination if it already exists.")

    args = parser.parse_args()
    try:
        count = convert(args.source, args.destination, args.format, status_filter=args.status, overwrite=args.overwrite)
    except (ValueError, OSError) as exc:
        sys.exit(f"Conversion failed: {exc}")

    print(f"Successfully converted {count} action item{'s' if count != 1 else ''} to {args.destination} (mode: {args.format})")
```

---

## Schema Formats Reference

### Standard Format (`--format standard`)
```json
{"id": "act_001", "description": "Review pull request", "completed": false, "due_at": "2026-09-25T18:00:00Z", "created_at": "2026-09-24T08:00:00Z", "conversation_id": "conv_123"}
```

### Automation Webhook Format (`--format task`)
```json
{"task_id": "act_001", "title": "Review pull request", "status": "pending", "due_date": "2026-09-25", "origin_ref": "conv_123"}
```

### Fine-Tuning Format (`--format fine-tune`)
```json
{"messages": [{"role": "system", "content": "You are a personal AI executive assistant."}, {"role": "user", "content": "What was the action item recorded from conversation conv_123?"}, {"role": "assistant", "content": "Task: Review pull request (Status: Pending, Due: 2026-09-25T18:00:00Z)"}]}
```
