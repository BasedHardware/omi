import json
import os
import sys
from pathlib import Path

def clean_anki_field(text):
    if not text:
        return ""
    text = str(text).replace("\t", " ")
    text = text.replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")
    return text.strip()

def convert(source, destination):
    raw = Path(source).read_bytes()
    data = json.loads(raw)
    items = data if isinstance(data, list) else data.get("memories", data.get("items", []))
    if not isinstance(items, list):
        raise ValueError("Expected JSON array from 'omi --json memory list'")

    dest = Path(destination)
    if dest.exists():
        raise FileExistsError(f"Destination already exists: {dest}")

    tmp = dest.with_suffix(dest.suffix + ".partial")
    try:
        lines = [
            "#separator:tab",
            "#html:true",
            "#tags column:3",
        ]
        for mem in items:
            if not isinstance(mem, dict):
                continue
            content = mem.get("content") or mem.get("text") or ""
            if not content:
                continue
            category = mem.get("category") or "general"
            created_at = mem.get("created_at") or ""

            front = clean_anki_field(content)
            back = f"Category: {clean_anki_field(category)}<br>Captured: {clean_anki_field(created_at)}"
            tags = clean_anki_field(category).replace(" ", "_")

            lines.append(f"{front}\t{back}\t{tags}")

        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python memories_to_anki.py <source.json> <destination.txt>", file=sys.stderr)
        sys.exit(1)
    try:
        convert(sys.argv[1], sys.argv[2])
    except FileExistsError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
