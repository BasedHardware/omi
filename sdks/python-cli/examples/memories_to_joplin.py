#!/usr/bin/env python3
"""Convert Omi memory JSON exports to Joplin-compatible Markdown notes or JEX archive.

Reads Omi memory JSON exports (from file paths or stdin), deduplicates by memory ID,
and generates clean, Joplin-ready Markdown notes with YAML frontmatter headers
or packages them into a portable .jex (Joplin Export) archive.

Joplin is a popular open-source, offline-first, cross-platform note-taking app.

Zero external dependencies - uses Python 3 standard library only (including tarfile).
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple


def sanitize_filename(name: str) -> str:
    """Sanitize string for safe filesystem filename across OSes."""
    cleaned = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned[:80] or "untitled_memory"


def parse_memories_data(raw: Any) -> List[Dict[str, Any]]:
    """Unwrap Omi memories from raw JSON input supporting common CLI shapes."""
    if isinstance(raw, str):
        data = json.loads(raw)
    else:
        data = raw

    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    elif isinstance(data, dict):
        for key in ("memories", "items", "data", "result"):
            val = data.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]
        return [data]
    return []


def format_memory_for_joplin(item: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize raw memory dictionary into canonical record schema."""
    mid = str(item.get("id") or item.get("uid") or "").strip()
    if not mid:
        raise ValueError("Memory record missing required 'id' field")

    content = ""
    title = ""
    structured = item.get("structured")
    if isinstance(structured, dict):
        title = structured.get("title") or ""
        content = structured.get("overview") or structured.get("title") or ""
    if not content:
        content = item.get("content") or item.get("text") or item.get("transcript") or ""
    if not title:
        first_line = content.strip().splitlines()[0] if content.strip() else "Omi Memory"
        title = first_line[:60]

    category = item.get("category")
    if not category and isinstance(structured, dict):
        category = structured.get("category")

    tags: List[str] = []
    raw_tags = item.get("tags")
    if isinstance(raw_tags, list):
        tags = [str(t).strip() for t in raw_tags if str(t).strip()]
    elif isinstance(raw_tags, str) and raw_tags.strip():
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]

    visibility = item.get("visibility")

    return {
        "id": mid,
        "title": title,
        "content": content,
        "category": category,
        "tags": tags,
        "visibility": visibility,
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }


def escape_yaml_string(val: str) -> str:
    """Format and escape string for YAML double-quoted scalar."""
    escaped = str(val).replace("\\", "\\\\").replace('"', '\\"')
    return '"' + escaped + '"'


def render_joplin_markdown(rec: Dict[str, Any], notebook: str = "Omi Memories") -> str:
    """Render a single memory record into standard Joplin Markdown note with frontmatter."""
    created_str = rec.get("created_at") or datetime.now(timezone.utc).isoformat()
    updated_str = rec.get("updated_at") or created_str
    tags = rec.get("tags") or []
    category = rec.get("category") or "general"

    frontmatter_lines = [
        "---",
        f"id: {escape_yaml_string(rec['id'])}",
        f"title: {escape_yaml_string(rec['title'])}",
        f"notebook: {escape_yaml_string(notebook)}",
        f"category: {escape_yaml_string(category)}",
        f"created: {escape_yaml_string(created_str)}",
        f"updated: {escape_yaml_string(updated_str)}",
        "source: \"omi-wearable\"",
    ]

    if tags:
        frontmatter_lines.append("tags:")
        for t in tags:
            frontmatter_lines.append(f"  - {escape_yaml_string(t)}")
    else:
        frontmatter_lines.append("tags: []")

    frontmatter_lines.append("---")
    frontmatter_lines.append("")
    frontmatter_lines.append(f"# {rec['title']}")
    frontmatter_lines.append("")
    frontmatter_lines.append(rec["content"].strip())
    frontmatter_lines.append("")

    return "\n".join(frontmatter_lines)


def process_memories_to_joplin(
    inputs: Sequence[str],
    notebook_name: str = "Omi Memories",
) -> Tuple[List[Tuple[str, str]], int]:
    """Load, deduplicate by ID, and generate (filename, markdown_content) pairs."""
    dedup: Dict[str, Dict[str, Any]] = {}

    for inp in inputs:
        if inp == "-":
            raw_content = sys.stdin.read()
        else:
            p = Path(inp)
            if not p.is_file():
                raise FileNotFoundError(f"Input file not found: {inp}")
            raw_content = p.read_bytes().decode("utf-8-sig")

        memories = parse_memories_data(raw_content)
        for m in memories:
            mid = str(m.get("id") or m.get("uid") or "").strip()
            if mid and mid not in dedup:
                dedup[mid] = m

    normalized = [format_memory_for_joplin(m) for m in dedup.values()]
    notes: List[Tuple[str, str]] = []

    for rec in normalized:
        clean_title = sanitize_filename(rec["title"])
        filename = f"{clean_title}_{rec['id'][:8]}.md"
        content = render_joplin_markdown(rec, notebook=notebook_name)
        notes.append((filename, content))

    return notes, len(normalized)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi memory JSON exports to Joplin-compatible Markdown notes or JEX archive.",
        epilog="""\
examples:
  omi --json memory list --limit 100 | python memories_to_joplin.py - -o notes_dir/
  python memories_to_joplin.py memories.json -o memories.jex
  python memories_to_joplin.py export.json -o joplin_notes/ --notebook-name "Wearable Thoughts"
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "inputs",
        metavar="INPUT",
        nargs="+",
        help="Path(s) to Omi memory JSON file(s), or '-' to read from standard input.",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="DEST",
        required=True,
        help="Destination directory (for Markdown notes) or .jex file path.",
    )
    parser.add_argument(
        "--notebook-name",
        default="Omi Memories",
        help="Target Joplin notebook name in metadata (default: Omi Memories).",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite destination directory/file if it already exists.",
    )

    args = parser.parse_args()
    dest_path = Path(args.output)

    is_jex = dest_path.suffix.lower() == ".jex"

    if dest_path.exists() and not args.force:
        sys.stderr.write(
            f"Error: Output destination already exists: {args.output} (use --force to overwrite)\n"
        )
        sys.exit(1)

    try:
        notes, count = process_memories_to_joplin(args.inputs, notebook_name=args.notebook_name)
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)

    if is_jex:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(dest_path, "w") as tar:
            for filename, md_content in notes:
                data = md_content.encode("utf-8")
                ti = tarfile.TarInfo(name=filename)
                ti.size = len(data)
                ti.mtime = int(time.time())
                tar.addfile(ti, io.BytesIO(data))
        sys.stderr.write(
            f"Successfully generated Joplin JEX archive: {args.output} ({count} notes)\n"
        )
    else:
        dest_path.mkdir(parents=True, exist_ok=True)
        for filename, md_content in notes:
            note_file = dest_path / filename
            note_file.write_text(md_content, encoding="utf-8")
        sys.stderr.write(
            f"Successfully generated Joplin Markdown notes directory: {args.output} ({count} notes)\n"
        )


if __name__ == "__main__":
    main()
