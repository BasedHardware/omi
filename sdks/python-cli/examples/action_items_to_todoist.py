import argparse
import json
import os
import sys
from pathlib import Path


def convert(source, destination):
    raw = Path(source).read_bytes()
    data = json.loads(raw)
    items = data if isinstance(data, list) else data.get("action_items", data.get("items", []))
    if not isinstance(items, list):
        raise ValueError("Expected JSON array from 'omi --json action-item list'")

    dest = Path(destination)
    if dest.exists():
        raise FileExistsError(f"Destination already exists: {dest}")

    tmp = dest.with_suffix(dest.suffix + ".partial")
    try:
        tasks = []
        for act in items:
            if not isinstance(act, dict):
                continue
            desc = act.get("description") or act.get("title") or "Action Item"
            content = desc.replace("\r", " ").replace("\n", " ").strip()

            task = {
                "content": content,
                "labels": ["omi", "ai-wearable"]
            }

            # Prioritize due_at emitted by Omi CLI, then fallback to due_date or due_string
            due = act.get("due_at") or act.get("due_date") or act.get("due_string")
            if due:
                task["due_string"] = due

            aid = act.get("id")
            if aid:
                task["description"] = f"Imported from Omi (ID: {aid})"

            tasks.append(task)

        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(tasks, f, indent=2, ensure_ascii=False)
            f.write("\n")

        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def main():
    parser = argparse.ArgumentParser(
        description="Format Omi action items for Todoist REST API task creation."
    )
    parser.add_argument("source", help="Path to input JSON file from 'omi --json action-item list'.")
    parser.add_argument("destination", nargs="?", default=None, help="Path to output JSON file.")
    parser.add_argument("-o", "--output", dest="output_flag", default=None, help="Path to output JSON file.")

    args = parser.parse_args()
    dest = args.output_flag or args.destination
    if not dest:
        parser.error("Destination JSON path must be provided either as a positional argument or via -o/--output flag.")

    try:
        convert(args.source, dest)
    except FileExistsError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
