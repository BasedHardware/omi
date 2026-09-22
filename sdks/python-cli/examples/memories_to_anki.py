import json
import os
import sys
from pathlib import Path


def convert(source, destination):
    raw = Path(source).read_bytes()
    data = json.loads(raw)
    items = data if isinstance(data, list) else data.get("memories", data.get("items", []))
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json memory list")

    dest = Path(destination)
    if dest.exists():
        raise FileExistsError(f"Destination already exists: {dest}")

    tmp = dest.with_suffix(dest.suffix + ".partial")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("#separator:tab
#html:true
#tags column:3
")
            for m in items:
                if not isinstance(m, dict):
                    continue
                cat = m.get("category", "general")
                content = (m.get("content") or "").replace("	", " ").replace("
", "<br>").replace("
", "<br>")
                created = m.get("created_at", "")[:10]
                front = f"Memory ({cat.capitalize()}): {created}" if created else f"Memory ({cat.capitalize()})"
                back = content
                tags = f"omi memory {cat}"
                f.write(f"{front}	{back}	{tags}
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
        print("Usage: python memories_to_anki.py <source.json> <destination.tsv>", file=sys.stderr)
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
