import json
import os
import sys
from pathlib import Path
from collections import defaultdict


def convert(source, destination):
    raw = Path(source).read_bytes()
    data = json.loads(raw)
    convos = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
    if not convos:
        raise ValueError("Expected JSON array of conversations from omi --json conversation list")

    dest = Path(destination)
    if dest.exists():
        raise FileExistsError(f"Destination already exists: {dest}")

    by_date = defaultdict(list)
    for c in convos:
        if not isinstance(c, dict):
            continue
        dt = (c.get("created_at") or "")[:10] or "Undated"
        by_date[dt].append(c)

    tmp = dest.with_suffix(dest.suffix + ".partial")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("# Executive Conversation Digest

")
            f.write(f"Total Conversations: {len(convos)} across {len(by_date)} days.

")

            for dt in sorted(by_date.keys(), reverse=True):
                items = by_date[dt]
                f.write(f"## {dt} ({len(items)} conversations)

")
                for c in items:
                    title = c.get("title") or c.get("structured", {}).get("title") or "Conversation"
                    overview = c.get("structured", {}).get("overview", "No summary available.")
                    actions = c.get("structured", {}).get("action_items", [])
                    f.write(f"### {title}

")
                    f.write(f"{overview}

")
                    if actions:
                        f.write("**Action Items:**
")
                        for a in actions:
                            desc = a.get("description", str(a)) if isinstance(a, dict) else str(a)
                            f.write(f"- [ ] {desc}
")
                        f.write("
")
                f.write("---

")

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
    convert(sys.argv[1], sys.argv[2])
