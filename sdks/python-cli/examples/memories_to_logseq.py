#!/usr/bin/env python3
"""
Convert Omi memories JSON export to a Logseq-format Markdown page.

Unlike memories_markdown.md (YAML frontmatter, one file per memory, aimed at
Obsidian/Notion), this writes a single Logseq *outliner* page: one top-level
block per memory, category and tags as Logseq hashtags (`#category`,
`#tag`), and a page-properties block at the top.

Usage:
    python memories_to_logseq.py memories.json memories.md
"""

import json
import os
import re
import sys
from pathlib import Path

_TAG_UNSAFE = re.compile(r"[^\w-]+")


def logseq_tag(value):
    """Turn *value* into a safe Logseq hashtag (spaces/punctuation -> hyphens).

    Logseq treats `#word` as a page link; a raw category like "personal
    growth" would only link the first word, so multi-word values are
    hyphenated into a single token instead.
    """
    slug = _TAG_UNSAFE.sub("-", str(value).strip()).strip("-")
    return f"#{slug}" if slug else None


def escape_block_text(value):
    """Neutralize Logseq/Markdown link and tag syntax in free-text content.

    `[[`, `]]`, and `#` would otherwise be interpreted as a page link or a
    tag by Logseq anywhere they appear in the text — even mid-sentence, not
    just at a block's start — even though they came from memory content,
    not from us. This keeps untrusted content inert, the same defensive
    intent as the CSV/Excel recipes' formula-injection guards; only the
    hashtags this script appends itself are meant to be real Logseq tags.
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
        if "memories" in items and isinstance(items["memories"], list):
            items = items["memories"]
        elif "data" in items and isinstance(items["data"], list):
            items = items["data"]
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError("Expected a JSON array or object from omi --json memory list")
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each memory must be an object")

    lines = [
        "type:: omi-memories",
        f"count:: {len(items)}",
        "",
    ]

    for item in items:
        category_tag = logseq_tag(item.get("category") or "uncategorized")
        tags_raw = item.get("tags") or []
        tag_tokens = [logseq_tag(t) for t in tags_raw if t] if isinstance(tags_raw, list) else []
        tag_tokens = [t for t in tag_tokens if t]

        hashtags = " ".join([category_tag] + tag_tokens) if category_tag else " ".join(tag_tokens)
        content = escape_block_text(item.get("content"))

        block = f"- {content}" + (f" {hashtags}" if hashtags else "")
        lines.append(block)
        created_at = item.get("created_at")
        if created_at:
            lines.append(f"  created:: {created_at}")
        memory_id = item.get("id")
        if memory_id:
            lines.append(f"  omi-id:: {memory_id}")

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
        sys.exit("Usage: python memories_to_logseq.py INPUT.json OUTPUT.md")
    try:
        convert(argv[1], argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"Logseq export failed: {exc}")


if __name__ == "__main__":
    main(sys.argv)
