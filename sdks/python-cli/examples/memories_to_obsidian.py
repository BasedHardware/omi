#!/usr/bin/env python3
"""Convert Omi memories into an Obsidian knowledge vault with Map of Content (MOC) and wikilinks.

Usage:
    python memories_to_obsidian.py memories.json -o ./ObsidianVault/
    omi --json memory list | python memories_to_obsidian.py - -o ~/Documents/SecondBrain/
    python memories_to_obsidian.py memories.json -o ./Vault/ --vault-name "Omi Mind"

Generates an interconnected Obsidian knowledge vault including:
- Index.md (Map of Content with category hubs and statistics)
- Individual atomic concept notes per memory with frontmatter and [[WikiLinks]]
- Category index notes linking related memories
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set


def slugify(text: str) -> str:
    """Create a safe filename slug."""
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text.strip("_") or "untitled"


def extract_memories(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON content and extract a list of memory dictionaries."""
    raw = content.lstrip("\ufeff")
    items = json.loads(raw)

    if isinstance(items, dict):
        for key in ("memories", "items", "data"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError(f"{source_label}: expected a JSON array or wrapped memories object")

    results: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source_label}: each memory must be a JSON object")
        if not item.get("id") or str(item.get("id")).strip() == "":
            raise ValueError(f"{source_label}: memory missing required 'id' field")
        results.append(item)

    return results


def build_obsidian_vault(
    sources: Sequence[str | Path],
    vault_dir: str | Path,
    vault_name: str = "Omi Knowledge Base",
) -> int:
    """Generate an Obsidian vault directory structure from memory exports."""
    all_memories: List[Dict[str, Any]] = []

    for src in sources:
        if str(src) == "-":
            content = sys.stdin.read()
            all_memories.extend(extract_memories(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_memories.extend(extract_memories(content, str(p)))

    out_dir = Path(vault_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    notes_dir = out_dir / "Memories"
    notes_dir.mkdir(parents=True, exist_ok=True)
    categories_dir = out_dir / "Categories"
    categories_dir.mkdir(parents=True, exist_ok=True)

    seen_ids = set()
    category_map: Dict[str, List[Dict[str, Any]]] = {}

    total_exported = 0
    for mem in all_memories:
        mid = str(mem.get("id"))
        if mid in seen_ids:
            continue
        seen_ids.add(mid)

        content = str(mem.get("content") or "").strip()
        cat = str(mem.get("category") or "General").strip().title()
        category_map.setdefault(cat, []).append(mem)

        # Generate atomic note
        title_snippet = content[:40].strip() if content else "Memory"
        note_name = f"{slugify(title_snippet)}_{mid[:6]}.md"
        note_path = notes_dir / note_name

        tags = ["omi", f"cat/{slugify(cat)}"]
        if isinstance(mem.get("tags"), list):
            for t in mem["tags"]:
                cleaned_tag = re.sub(r"[^\w-]", "", str(t).lower())
                if cleaned_tag:
                    tags.append(cleaned_tag)

        note_body = [
            "---",
            f"id: \"{mid}\"",
            f"category: \"[[{cat}]]\"",
            f"created: \"{mem.get('created_at') or ''}\"",
            "tags:",
        ]
        for t in tags:
            note_body.append(f"  - {t}")
        note_body.extend([
            "---",
            "",
            f"# {content[:60]}",
            "",
            content,
            "",
            "---",
            f"**Related Hub**: [[{cat}]] | **Vault Index**: [[Index|Map of Content]]",
        ])

        note_path.write_text("\n".join(note_body), encoding="utf-8")
        total_exported += 1

    # Generate Category Hub Notes
    for cat_name, cat_items in category_map.items():
        cat_file = categories_dir / f"{cat_name}.md"
        cat_lines = [
            "---",
            f"type: category-hub",
            f"category: \"{cat_name}\"",
            f"total_memories: {len(cat_items)}",
            "---",
            "",
            f"# 📁 {cat_name} Hub",
            "",
            f"Collection of **{len(cat_items)}** recorded memories and insights in category *{cat_name}*.",
            "",
            "## Notes",
            "",
        ]
        for it in cat_items:
            mid = str(it.get("id"))
            text_snip = str(it.get("content") or "")[:50].replace("\n", " ")
            note_ref = f"{slugify(text_snip)}_{mid[:6]}"
            cat_lines.append(f"- [[{note_ref}|{text_snip}]]")
        cat_lines.extend([
            "",
            "---",
            "[[Index|Back to Map of Content]]",
        ])
        cat_file.write_text("\n".join(cat_lines), encoding="utf-8")

    # Generate Index (Map of Content)
    index_file = out_dir / "Index.md"
    index_lines = [
        "---",
        "type: moc",
        f"vault_name: \"{vault_name}\"",
        f"total_memories: {total_exported}",
        f"total_categories: {len(category_map)}",
        "---",
        "",
        f"# 🧠 {vault_name}",
        "",
        f"> **Vault Statistics:** {total_exported} atomic notes across {len(category_map)} knowledge categories.",
        "",
        "## Knowledge Categories",
        "",
    ]
    for cat_name, items in sorted(category_map.items()):
        index_lines.append(f"- [[{cat_name}]] ({len(items)} notes)")
    index_lines.extend([
        "",
        "## Recent Notes",
        "",
    ])
    for mem in all_memories[:15]:
        mid = str(mem.get("id"))
        snip = str(mem.get("content") or "")[:50].replace("\n", " ")
        ref = f"{slugify(snip)}_{mid[:6]}"
        index_lines.append(f"- [[{ref}|{snip}]]")
    index_lines.append("")

    index_file.write_text("\n".join(index_lines), encoding="utf-8")

    return total_exported


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi memories into an Obsidian knowledge vault with Map of Content and wikilinks."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Input JSON files or '-' for standard input",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Target folder to build the Obsidian vault",
    )
    parser.add_argument(
        "--vault-name",
        default="Omi Knowledge Base",
        help="Custom title for the Vault Index (default: Omi Knowledge Base)",
    )
    args = parser.parse_args()

    try:
        count = build_obsidian_vault(args.inputs, args.output, vault_name=args.vault_name)
        print(f"Generated Obsidian vault with {count} memory notes at {args.output}", file=sys.stderr)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
