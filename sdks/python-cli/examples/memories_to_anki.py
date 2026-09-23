#!/usr/bin/env python3
"""
Convert Omi memories JSON exports into Anki-compatible TSV flashcard files for spaced repetition.

Usage:
    # Pipe directly from omi CLI
    omi --json memory list | python memories_to_anki.py - --output omi_flashcards.tsv

    # Convert from a saved JSON file
    python memories_to_anki.py memories.json --output omi_flashcards.tsv

    # Filter by category and add custom deck name
    python memories_to_anki.py memories.json --output omi_flashcards.tsv --category learnings,work --deck "Omi::Knowledge"

    # Export with tags column and specific front template
    python memories_to_anki.py memories.json --output omi_flashcards.tsv --tags --template prompt
"""

import argparse
import csv
import io
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure UTF-8 output on all platforms
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    elif hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")



CATEGORY_PROMPTS: Dict[str, str] = {
    "work": "Work Context & Project Insight",
    "skills": "Skill & Technical Proficiency",
    "learnings": "Key Learning & Principle",
    "interests": "Topic of Interest",
    "habits": "Habit & Routine",
    "lifestyle": "Lifestyle Preference",
    "hobbies": "Hobby & Creative Pursuit",
    "core": "Core Personal Fact",
    "interesting": "Interesting Fact & Observation",
    "manual": "Saved Note & Insight",
    "workflow": "Workflow & Process Rule",
    "system": "System Configuration & Rule",
    "other": "Knowledge Fact",
}


def parse_datetime(iso_str: Optional[str]) -> Optional[datetime]:
    """Safely parse an ISO-8601 datetime string and normalize to UTC."""
    if not iso_str or not isinstance(iso_str, str):
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception:
        return None


def sanitize_field(text: str) -> str:
    """Sanitize text field for TSV/Anki export: replace newlines with <br> and remove tabs."""
    if not text:
        return ""
    # Normalize carriage returns and newlines to HTML break for Anki multiline cards
    cleaned = text.replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")
    # Tabs are TSV delimiters in Anki, replace with 4 spaces
    cleaned = cleaned.replace("\t", "    ")
    return cleaned.strip()


def normalize_tag(tag: str) -> str:
    """Normalize a string to a valid Anki tag (no spaces or special punctuation)."""
    if not tag:
        return ""
    # Replace spaces and illegal characters with underscores/hyphens
    clean = re.sub(r"[^\w-]", "_", tag.strip())
    clean = re.sub(r"_+", "_", clean).strip("_")
    return clean


def format_front_prompt(item: Dict[str, Any], template: str = "category") -> str:
    """Generate the Front of the flashcard based on category or content hints."""
    cat = str(item.get("category") or "").strip().lower()
    prompt_hint = CATEGORY_PROMPTS.get(cat, "Personal Knowledge & Memory")
    content = str(item.get("content") or "").strip()

    created_dt = parse_datetime(item.get("created_at"))
    date_str = f" ({created_dt.strftime('%b %Y')})" if created_dt else ""

    if template == "prompt":
        # Question style prompt
        if cat in ("learnings", "skills"):
            return f"What key insight was recorded regarding: {prompt_hint}{date_str}?"
        if cat == "work":
            return f"What context/rule was documented for: {prompt_hint}{date_str}?"
        return f"Recall the details for: {prompt_hint}{date_str}"
    elif template == "cloze":
        # First sentence or summary prompt
        first_line = content.split("\n")[0]
        if len(first_line) > 60:
            first_line = first_line[:57] + "..."
        return f"[{prompt_hint}] {first_line}"
    else:
        # Default: clean category label with date badge
        cat_label = cat.replace("_", " ").title() if cat else "General"
        return f"Omi Memory - {cat_label}{date_str}"


def extract_tags(item: Dict[str, Any], extra_tags: Optional[List[str]] = None) -> str:
    """Collect and format space-separated Anki tags for a memory item."""
    tags_set: List[str] = ["omi_memory"]

    cat = str(item.get("category") or "").strip().lower()
    if cat:
        tags_set.append(f"category::{normalize_tag(cat)}")

    raw_tags = item.get("tags")
    if isinstance(raw_tags, list):
        for t in raw_tags:
            norm = normalize_tag(str(t))
            if norm and norm not in tags_set:
                tags_set.append(norm)

    if extra_tags:
        for t in extra_tags:
            norm = normalize_tag(str(t))
            if norm and norm not in tags_set:
                tags_set.append(norm)

    return " ".join(tags_set)


def memory_to_card(
    item: Dict[str, Any],
    template: str = "category",
    include_tags: bool = True,
    deck: Optional[str] = None,
    extra_tags: Optional[List[str]] = None,
) -> List[str]:
    """Convert a single memory item to a list of TSV column values for Anki."""
    content = str(item.get("content") or "").strip()
    if not content:
        return []

    front = sanitize_field(format_front_prompt(item, template=template))
    back = sanitize_field(content)

    row = [front, back]

    if include_tags:
        tags_str = extract_tags(item, extra_tags=extra_tags)
        row.append(tags_str)

    return row


def parse_input(source: str) -> List[Dict[str, Any]]:
    """Load and extract memory items from stdin or file."""
    if source == "-":
        raw_text = sys.stdin.read()
    else:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {source}")
        raw_text = path.read_text(encoding="utf-8")

    if not raw_text.strip():
        return []

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as err:
        raise ValueError(f"Invalid JSON data: {err}")

    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    elif isinstance(data, dict):
        if "memories" in data and isinstance(data["memories"], list):
            return [x for x in data["memories"] if isinstance(x, dict)]
        if "data" in data and isinstance(data["data"], list):
            return [x for x in data["data"] if isinstance(x, dict)]
        return [data]
    return []


def write_anki_tsv(
    cards: List[List[str]],
    output_path: Optional[str] = None,
    deck: Optional[str] = None,
    include_tags: bool = True,
) -> Tuple[int, Optional[str]]:
    """Write cards to standard Anki TSV file with atomic file replacement if writing to disk."""
    header_comments = [
        "#separator:tab",
        "#html:true",
    ]
    if deck:
        header_comments.append(f"#deck:{deck}")
    if include_tags:
        header_comments.append("#tags column:3")

    lines: List[str] = []
    lines.extend(header_comments)
    for card in cards:
        if card:
            lines.append("\t".join(card))

    output_content = "\n".join(lines) + "\n"

    if not output_path or output_path == "-":
        sys.stdout.write(output_content)
        return len(cards), None

    dest = Path(output_path).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write pattern
    temp_fd, temp_file_path = tempfile.mkstemp(
        dir=dest.parent,
        prefix=f".{dest.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(output_content)
        os.replace(temp_file_path, dest)
    except Exception:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise

    return len(cards), str(dest)


def filter_memories(
    memories: List[Dict[str, Any]],
    categories: Optional[Set[str]] = None,
    exclude_private: bool = False,
) -> List[Dict[str, Any]]:
    """Filter memory records by category and visibility."""
    filtered: List[Dict[str, Any]] = []
    for m in memories:
        if not isinstance(m, dict):
            continue
        if exclude_private:
            vis = str(m.get("visibility") or "").strip().lower()
            if vis == "private":
                continue
        if categories:
            cat = str(m.get("category") or "").strip().lower()
            if cat not in categories:
                continue
        filtered.append(m)
    return filtered


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi memories JSON exports into Anki-compatible TSV flashcards.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input",
        help="Input JSON file or '-' to read from stdin (e.g. 'omi --json memory list | python memories_to_anki.py -')",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output .tsv file path. If omitted or '-', output is written to stdout.",
        default=None,
    )
    parser.add_argument(
        "--deck",
        help="Anki deck name (e.g. 'Omi::Memories' or 'Knowledge::Learnings').",
        default=None,
    )
    parser.add_argument(
        "--category",
        help="Comma-separated list of categories to include (e.g. 'learnings,skills,work').",
        default=None,
    )
    parser.add_argument(
        "--template",
        choices=["category", "prompt", "cloze"],
        default="category",
        help="Front of card styling: 'category' (default badge), 'prompt' (question), 'cloze' (summary lead).",
    )
    parser.add_argument(
        "--no-tags",
        action="store_true",
        help="Omit the tags column from the TSV output.",
    )
    parser.add_argument(
        "--tag",
        action="append",
        help="Extra tag to apply to all exported cards (can be specified multiple times).",
    )
    parser.add_argument(
        "--exclude-private",
        action="store_true",
        help="Exclude memories marked with private visibility.",
    )

    args = parser.parse_args()

    try:
        raw_memories = parse_input(args.input)
    except Exception as err:
        sys.stderr.write(f"Error reading input: {err}\n")
        return 1

    cats = None
    if args.category:
        cats = {c.strip().lower() for c in args.category.split(",") if c.strip()}

    memories = filter_memories(raw_memories, categories=cats, exclude_private=args.exclude_private)

    include_tags = not args.no_tags
    cards: List[List[str]] = []
    for m in memories:
        card = memory_to_card(
            m,
            template=args.template,
            include_tags=include_tags,
            deck=args.deck,
            extra_tags=args.tag,
        )
        if card:
            cards.append(card)

    try:
        count, path = write_anki_tsv(
            cards,
            output_path=args.output,
            deck=args.deck,
            include_tags=include_tags,
        )
        if path:
            sys.stderr.write(f"Successfully exported {count} memory flashcards to {path}\n")
    except Exception as err:
        sys.stderr.write(f"Error writing Anki TSV: {err}\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
