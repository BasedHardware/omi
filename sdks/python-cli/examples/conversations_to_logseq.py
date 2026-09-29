#!/usr/bin/env python3
"""
Convert Omi conversations JSON export to a Logseq-format Markdown page.

Each conversation becomes a top-level outliner block titled from its
`structured` summary, tagged by category, with the overview and date/id as
block properties — distinct from conversations_markdown.md, which targets
Obsidian/Notion with YAML frontmatter and per-conversation files.

Usage:
    python conversations_to_logseq.py conversations.json conversations.md
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
    from the conversation's own title/overview, not from us.
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
        if "conversations" in items and isinstance(items["conversations"], list):
            items = items["conversations"]
        elif "data" in items and isinstance(items["data"], list):
            items = items["data"]
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError("Expected a JSON array or object from omi --json conversation list")
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each conversation must be an object")

    lines = [
        "type:: omi-conversations",
        f"count:: {len(items)}",
        "",
    ]

    for item in items:
        structured = item.get("structured") if isinstance(item.get("structured"), dict) else {}
        title = escape_block_text(structured.get("title") or "Untitled conversation")
        category = structured.get("category")
        overview = structured.get("overview")
        category_tag = logseq_tag(category) if category else None

        block = f"- {title} {category_tag}" if category_tag else f"- {title}"
        lines.append(block)
        date = item.get("started_at") or item.get("created_at")
        if date:
            lines.append(f"  date:: {date}")
        conv_id = item.get("id")
        if conv_id:
            lines.append(f"  omi-id:: {conv_id}")
        if overview:
            # A nested child block rather than a property: overviews are
            # prose, not a short key-value fact, so they read more like a
            # normal Logseq outline entry under the conversation.
            lines.append(f"  - {escape_block_text(overview)}")

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
        sys.exit("Usage: python conversations_to_logseq.py INPUT.json OUTPUT.md")
    try:
        convert(argv[1], argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"Logseq export failed: {exc}")


if __name__ == "__main__":
    main(sys.argv)
