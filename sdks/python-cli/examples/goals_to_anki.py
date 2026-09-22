#!/usr/bin/env python3
"""
Convert Omi tracked goals JSON export to an Anki deck (.apkg) for spaced-repetition check-ins.

Usage:
    python goals_to_anki.py goals.json goals.apkg [--deck-name NAME]
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
# orphan previously-imported cards). Distinct from the memories/action-items/
# conversations Anki recipes so all note types can coexist in one collection.
MODEL_ID = 1969384102

MODEL = genanki.Model(
    MODEL_ID,
    "Omi Goal",
    fields=[{"name": "Front"}, {"name": "Back"}],
    templates=[
        {
            "name": "Card 1",
            "qfmt": "{{Front}}",
            "afmt": '{{FrontSide}}<hr id="answer">{{Back}}',
        }
    ],
)

DEFAULT_DECK_NAME = "Omi Goals"


def deck_id_for(deck_name):
    """Derive a stable numeric deck ID from *deck_name*.

    Anki decks are identified by this ID, not by name: re-running the export
    with the same --deck-name always targets the same deck instead of
    creating a duplicate one on each import.
    """
    digest = hashlib.sha256(f"omi-cli-goals-anki:{deck_name}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def field_html(value):
    """Escape *value* for use inside an Anki HTML field."""
    if value is None:
        return ""
    return html.escape(str(value), quote=False).replace("\n", "<br>")


def progress_pct(current, target, min_value, max_value):
    """Fraction of a goal completed, clamped to [0, 1].

    Prefers current/target (matches the convention used by goals_csv.md);
    falls back to the min/max range when target isn't usable (e.g. 0 or
    missing).
    """
    try:
        c = float(current)
    except (TypeError, ValueError):
        return 0.0
    try:
        t = float(target)
        if t > 0:
            return max(0.0, min(1.0, c / t))
    except (TypeError, ValueError):
        pass
    try:
        lo, hi = float(min_value), float(max_value)
        if hi > lo:
            return max(0.0, min(1.0, (c - lo) / (hi - lo)))
    except (TypeError, ValueError):
        pass
    return 0.0


def format_value(value):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return field_html(value)
    if f == int(f):
        return str(int(f))
    return f"{f:g}"


def convert(source, destination, deck_name=DEFAULT_DECK_NAME):
    raw_content = Path(source).read_text(encoding="utf-8")
    if raw_content.startswith("﻿"):
        raw_content = raw_content[1:]
    items = json.loads(raw_content)

    if isinstance(items, dict):
        if "goals" in items and isinstance(items["goals"], list):
            items = items["goals"]
        elif "data" in items and isinstance(items["data"], list):
            items = items["data"]
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError("Expected a JSON array or object from omi --json goal list")

    deck = genanki.Deck(deck_id_for(deck_name), deck_name)

    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each goal must be an object")

        goal_id = item.get("id")
        title = item.get("title") or "Untitled goal"
        unit = item.get("unit") or ""
        current = item.get("current_value")
        target = item.get("target_value")
        pct = progress_pct(current, target, item.get("min_value"), item.get("max_value"))
        is_active = item.get("is_active", True)

        front = f"<b>{field_html(title)}</b><br><i>What's my progress on this goal?</i>"

        status = "Active" if is_active else "Completed / Inactive"
        summary = f"{format_value(current)} / {format_value(target)} {field_html(unit)}".strip()
        back = f"{summary} · {pct * 100:.0f}%<br><small>{field_html(status)}</small>"

        note = genanki.Note(
            model=MODEL,
            fields=[front, back],
            # A GUID derived from the goal's own id keeps re-imports stable:
            # Anki's "update notes" import mode recognizes the same card
            # instead of adding a duplicate as progress changes.
            guid=genanki.guid_for(goal_id) if goal_id else None,
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
    parser = argparse.ArgumentParser(description="Convert an Omi goals JSON export to an Anki deck (.apkg).")
    parser.add_argument("source", help="Path to a JSON export from `omi --json goal list`.")
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
