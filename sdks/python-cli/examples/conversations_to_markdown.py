#!/usr/bin/env python3
"""Export Omi conversations to Markdown files.

Reads a JSON file (or stdin via ``-``) containing a list of conversation
objects and writes one Markdown file per conversation into the output
directory.  Title slugs are derived from the ``structured.title`` field;
fallback titles and overviews are taken from the same object.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


def slugify(text: str) -> str:
    """Return a filesystem-safe slug derived from *text*."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s]+", "-", text)
    return text or "untitled"


def read_input(source: str) -> list[dict]:
    """Read and return the JSON list from *source*."""
    if source == "-":
        raw = sys.stdin.buffer.read()
        text = raw.decode("utf-8-sig")
        return json.loads(text)
    path = Path(source)
    with path.open("r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def export_conversations(
    conversations: list[dict],
    output_dir: Path,
) -> None:
    """Write each conversation as a Markdown file inside *output_dir*."""
    output_dir.mkdir(parents=True, exist_ok=True)

    for conv in conversations:
        structured = conv.get("structured") or {}
        title = structured.get("title", "untitled")
        overview = structured.get("overview", "")
        conv_id = conv.get("id", slugify(title))

        slug = slugify(title)
        filename = f"{slug}.md"
        filepath = output_dir / filename

        lines = [f"# {title}", ""]
        if overview:
            lines.append(overview)
            lines.append("")

        filepath.write_text("\n".join(lines), encoding="utf-8")

        print(f"Exported: {filepath}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export Omi conversations to Markdown files."
    )
    parser.add_argument(
        "source",
        help="Path to JSON file containing conversations, or ``-`` for stdin.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("notes"),
        help="Directory in which to write the Markdown files (default: notes).",
    )
    args = parser.parse_args()

    conversations = read_input(args.source)
    export_conversations(conversations, args.output_dir)


if __name__ == "__main__":
    main()
