#!/usr/bin/env python3
"""Convert Omi memories and facts into Anki-compatible TSV flashcard decks.

Usage:
    python memories_to_anki.py memories.json -o omi_deck.tsv
    omi --json memory list | python memories_to_anki.py - -o anki_cards.txt
    python memories_to_anki.py memories.json -o work_cards.tsv --category work,learnings

Outputs tab-delimited cards formatted for instant File -> Import in Anki
(Spaced Repetition Flashcards), with Front, Back, Deck name, and tags.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def clean_card_text(text: str) -> str:
    """Sanitize card text to prevent layout corruption in Anki."""
    if not text:
        return ""
    # In Anki TSV import, tabs separate fields; newlines within fields become <br>
    cleaned = text.replace("\t", " ").strip()
    cleaned = re.sub(r"\r\n|\r|\n", "<br>", cleaned)
    return cleaned


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


def make_card(item: Dict[str, Any], deck_prefix: str = "Omi::Memories") -> Optional[List[str]]:
    """Generate [Front, Back, Deck, Tags] row for Anki."""
    content = str(item.get("content") or "").strip()
    if not content:
        return None

    cat = str(item.get("category") or "General").strip()
    safe_cat = cat.replace("_", " ").title()
    deck_name = f"{deck_prefix}::{safe_cat}" if safe_cat else deck_prefix

    # Generate front prompt based on category and first words
    preview = content if len(content) <= 60 else content[:57] + "..."
    front = f"<b>{safe_cat} Recall:</b><br>{preview}"
    back = content

    tags_list = ["omi", f"cat:{re.sub(r'[^a-zA-Z0-9_-]', '', safe_cat.lower())}"]
    raw_tags = item.get("tags")
    if isinstance(raw_tags, list):
        for t in raw_tags:
            if t:
                clean_t = re.sub(r"[^a-zA-Z0-9_-]", "", str(t).lower())
                if clean_t:
                    tags_list.append(clean_t)

    return [
        clean_card_text(front),
        clean_card_text(back),
        deck_name,
        " ".join(tags_list),
    ]


def convert_to_anki(
    sources: Sequence[str | Path],
    output_dest: Optional[str | Path] = None,
    category_filter: Optional[str] = None,
    deck_name: str = "Omi::Memories",
) -> int:
    """Convert memories to Anki TSV deck format."""
    all_memories: List[Dict[str, Any]] = []

    for src in sources:
        if str(src) == "-":
            content = sys.stdin.read()
            all_memories.extend(extract_memories(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_memories.extend(extract_memories(content, str(p)))

    filter_cats = {c.strip().lower() for c in category_filter.split(",")} if category_filter else None

    seen_ids = set()
    cards = []
    for mem in all_memories:
        mid = str(mem.get("id"))
        if mid not in seen_ids:
            seen_ids.add(mid)
            if filter_cats:
                cat = str(mem.get("category") or "").strip().lower()
                if cat not in filter_cats:
                    continue
            card = make_card(mem, deck_prefix=deck_name)
            if card:
                cards.append(card)

    buffer = io.StringIO()
    # Write Anki deck headers so Anki auto-configures columns
    buffer.write("#separator:tab\n")
    buffer.write("#html:true\n")
    buffer.write("#deck column:3\n")
    buffer.write("#tags column:4\n")

    writer = csv.writer(buffer, delimiter="\t", lineterminator="\n")
    writer.writerows(cards)
    output_text = buffer.getvalue()

    if output_dest and str(output_dest) != "-":
        out_path = Path(output_dest)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text, encoding="utf-8")
    else:
        sys.stdout.write(output_text)

    return len(cards)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi memories and facts into Anki-compatible TSV flashcard decks."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Input JSON files or '-' for standard input",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Destination TSV file (defaults to stdout)",
    )
    parser.add_argument(
        "-c",
        "--category",
        default=None,
        help="Filter by category (comma-separated, e.g. 'work,learnings')",
    )
    parser.add_argument(
        "--deck",
        default="Omi::Memories",
        help="Base Anki deck name (default: Omi::Memories)",
    )
    args = parser.parse_args()

    try:
        count = convert_to_anki(args.inputs, args.output, category_filter=args.category, deck_name=args.deck)
        if args.output != "-":
            print(f"Exported {count} flashcard(s) to Anki deck at {args.output}", file=sys.stderr)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
