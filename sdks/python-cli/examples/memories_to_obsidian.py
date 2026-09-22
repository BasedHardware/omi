#!/usr/bin/env python3
"""
memories_to_obsidian.py

A small utility that converts a JSON export of OMI memories into a set of
Obsidian‑compatible markdown files.

Each memory is written to its own ``.md`` file inside the target vault directory.
The file contains a YAML front‑matter block with the most common metadata
(title, tags, created date) followed by the raw content.  Any occurrence of a
memory title inside the content is automatically turned into an Obsidian wikilink
(`[[Title]]`).

The script is deliberately defensive:
* All I/O errors are caught and reported with a clear message.
* JSON parsing errors are surfaced as ``ValueError`` with context.
* Files are written atomically – a temporary file is created first and then
  renamed to its final destination, guaranteeing that partially‑written files
  never appear in the vault.

Typical usage::

    python memories_to_obsidian.py \\
        --input memories.json \\
        --output /path/to/obsidian/vault

"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Mapping, Sequence

# --------------------------------------------------------------------------- #
# Helper utilities
# --------------------------------------------------------------------------- #


def _load_memories(path: Path) -> List[Mapping[str, object]]:
    """
    Load a list of memory objects from a JSON file.

    The JSON file must contain a top‑level array where each element is a mapping
    with at least the following keys:

    * ``id`` (optional) – a unique identifier.
    * ``title`` – the human readable title.
    * ``content`` – the body text.
    * ``tags`` – a list of strings (optional).
    * ``created_at`` – an ISO‑8601 timestamp (optional).

    Parameters
    ----------
    path:
        Path to the JSON file.

    Returns
    -------
    List[Mapping[str, object]]
        The parsed memory objects.

    Raises
    ------
    FileNotFoundError
        If ``path`` does not exist.
    ValueError
        If the file cannot be decoded as JSON or does not contain the expected
        structure.
    """
    if not path.is_file():
        raise FileNotFoundError(f"Memory export not found: {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

    if not isinstance(raw, list):
        raise ValueError(f"Expected a JSON array at top level in {path}")

    for idx, mem in enumerate(raw):
        if not isinstance(mem, dict):
            raise ValueError(f"Memory entry #{idx} is not an object")
        if "title" not in mem or "content" not in mem:
            raise ValueError(
                f"Memory entry #{idx} missing required fields 'title' or 'content'"
            )
    return raw  # type: ignore[return-value]


def _slugify(title: str) -> str:
    """
    Produce a filesystem‑safe filename from a memory title.

    The implementation is intentionally simple – it replaces path separators,
    strips surrounding whitespace and substitutes any remaining unsafe
    characters with an underscore.

    Parameters
    ----------
    title:
        The original title.

    Returns
    -------
    str
        A safe filename (without extension).
    """
    unsafe = r'<>:"/\\|?*'
    cleaned = "".join("_" if c in unsafe else c for c in title.strip())
    # Collapse consecutive underscores and limit length
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned[:200]  # guard against extremely long titles


def _format_frontmatter(mem: Mapping[str, object]) -> str:
    """
    Render a YAML front‑matter block for a single memory.

    Only a subset of fields is emitted – enough for typical Obsidian usage.

    Parameters
    ----------
    mem:
        The memory mapping.

    Returns
    -------
    str
        The front‑matter string (including the leading and trailing ``---``).
    """
    title = mem.get("title", "")
    tags = mem.get("tags", [])
    created = mem.get("created_at")
    if created:
        try:
            # Normalise to ISO‑8601 date only
            created_dt = datetime.fromisoformat(str(created))
            created_str = created_dt.date().isoformat()
        except Exception:
            created_str = str(created)
    else:
        created_str = datetime.now().date().isoformat()

    # Ensure tags is a list of strings
    if not isinstance(tags, Sequence):
        tags = []
    tags_list = [str(t) for t in tags]

    front = [
        "---",
        f"title: {title}",
        f"date: {created_str}",
    ]
    if tags_list:
        front.append(f"tags: [{', '.join(tags_list)}]")
    front.append("---")
    return "\n".join(front)


def _replace_wikilinks(content: str, title_map: Mapping[str, str]) -> str:
    """
    Replace plain occurrences of known titles with Obsidian wikilinks.

    The replacement is naïve but works well for short titles that appear as
    whole words.  It does **not** attempt to handle overlapping titles or
    markdown code blocks.

    Parameters
    ----------
    content:
        The original markdown body.
    title_map:
        Mapping from original title to the wikilink target (usually the same
        title).

    Returns
    -------
    str
        The content with wikilinks inserted.
    """
    # Sort by length descending to avoid partial replacement of a longer title
    for title in sorted(title_map.keys(), key=len, reverse=True):
        safe = title_map[title]
        # Simple word‑boundary replacement
        content = content.replace(title, f"[[{safe}]]")
    return content


def export_memories_to_obsidian(
    input_path: Path, output_dir: Path
) -> List[Path]:
    """
    Convert a JSON memory export into a set of markdown files suitable for an
    Obsidian vault.

    Parameters
    ----------
    input_path:
        Path to the JSON file containing the memories.
    output_dir:
        Directory that will receive the generated ``.md`` files.  It is created
        if it does not already exist.

    Returns
    -------
    List[Path]
        Paths of the markdown files that were written.

    Raises
    ------
    Exception
        Propagates any I/O or parsing errors with a helpful message.
    """
    memories = _load_memories(input_path)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Build a quick lookup for wikilink replacement
    title_to_wikilink = {mem["title"]: mem["title"] for mem in memories}

    written_files: List[Path] = []

    for mem in memories:
        title: str = str(mem["title"])
        slug = _slugify(title)
        target_path = output_dir / f"{slug}.md"

        frontmatter = _format_frontmatter(mem)
        body = str(mem.get("content", ""))
        body = _replace_wikilinks(body, title_to_wikilink)

        full_content = f"{frontmatter}\n\n{body}\n"

        # Write atomically
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                delete=False,
                dir=output_dir,
                suffix=".md.tmp",
            ) as tmp:
                tmp.write(full_content)
                temp_path = Path(tmp.name)
            # On POSIX rename is atomic
            temp_path.replace(target_path)
            written_files.append(target_path)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to write memory '{title}' to {target_path}: {exc}"
            ) from exc

    return written_files


# --------------------------------------------------------------------------- #
# CLI entry point
# --------------------------------------------------------------------------- #


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export OMI memories to an Obsidian vault as markdown files."
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        type=Path,
        help="Path to the JSON file containing the memory export.",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        type=Path,
        help="Directory that will receive the generated markdown files.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    try:
        files = export_memories_to_obsidian(args.input, args.output)
        print(f"✅ Exported {len(files)} memories to {args.output}")
        return 0
    except Exception as exc:  # pragma: no cover – top‑level error handling
        print(f"❌ Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
