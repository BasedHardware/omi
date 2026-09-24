# Export action items to Emacs Org-mode Agenda

Use this recipe to convert your Omi tasks and action items into a clean Emacs Org-mode (`.org`) agenda file.
It parses exported JSON files, formats active `DEADLINE` and inactive `CREATED_AT`/`CLOSED` timestamps, and creates Org-mode `:PROPERTIES:` drawers with unique task IDs and conversation metadata.

You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

## 1. Export Action Items

Export action items to JSON:

```sh
omi --json action-item list --limit 200 --offset 0 > action_items_0.json
```

## 2. Converter Script (`action_items_to_org.py`)

Save the following as `action_items_to_org.py`:

```python
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def text(value):
    """Store loosely typed API fields as text; anything non-null is coerced, not rejected."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)


def parse_iso_stamp(value):
    """Parse an ISO-8601 timestamp string into a UTC datetime object."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return parsed


def format_org_timestamp(dt, active=True):
    """Format datetime into Org-mode timestamp string (active `<...>` or inactive `[...]`)."""
    if dt is None:
        return ""
    day_name = DAY_NAMES[dt.weekday()]
    stamp_str = f"{dt.strftime('%Y-%m-%d')} {day_name} {dt.strftime('%H:%M')}"
    return f"<{stamp_str}>" if active else f"[{stamp_str}]"


def escape_org_text(text_val):
    """Escape Org-mode special markup characters like cookies and tags."""
    if not text_val:
        return ""
    lines = text_val.splitlines()
    escaped_lines = []
    for line in lines:
        cleaned = line.replace("[#A]", "[\u200b#A]").replace("[#B]", "[\u200b#B]").replace("[#C]", "[\u200b#C]")
        escaped_lines.append(cleaned)
    return "\n".join(escaped_lines)


def items_from(source):
    content = Path(source).read_bytes().decode("utf-8-sig")
    items = json.loads(content)
    if isinstance(items, dict):
        items = (
            items.get("action_items")
            or items.get("items")
            or items.get("data")
            or [items]
        )
    if not isinstance(items, list):
        raise ValueError(f"{source}: expected a JSON array or object containing action items")

    parsed_items = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source}: each action item must be an object")
        item_id = item.get("id")
        if item_id is None or str(item_id).strip() == "":
            raise ValueError(f"{source}: action item is missing an id")

        description = item.get("description") or item.get("title") or "Untitled Action Item"
        completed = bool(item.get("completed"))
        due_at = parse_iso_stamp(item.get("due_at"))
        created_at = parse_iso_stamp(item.get("created_at"))
        completed_at = parse_iso_stamp(item.get("completed_at"))
        conversation_id = item.get("conversation_id")

        parsed_items.append({
            "id": str(item_id),
            "description": escape_org_text(text(description)),
            "completed": completed,
            "due_at": due_at,
            "created_at": created_at,
            "completed_at": completed_at,
            "conversation_id": text(conversation_id) if conversation_id else None,
        })
    return parsed_items


def convert_to_org(items, title="Omi Action Items"):
    lines = [f"#+TITLE: {title}", "#+AUTHOR: Omi CLI", ""]

    def sort_key(item):
        if not item["completed"]:
            return (0, item["due_at"] or datetime.max.replace(tzinfo=timezone.utc), item["id"])
        return (1, item["completed_at"] or datetime.max.replace(tzinfo=timezone.utc), item["id"])

    sorted_items = sorted(items, key=sort_key)

    for item in sorted_items:
        status_kw = "DONE" if item["completed"] else "TODO"
        desc_headline = item["description"].splitlines()[0] if item["description"] else "Untitled Task"
        lines.append(f"* {status_kw} {desc_headline}")

        meta_line = []
        if item["completed"] and item["completed_at"]:
            meta_line.append(f"CLOSED: {format_org_timestamp(item['completed_at'], active=False)}")
        if item["due_at"]:
            meta_line.append(f"DEADLINE: {format_org_timestamp(item['due_at'], active=True)}")

        if meta_line:
            lines.append("  " + " ".join(meta_line))

        lines.append("  :PROPERTIES:")
        lines.append(f"  :ID: {item['id']}")
        if item["conversation_id"]:
            lines.append(f"  :CONVERSATION_ID: {item['conversation_id']}")
        if item["created_at"]:
            lines.append(f"  :CREATED_AT: {format_org_timestamp(item['created_at'], active=False)}")
        lines.append("  :END:")

        desc_lines = item["description"].splitlines()
        if len(desc_lines) > 1:
            for body_line in desc_lines[1:]:
                lines.append(f"  {body_line}")
        lines.append("")

    return "\n".join(lines)


def export(target_file, sources):
    all_items = []
    seen_ids = set()
    for source in sources:
        for item in items_from(source):
            if item["id"] not in seen_ids:
                seen_ids.add(item["id"])
                all_items.append(item)

    org_content = convert_to_org(all_items)
    Path(target_file).write_text(org_content, encoding="utf-8")
    return len(all_items)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: python action_items_to_org.py OUTPUT.org INPUT.json [INPUT.json ...]")
    try:
        count = export(sys.argv[1], sys.argv[2:])
    except (OSError, ValueError) as exc:
        sys.exit(f"Org-mode export failed: {exc}")
    print(f"Successfully exported {count} action item(s) to {sys.argv[1]}")
```

## 3. Run Conversion

Convert exported JSON files into an `.org` agenda file:

```sh
python action_items_to_org.py ~/Org/omi_tasks.org action_items_0.json
```

Include `~/Org/omi_tasks.org` in your `org-agenda-files` in Emacs (`M-x org-agenda` `a`) to view deadlines and tasks in your schedule.
