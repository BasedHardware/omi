#!/usr/bin/env python3
"""
Convert Omi action items JSON export to a Logseq-format Markdown page.

Uses Logseq's native task markers (`TODO`/`DONE`) so every item renders as a
real, checkable Logseq task block — distinct from action_items_markdown.md,
which targets Obsidian/Notion with GFM checkboxes and YAML frontmatter.

Usage:
    python action_items_to_logseq.py action_items.json action_items.md
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
    from the item's own description, not from us. This keeps untrusted
    content inert, the same defensive intent as the CSV/Excel recipes'
    formula-injection guards.
    """
    text = str(value) if value is not None else ""
    text = text.replace("[[", "\\[\\[").replace("]]", "\\]\\]")
    text = text.replace("#", "\\#")
    return text.replace("\n", "\n  ")


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
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each action item must be an object")

    lines = [
        "type:: omi-action-items",
        f"count:: {len(items)}",
        "",
    ]

    for item in items:
        completed = bool(item.get("completed"))
        marker = "DONE" if completed else "TODO"
        description = escape_block_text(item.get("description"))
        due_at = item.get("due_at")

        block = f"- {marker} {description}"
        lines.append(block)
        if due_at and not completed:
            due_date = str(due_at).split("T", 1)[0]
            lines.append(f"  DEADLINE: <{due_date}>")
        item_id = item.get("id")
        if item_id:
            lines.append(f"  omi-id:: {item_id}")

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
        sys.exit("Usage: python action_items_to_logseq.py INPUT.json OUTPUT.md")
    try:
        convert(argv[1], argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"Logseq export failed: {exc}")


if __name__ == "__main__":
    main(sys.argv)
