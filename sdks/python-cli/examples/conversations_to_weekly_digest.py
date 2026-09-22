import json
import os
import sys
from collections import defaultdict
from pathlib import Path

def convert(source, destination):
    raw = Path(source).read_bytes()
    data = json.loads(raw)
    items = data if isinstance(data, list) else data.get("conversations", data.get("items", []))
    if not isinstance(items, list):
        raise ValueError("Expected JSON array from 'omi --json conversation list'")

    dest = Path(destination)
    if dest.exists():
        raise FileExistsError(f"Destination already exists: {dest}")

    grouped = defaultdict(list)
    for c in items:
        if not isinstance(c, dict):
            continue
        date_str = (c.get("started_at") or c.get("created_at") or "")[:10] or "Undated"
        grouped[date_str].append(c)

    lines = ["# Executive Conversation Digest", "", f"Total Conversations: {len(items)}", ""]
    for date_key in sorted(grouped.keys(), reverse=True):
        lines.append(f"## {date_key}")
        lines.append("")
        for conv in grouped[date_key]:
            cid = conv.get("id", "Unknown")
            struct = conv.get("structured") or {}
            if not isinstance(struct, dict):
                struct = {}
            title = struct.get("title") or conv.get("title") or f"Conversation {cid}"
            overview = struct.get("overview") or "No overview provided."
            lines.append(f"### {title}")
            lines.append(f"**ID**: `{cid}`")
            lines.append("")
            lines.append(f"**Summary**: {overview}")
            lines.append("")
            action_items = conv.get("action_items") or struct.get("action_items") or []
            if action_items and isinstance(action_items, list):
                lines.append("**Action Items**:")
                for item in action_items:
                    if isinstance(item, dict):
                        desc = item.get("description") or item.get("content") or "Task"
                        checked = "x" if item.get("completed") else " "
                        lines.append(f"- [{checked}] {desc}")
                    elif isinstance(item, str):
                        lines.append(f"- [ ] {item}")
                lines.append("")
            lines.append("---")
            lines.append("")

    tmp = dest.with_suffix(dest.suffix + ".partial")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines).strip() + "\n")
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python conversations_to_weekly_digest.py <source.json> <destination.md>", file=sys.stderr)
        sys.exit(1)
    try:
        convert(sys.argv[1], sys.argv[2])
    except FileExistsError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
