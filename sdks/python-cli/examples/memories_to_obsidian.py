import argparse
import json
import os
import sys
from pathlib import Path


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
            "---",
            "tags:",
            "  - omi/memories",
            "---",
            "",
            "# Omi Memories",
            "",
            "Exported from [[Omi]] device memory log.",
            "",
        ]
        for mem in items:
            if not isinstance(mem, dict):
                continue
            content = mem.get("content") or mem.get("text") or ""
            if not content:
                continue
            category = mem.get("category") or "general"
            created_at = mem.get("created_at") or ""

            # Ensure multiline blockquote preserves '>' on every line
            for line in content.splitlines():
                lines.append(f"> {line}")
            lines.append(f"> — [[{category.title()}]] · *{created_at}*")
            lines.append("")

        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines).strip() + "\n")

        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def main():
    parser = argparse.ArgumentParser(
        description="Convert Omi memories into Obsidian Markdown notes with wikilinks."
    )
    parser.add_argument("source", help="Path to input JSON file from 'omi --json memory list'.")
    parser.add_argument("destination", nargs="?", default=None, help="Path to output Markdown file.")
    parser.add_argument("-o", "--output", dest="output_flag", default=None, help="Path to output Markdown file.")

    args = parser.parse_args()
    dest = args.output_flag or args.destination
    if not dest:
        parser.error("Destination path must be provided either as a positional argument or via -o/--output flag.")

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
