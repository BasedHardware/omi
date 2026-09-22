import json
import os
import sys
import datetime
from pathlib import Path

def sanitize_md(text):
    if not text:
        return ""
    s = str(text)
    if s.lstrip().startswith(("=", "+", "-", "@")):
        s = "'" + s
    return s

def convert(source, destination):
    raw = Path(source).read_bytes()
    data = json.loads(raw)
    items = data if isinstance(data, list) else data.get("memories", data.get("items", []))
    if not isinstance(items, list):
        raise ValueError("Expected JSON array from omi --json memory list")

    dest = Path(destination)
    if dest.exists():
        raise FileExistsError(f"Destination already exists: {dest}")

    tmp = dest.with_suffix(dest.suffix + ".partial")
    try:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        categories = set()
        for it in items:
            if isinstance(it, dict) and it.get("category"):
                categories.add(str(it["category"]).lower().replace(" ", "-"))

        tags_yaml = "
".join(f"  - {c}" for c in sorted(categories)) if categories else "  - general"

        with open(tmp, "w", encoding="utf-8") as f:
            f.write(f"""---
source: omi
type: memories-vault
exported_at: {now_iso}
total_memories: {len(items)}
tags:
  - omi
  - memories
{tags_yaml}
---

# Omi Memories Vault

Exported from [[Omi]] device memory log.

""")
            by_category = {}
            for it in items:
                if not isinstance(it, dict):
                    continue
                cat = str(it.get("category") or "Uncategorized").title()
                by_category.setdefault(cat, []).append(it)

            for cat, mem_list in sorted(by_category.items()):
                f.write(f"## {cat}

")
                for m in mem_list:
                    mid = m.get("id", "mem")
                    content = sanitize_md(m.get("content") or m.get("text") or m.get("title") or "")
                    created = m.get("created_at") or m.get("date") or "Unknown date"
                    tags = [f"#{t}" for t in m.get("tags", []) if isinstance(t, str)]
                    tag_str = " " + " ".join(tags) if tags else ""
                    
                    f.write(f"- **{created}** (`{mid}`){tag_str}
")
                    f.write(f"  > {content}

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
        print("Usage: python memories_to_obsidian.py <source.json> <destination.md>", file=sys.stderr)
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
