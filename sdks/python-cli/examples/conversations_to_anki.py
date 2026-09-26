#!/usr/bin/env python3
"""
Convert Omi conversations JSON export to an Anki deck (.apkg) for spaced-repetition review.

Usage:
    python conversations_to_anki.py conversations.json conversations.apkg [--deck-name NAME]
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
# orphan previously-imported cards). Distinct from memories_to_anki.py's and
# action_items_to_anki.py's MODEL_ID so all three note types can coexist in
# the same collection without colliding.
MODEL_ID = 1969382930

MODEL = genanki.Model(
    MODEL_ID,
    "Omi Conversation",
    fields=[{"name": "Front"}, {"name": "Back"}],
    templates=[
        {
            "name": "Card 1",
            "qfmt": "{{Front}}",
            "afmt": '{{FrontSide}}<hr id="answer">{{Back}}',
        }
    ],
)

DEFAULT_DECK_NAME = "Omi Conversations"


def deck_id_for(deck_name):
    """Derive a stable numeric deck ID from *deck_name*.

    Anki decks are identified by this ID, not by name: re-running the export
    with the same --deck-name always targets the same deck instead of
    creating a duplicate one on each import.
    """
    digest = hashlib.sha256(f"omi-cli-conversations-anki:{deck_name}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def field_html(value):
    """Escape *value* for use inside an Anki HTML field.

    Anki card fields render as HTML, so unescaped content containing '<',
    '&', or similar would be interpreted as markup instead of shown as text.
    Newlines are turned into '<br>' so multi-line overviews still read as
    separate lines on the card.
    """
    if value is None:
        return ""
    return html.escape(str(value), quote=False).replace("\n", "<br>")


def format_date(value):
    """Render an ISO-8601 timestamp as a short human-readable date."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.strftime("%Y-%m-%d")


def convert(source, destination, deck_name=DEFAULT_DECK_NAME):
    raw_content = Path(source).read_text(encoding="utf-8")
    if raw_content.startswith("﻿"):
        raw_content = raw_content[1:]
    items = json.loads(raw_content)

    if isinstance(items, dict):
        if "conversations" in items and isinstance(items["conversations"], list):
            items = items["conversations"]
        elif "data" in items and isinstance(items["data"], list):
            items = items["data"]
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError("Expected a JSON array or object from omi --json conversation list")

    deck = genanki.Deck(deck_id_for(deck_name), deck_name)

    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each conversation must be an object")

        conv_id = item.get("id")
        structured = item.get("structured") if isinstance(item.get("structured"), dict) else {}
        title = structured.get("title") or "Untitled conversation"
        category = structured.get("category") or "general"
        overview = structured.get("overview") or ""
        date = format_date(item.get("started_at") or item.get("created_at"))

        front = "<b>What happened in this conversation?</b>"
        meta_bits = [b for b in (date, category) if b]
        if meta_bits:
            front += f"<br><i>{field_html(' · '.join(meta_bits))}</i>"

        back = f"<b>{field_html(title)}</b>"
        if overview:
            back += f"<br><br>{field_html(overview)}"

        note = genanki.Note(
            model=MODEL,
            fields=[front, back],
            # A GUID derived from the conversation's own id keeps re-imports
            # stable: Anki's "update notes" import mode recognizes the same
            # card instead of adding a duplicate when the summary changes.
            guid=genanki.guid_for(conv_id) if conv_id else None,
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
    parser = argparse.ArgumentParser(description="Convert an Omi conversations JSON export to an Anki deck (.apkg).")
    parser.add_argument("source", help="Path to a JSON export from `omi --json conversation list`.")
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
