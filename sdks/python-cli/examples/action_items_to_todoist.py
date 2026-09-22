import json
import os
import sys
import re
from pathlib import Path

def sanitize_text(text):
    if not text:
        return ""
    s = str(text).strip()
    if s.lstrip().startswith(("=", "+", "-", "@")):
        s = "'" + s
    return s

def extract_due_string(text):
    patterns = [
        r"\b(today|tomorrow|tonight)\b",
        r"\b(by\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b",
        r"\b(next\s+(?:week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b",
        r"\b(before\s+[a-z0-9\s]+)\b",
        r"\b(in\s+\d+\s+(?:days?|weeks?|hours?))\b",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None

def resolve_priority(text):
    lower = text.lower()
    if any(k in lower for k in ("urgent", "asap", "critical", "immediately", "blocker")):
        return 4
    if any(k in lower for k in ("important", "priority", "soon", "must")):
        return 3
    if any(k in lower for k in ("low priority", "optional", "someday", "nice to have")):
        return 1
    return 2

def convert(source, destination):
    raw = Path(source).read_bytes()
    data = json.loads(raw)
    
    items = []
    if isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict) and "action_items" in entry.get("structured", {}):
                items.extend(entry["structured"]["action_items"])
            elif isinstance(entry, dict) and "action_items" in entry:
                items.extend(entry["action_items"])
            elif isinstance(entry, dict) and ("description" in entry or "content" in entry):
                items.append(entry)
    elif isinstance(data, dict):
        if "action_items" in data:
            items = data["action_items"]
        elif "items" in data:
            items = data["items"]

    dest = Path(destination)
    if dest.exists():
        raise FileExistsError(f"Destination already exists: {dest}")

    tasks = []
    for it in items:
        if not isinstance(it, dict):
            content = str(it)
            desc = ""
            due = None
            prio = resolve_priority(content)
        else:
            content = it.get("description") or it.get("content") or it.get("title") or ""
            desc = it.get("context") or it.get("notes") or f"Imported from Omi (ID: {it.get('id', 'item')})"
            due = it.get("due_date") or it.get("due_string") or extract_due_string(content)
            prio = it.get("priority") or resolve_priority(content)

        task_payload = {
            "content": sanitize_text(content),
            "description": sanitize_text(desc),
            "priority": prio,
            "labels": ["omi", "ai-wearable"],
        }
        if due:
            task_payload["due_string"] = str(due)

        tasks.append(task_payload)

    result = {
        "source": "omi-action-items",
        "total_tasks": len(tasks),
        "tasks": tasks,
    }

    tmp = dest.with_suffix(dest.suffix + ".partial")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python action_items_to_todoist.py <source.json> <destination.json>", file=sys.stderr)
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
