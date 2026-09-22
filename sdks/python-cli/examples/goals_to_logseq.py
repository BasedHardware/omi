#!/usr/bin/env python3
"""
Convert Omi tracked goals JSON export to a Logseq-format Markdown page.

Distinct from a plain Markdown export: each goal is a Logseq outliner block
with `progress::`/`current::`/`target::` block properties and an `#active`
or `#completed` hashtag, so Logseq's linked-references view groups goals by
status automatically.

Usage:
    python goals_to_logseq.py goals.json goals.md
"""

import json
import os
import re
import sys
from pathlib import Path

_TAG_UNSAFE = re.compile(r"[^\w-]+")


def logseq_tag(value):
    """Turn *value* into a safe Logseq hashtag (spaces/punctuation -> hyphens)."""
    slug = _TAG_UNSAFE.sub("-", str(value).strip()).strip("-")
    return f"#{slug}" if slug else None


def escape_block_text(value):
    """Neutralize Logseq/Markdown link and tag syntax in free-text content.

    `[[`, `]]`, and `#` would otherwise be interpreted as a page link or a
    tag by Logseq anywhere they appear in the text, even though they came
    from the goal's own title, not from us.
    """
    text = str(value) if value is not None else ""
    text = text.replace("[[", "\\[\\[").replace("]]", "\\]\\]")
    text = text.replace("#", "\\#")
    return text.replace("\n", "\n  ")


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
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each goal must be an object")

    lines = [
        "type:: omi-goals",
        f"count:: {len(items)}",
        "",
    ]

    for item in items:
        title = escape_block_text(item.get("title") or "Untitled goal")
        is_active = item.get("is_active", True)
        status_tag = logseq_tag("active" if is_active else "completed")
        pct = progress_pct(
            item.get("current_value"), item.get("target_value"), item.get("min_value"), item.get("max_value")
        )

        block = f"- {title} {status_tag}" if status_tag else f"- {title}"
        lines.append(block)
        if pct is not None:
            lines.append(f"  progress:: {pct * 100:.0f}%")
        lines.append(f"  current:: {item.get('current_value')}")
        lines.append(f"  target:: {item.get('target_value')}")
        goal_id = item.get("id")
        if goal_id:
            lines.append(f"  omi-id:: {goal_id}")

    output_path = Path(destination)
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing {output_path}")

    partial = output_path.with_name(output_path.name + ".partial")
    try:
        partial.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        os.replace(partial, output_path)
    except OSError:
        partial.unlink(missing_ok=True)
        raise


def main(argv):
    if len(argv) != 3:
        sys.exit("Usage: python goals_to_logseq.py INPUT.json OUTPUT.md")
    try:
        convert(argv[1], argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"Logseq export failed: {exc}")


if __name__ == "__main__":
    main(sys.argv)
