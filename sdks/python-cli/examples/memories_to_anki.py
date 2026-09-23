#!/usr/bin/env python3
"""
Convert Omi memories JSON export to an Anki deck (.apkg) for spaced-repetition review.

Usage:
    python memories_to_anki.py memories.json memories.apkg [--deck-name NAME]
"""

import argparse
import hashlib
import html
import json
import os
import sys
from pathlib import Path

import genanki

# Fixed so every run of this script produces notes Anki recognizes as the
# same note type across re-exports (required by genanki; changing this would
# orphan previously-imported cards).
MODEL_ID = 1969380420

MODEL = genanki.Model(
    MODEL_ID,
    "Omi Memory",
    fields=[{"name": "Front"}, {"name": "Back"}],
    templates=[
        {
            "name": "Card 1",
            "qfmt": "{{Front}}",
            "afmt": '{{FrontSide}}<hr id="answer">{{Back}}',
        }
    ],
)

DEFAULT_DECK_NAME = "Omi Memories"


def deck_id_for(deck_name):
    """Derive a stable numeric deck ID from *deck_name*.

    Anki decks are identified by this ID, not by name: re-running the export
    with the same --deck-name always targets the same deck instead of
    creating a duplicate one on each import.
    """
    digest = hashlib.sha256(f"omi-cli-memories-anki:{deck_name}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def field_html(value):
    """Escape *value* for use inside an Anki HTML field.

    Anki card fields render as HTML, so unescaped memory content containing
    '<', '&', or similar would be interpreted as markup instead of shown as
    text. Newlines are turned into '<br>' so multi-line content still reads
    as separate lines on the card.
    """
    if value is None:
        return ""
    return html.escape(str(value), quote=False).replace("\n", "<br>")


def convert(source, destination, deck_name=DEFAULT_DECK_NAME):
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

    deck = genanki.Deck(deck_id_for(deck_name), deck_name)

    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each memory must be an object")

        memory_id = item.get("id")
        category = str(item.get("category") or "uncategorized").replace("_", " ").title()
        tags_raw = item.get("tags") or []
        tags_str = ", ".join(str(t).strip() for t in tags_raw if t) if isinstance(tags_raw, list) else str(tags_raw)

        front = f"<b>{field_html(category)}</b>"
        if tags_str:
            front += f"<br><i>{field_html(tags_str)}</i>"

        back = field_html(item.get("content"))
        created_at = item.get("created_at")
        if created_at:
            back += f"<br><br><small>Captured {field_html(created_at)}</small>"

        note = genanki.Note(
            model=MODEL,
            fields=[front, back],
            # A GUID derived from the memory's own id keeps re-imports stable:
            # Anki's "update notes" import mode recognizes the same card
            # instead of adding a duplicate when content changes.
            guid=genanki.guid_for(memory_id) if memory_id else None,
        )
        deck.add_note(note)

    output_path = Path(destination)
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing {output_path}")

    partial = output_path.with_name(output_path.name + ".partial")
    try:
        genanki.Package(deck).write_to_file(str(partial))
        os.replace(partial, output_path)
    except OSError:
        partial.unlink(missing_ok=True)
        raise


def main(argv):
    parser = argparse.ArgumentParser(description="Convert an Omi memories JSON export to an Anki deck (.apkg).")
    parser.add_argument("source", help="Path to a JSON export from `omi --json memory list`.")
    parser.add_argument("destination", help="Path to write the .apkg deck to.")
    parser.add_argument(
        "--deck-name", default=DEFAULT_DECK_NAME, help=f"Anki deck name (default: {DEFAULT_DECK_NAME!r})."
    )
    args = parser.parse_args(argv)
    convert(args.source, args.destination, args.deck_name)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except (OSError, ValueError) as exc:
        sys.exit(f"Anki export failed: {exc}")
