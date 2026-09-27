"""Convert Omi memories JSON exports to Anki flashcards TSV format.

See memories_anki.md for the full recipe and Anki import instructions.

Usage:
    omi --json memory list --limit 200 > memories.json
    python memories_to_anki.py anki_deck.tsv memories.json
    python memories_to_anki.py --category learnings --prompt "What insight did I capture about {category}?" deck.tsv memories.json
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


def clean_text(value: Any) -> str:
    """Normalize text whitespace and return cleaned string or empty string."""
    if value is None:
        return ""
    if not isinstance(value, str):
        text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    else:
        text = value
    # Replace tabs and newlines with spaces to preserve TSV column separation
    return " ".join(text.replace("\t", " ").split())


def clean_tag(value: Any) -> str:
    """Normalize tag string for Anki (replace spaces with underscores, clean whitespace)."""
    text = clean_text(value)
    return text.replace(" ", "_")


def parse_time(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None if unusable."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_memories(sources: Sequence[str]) -> List[Dict[str, Any]]:
    """Load and deduplicate memories from multiple JSON sources or envelopes."""
    mem_map: OrderedDict[str, Dict[str, Any]] = OrderedDict()
    for source in sources:
        path = Path(source)
        content = path.read_bytes().decode("utf-8-sig")
        payload = json.loads(content)

        if isinstance(payload, dict):
            found_key = None
            for key in ("memories", "items", "data", "results"):
                if key in payload:
                    found_key = key
                    break
            if found_key is not None:
                items = payload[found_key]
            elif "id" in payload or "content" in payload:
                items = [payload]
            else:
                raise ValueError(f"{source}: expected JSON array or object containing memories")
        elif isinstance(payload, list):
            items = payload
        else:
            raise ValueError(f"{source}: expected JSON array or object containing memories")

        if not isinstance(items, list):
            raise ValueError(f"{source}: memories payload must be a JSON array")

        for raw in items:
            if not isinstance(raw, dict):
                raise ValueError(f"{source}: each memory entry must be a JSON object")
            mem_id = raw.get("id")
            if mem_id is None or str(mem_id).strip() == "":
                raise ValueError(f"{source}: memory item missing non-empty string 'id'")
            mem_map[str(mem_id)] = raw

    return list(mem_map.values())


def format_anki_card(
    raw: Dict[str, Any],
    prompt_template: str = "What did I record regarding {category}?",
) -> Tuple[str, str, str]:
    """Format single memory into (Front, Back, Tags) tuple for Anki import."""
    content = clean_text(raw.get("content"))
    category = clean_text(raw.get("category")) or "general"
    created_dt = parse_time(raw.get("created_at"))

    try:
        front = prompt_template.format(category=category.capitalize())
    except (KeyError, IndexError, ValueError):
        front = f"What did I record regarding {category.capitalize()}?"

    back = content

    tags = ["omi", clean_tag(category)]
    raw_tags = raw.get("tags")
    if isinstance(raw_tags, list):
        for t in raw_tags:
            ct = clean_tag(t)
            if ct and ct not in tags:
                tags.append(ct)
    elif isinstance(raw_tags, str):
        for t in raw_tags.split(","):
            ct = clean_tag(t)
            if ct and ct not in tags:
                tags.append(ct)

    if created_dt:
        tags.append(f"year_{created_dt.year}")

    return front, back, " ".join(tags)


def convert(
    sources: Sequence[str],
    destination: str,
    category_filter: Optional[str] = None,
    tag_filter: Optional[str] = None,
    prompt_template: str = "What did I record regarding {category}?",
    force: bool = False,
) -> int:
    """Convert memory JSON files to an Anki-compatible TSV file."""
    memories = load_memories(sources)

    if category_filter:
        cat_lower = category_filter.strip().lower()
        memories = [m for m in memories if clean_text(m.get("category")).lower() == cat_lower]

    if tag_filter:
        want_tag = clean_tag(tag_filter).lower()
        filtered = []
        for m in memories:
            raw_tags = m.get("tags")
            tags_set = set()
            if isinstance(raw_tags, list):
                tags_set = {clean_tag(t).lower() for t in raw_tags if str(t).strip()}
            elif isinstance(raw_tags, str):
                tags_set = {clean_tag(t).lower() for t in raw_tags.split(",") if str(t).strip()}
            if want_tag in tags_set:
                filtered.append(m)
        memories = filtered

    output_path = Path(destination)
    if not force:
        try:
            output_file = output_path.open("xb")
        except FileExistsError:
            raise FileExistsError(f"Refusing to overwrite existing {output_path} (use --force to overwrite)") from None
    else:
        output_file = output_path.open("wb")

    buffer = io.StringIO()
    # Anki TSV file format: Front \t Back \t Tags
    writer = csv.writer(buffer, delimiter="\t", lineterminator="\n")
    written_count = 0
    for m in memories:
        front, back, tags_str = format_anki_card(m, prompt_template=prompt_template)
        if back:  # Only export cards with valid content
            writer.writerow([front, back, tags_str])
            written_count += 1

    payload = buffer.getvalue().encode("utf-8")
    try:
        with output_file:
            output_file.write(payload)
    except OSError:
        if not force:
            output_path.unlink(missing_ok=True)
        raise
    return written_count


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Export Omi memories and facts to Anki flashcards (.tsv) format."
    )
    parser.add_argument("destination", help="destination TSV file to create")
    parser.add_argument("sources", nargs="+", help="one or more JSON memory export files")
    parser.add_argument(
        "--category",
        help="filter memories by category name (case-insensitive)",
    )
    parser.add_argument(
        "--tag",
        help="filter memories by tag (case-insensitive)",
    )
    parser.add_argument(
        "--prompt",
        default="What did I record regarding {category}?",
        help="front card prompt template with optional {category} placeholder (default: 'What did I record regarding {category}?')",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="overwrite destination file if it already exists",
    )
    return parser


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()

    try:
        count = convert(
            sources=args.sources,
            destination=args.destination,
            category_filter=args.category,
            tag_filter=args.tag,
            prompt_template=args.prompt,
            force=args.force,
        )
        print(f"Exported {count} Anki flashcard(s) to: {args.destination}")
    except (OSError, ValueError) as exc:
        sys.exit(f"Export failed: {exc}")
