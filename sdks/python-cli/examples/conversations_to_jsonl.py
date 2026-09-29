#!/usr/bin/env python3
"""
Convert Omi conversations JSON export to UTF-8 JSON Lines (.jsonl), one conversation per line.

Usage:
    python conversations_to_jsonl.py conversations.json conversations.jsonl
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
        if "conversations" in items and isinstance(items["conversations"], list):
            items = items["conversations"]
        elif "data" in items and isinstance(items["data"], list):
            items = items["data"]
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError("Expected a JSON array or object from omi --json conversation list")

    lines = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each conversation must be an object")
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
        sys.exit("Usage: python conversations_to_jsonl.py INPUT.json OUTPUT.jsonl")
    try:
        convert(argv[1], argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"JSONL export failed: {exc}")


if __name__ == "__main__":
    main(sys.argv)
