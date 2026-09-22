#!/usr/bin/env python3
"""
Convert Omi action items JSON export to UTF-8 JSON Lines (.jsonl), one item per line.

Usage:
    python action_items_to_jsonl.py action_items.json action_items.jsonl
"""

import json
import os
import sys
from pathlib import Path


def convert(source, destination):
    raw_content = Path(source).read_text(encoding="utf-8")
    if raw_content.startswith("﻿"):
        raw_content = raw_content[1:]
    items = json.loads(raw_content)

    if isinstance(items, dict):
        if "action_items" in items and isinstance(items["action_items"], list):
            items = items["action_items"]
        elif "data" in items and isinstance(items["data"], list):
            items = items["data"]
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError("Expected a JSON array or object from omi --json action-item list")

    lines = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each action item must be an object")
        lines.append(json.dumps(item, ensure_ascii=False, allow_nan=False))

    output_path = Path(destination)
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing {output_path}")

    partial = output_path.with_name(output_path.name + ".partial")
    try:
        content = ("\n".join(lines) + "\n") if lines else ""
        partial.write_text(content, encoding="utf-8", newline="\n")
        os.replace(partial, output_path)
    except OSError:
        partial.unlink(missing_ok=True)
        raise


def main(argv):
    if len(argv) != 3:
        sys.exit("Usage: python action_items_to_jsonl.py INPUT.json OUTPUT.jsonl")
    try:
        convert(argv[1], argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"JSONL export failed: {exc}")


if __name__ == "__main__":
    main(sys.argv)
