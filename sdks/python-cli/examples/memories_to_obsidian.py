#!/usr/bin/env python3
"""
Export memories to an Obsidian vault.

This script reads a JSON file containing an array of memories and writes each
memory as a Markdown file in the specified Obsidian vault. Each file contains
YAML frontmatter with the memory title, date, and tags, followed by the
memory content. The script writes to a temporary file first and then atomically
renames it to avoid partial writes.

Usage:
    python memories_to_obsidian.py --input memories.json --vault /path/to/vault
"""

import argparse
import json
import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

log = logging.getLogger(__name__)


def _parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export memories to an Obsidian vault."
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        type=Path,
        help="Path to the JSON file containing memories.",
    )
    parser.add_argument(
        "--vault",
        "-v",
        required=True,
        type=Path,
        help="Path to the root of the Obsidian vault.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without writing files.",
    )
    return parser.parse_args(argv)


def _load_memories(path: Path) -> List[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("Memories JSON must be a list of objects.")
        return data
    except Exception as exc:
        log.exception("Failed to load memories from %s", path)
        raise RuntimeError(f"Could not load memories: {exc}") from exc


def _sanitize_filename(name: str) -> str:
    """
    Convert a string into a safe filename for Obsidian.
    """
    # Replace spaces with underscores and remove problematic characters
    return "".join(c if c.isalnum() or c in (" ", "_") else "_" for c in name).replace(
        " ", "_"
    )


def _memory_to_markdown(mem: Dict[str, Any]) -> str:
    title = mem.get("title", "Untitled")
    date_str = mem.get("date")
    try:
        date = datetime.fromisoformat(date_str) if date_str else datetime.now()
    except Exception:
        date = datetime.now()
    tags = mem.get("tags", [])
    content = mem.get("content", "")

    frontmatter = {
        "title": title,
        "date": date.isoformat(),
        "tags": tags,
    }

    fm_lines = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, list):
            fm_lines.append(f"{key}: {json.dumps(value)}")
        else:
            fm_lines.append(f"{key}: {value}")
    fm_lines.append("---\n")

    # Convert tags to wikilinks
    tag_links = " ".join(f"[[{tag}]]" for tag in tags)

    md = "\n".join(fm_lines) + content + "\n\n" + tag_links + "\n"
    return md


def _write_atomic(path: Path, content: str, dry_run: bool = False) -> None:
    if dry_run:
        log.info("[DRY-RUN] Would write to %s", path)
        return

    tmp_path = path.with_suffix(".tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as f:
            f.write(content)
        # Ensure the directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic rename
        tmp_path.replace(path)
        log.info("Wrote %s", path)
    except Exception as exc:
        log.exception("Failed to write %s", path)
        raise RuntimeError(f"Could not write file {path}: {exc}") from exc


def main(argv: List[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    memories = _load_memories(args.input)

    for mem in memories:
        title = mem.get("title", "Untitled")
        filename = _sanitize_filename(title) + ".md"
        target_path = args.vault / filename
        md_content = _memory_to_markdown(mem)
        _write_atomic(target_path, md_content, dry_run=args.dry_run)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log.error("Unhandled error: %s", exc)
        sys.exit(1)
