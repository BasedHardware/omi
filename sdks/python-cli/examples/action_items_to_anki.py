#!/usr/bin/env python3
"""
Convert Omi action items JSON export to an Anki deck (.apkg) for spaced-repetition review.

Usage:
    python action_items_to_anki.py action_items.json action_items.apkg [--deck-name NAME]
"""

import argparse
import hashlib
import html
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import genanki

# Fixed so every run of this script produces notes Anki recognizes as the
# same note type across re-exports (required by genanki; changing this would
# orphan previously-imported cards). Distinct from memories_to_anki.py's
# MODEL_ID so the two note types never collide in the same collection.
MODEL_ID = 1969381777

MODEL = genanki.Model(
    MODEL_ID,
    "Omi Action Item",
    fields=[{"name": "Front"}, {"name": "Back"}],
    templates=[
        {
            "name": "Card 1",
            "qfmt": "{{Front}}",
            "afmt": '{{FrontSide}}<hr id="answer">{{Back}}',
        }
    ],
)

DEFAULT_DECK_NAME = "Omi Action Items"


def deck_id_for(deck_name):
    """Derive a stable numeric deck ID from *deck_name*.

    Anki decks are identified by this ID, not by name: re-running the export
    with the same --deck-name always targets the same deck instead of
    creating a duplicate one on each import.
    """
    digest = hashlib.sha256(f"omi-cli-action-items-anki:{deck_name}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def field_html(value):
    """Escape *value* for use inside an Anki HTML field.

    Anki card fields render as HTML, so unescaped content containing '<',
    '&', or similar would be interpreted as markup instead of shown as text.
    Newlines are turned into '<br>' so multi-line descriptions still read as
    separate lines on the card.
    """
    if value is None:
        return ""
    return html.escape(str(value), quote=False).replace("\n", "<br>")


def format_due(due_at):
    """Render an ISO-8601 due date as a short human-readable string.

    Falls back to the raw value for anything that doesn't parse, so a
    malformed timestamp is still shown instead of silently dropped.
    """
    if not due_at:
        return None
    try:
        parsed = datetime.fromisoformat(str(due_at).replace("Z", "+00:00"))
    except ValueError:
        return str(due_at)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.strftime("%Y-%m-%d")


def convert(source, destination, deck_name=DEFAULT_DECK_NAME):
    raw_content = Path(source).read_text(encoding="utf-8")
    if raw_content.startswith("﻿"):
        raw_content = raw_content[1:]
    items = json.loads(raw_content)

    if isinstance(items, dict):
        if "action_items" in items and isinstance(items["action_items"], list):
            items = items["action_items"]
        elif "data" in items and isinstance(items["data"], list):
            items = items["data"]
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError("Expected a JSON array or object from omi --json action-item list")

    deck = genanki.Deck(deck_id_for(deck_name), deck_name)

    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each action item must be an object")

        item_id = item.get("id")
        completed = bool(item.get("completed"))
        status = "Done" if completed else "Open"
        due = format_due(item.get("due_at"))

        front = "<b>Action item</b>"
        if due and not completed:
            front += f"<br><i>Due {field_html(due)}</i>"

        back = field_html(item.get("description"))
        back += f"<br><br><small>Status: {field_html(status)}"
        if due:
            back += f" · Due {field_html(due)}"
        back += "</small>"

        note = genanki.Note(
            model=MODEL,
            fields=[front, back],
            # A GUID derived from the item's own id keeps re-imports stable:
            # Anki's "update notes" import mode recognizes the same card
            # instead of adding a duplicate when its status/content changes.
            guid=genanki.guid_for(item_id) if item_id else None,
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
    parser = argparse.ArgumentParser(description="Convert an Omi action items JSON export to an Anki deck (.apkg).")
    parser.add_argument("source", help="Path to a JSON export from `omi --json action-item list`.")
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
