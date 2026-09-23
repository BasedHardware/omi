#!/usr/bin/env python3
"""
Convert Omi tracked goals JSON export to UTF-8 JSON Lines (.jsonl), one goal per line.

Adds a computed `progress_pct` field to each record (matching the convention
already used by goals_csv.md: current_value / target_value, falling back to
the min_value-max_value range when target_value isn't usable).

Usage:
    python goals_to_jsonl.py goals.json goals.jsonl
"""

import json
import os
import sys
from pathlib import Path


def progress_pct(current, target, min_value, max_value):
    """Fraction of a goal completed, clamped to [0, 1]."""
    try:
        c = float(current)
    except (TypeError, ValueError):
        return None
    try:
        t = float(target)
        if t > 0:
            return round(max(0.0, min(1.0, c / t)), 4)
    except (TypeError, ValueError):
        pass
    try:
        lo, hi = float(min_value), float(max_value)
        if hi > lo:
            return round(max(0.0, min(1.0, (c - lo) / (hi - lo))), 4)
    except (TypeError, ValueError):
        pass
    return None


def convert(source, destination):
    raw_content = Path(source).read_text(encoding="utf-8")
    if raw_content.startswith("﻿"):
        raw_content = raw_content[1:]
    items = json.loads(raw_content)

    if isinstance(items, dict):
        if "goals" in items and isinstance(items["goals"], list):
            items = items["goals"]
        elif "data" in items and isinstance(items["data"], list):
            items = items["data"]
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError("Expected a JSON array or object from omi --json goal list")

    lines = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each goal must be an object")
        record = dict(item)
        record["progress_pct"] = progress_pct(
            item.get("current_value"), item.get("target_value"), item.get("min_value"), item.get("max_value")
        )
        lines.append(json.dumps(record, ensure_ascii=False, allow_nan=False))

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
        sys.exit("Usage: python goals_to_jsonl.py INPUT.json OUTPUT.jsonl")
    try:
        convert(argv[1], argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"JSONL export failed: {exc}")


if __name__ == "__main__":
    main(sys.argv)
