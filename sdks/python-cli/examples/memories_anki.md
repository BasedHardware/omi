# Convert memories to an Anki deck (.apkg) for spaced-repetition review

Use this recipe when you want to actually *review* the facts and learnings Omi has captured about you, instead of just archiving them. It converts a memories JSON export into an Anki deck: the category and tags are the front of the card, the memory content is the back, and Anki's spaced-repetition scheduler brings each one back for review over time. It reads a saved JSON export, makes no network requests, and complements [`memories_markdown.md`](memories_markdown.md).

You need Python 3.10+, an authenticated `omi-cli` for the initial export, and [`genanki`](https://pypi.org/project/genanki/):

```sh
pip install genanki
```

Export your memories:

```sh
omi --json memory list --limit 200 > memories.json
```

Run the converter:

```sh
python sdks/python-cli/examples/memories_to_anki.py memories.json memories.apkg
```

Or name the deck explicitly (defaults to `Omi Memories`):

```sh
python sdks/python-cli/examples/memories_to_anki.py memories.json memories.apkg --deck-name "Omi / Work"
```

Double-click `memories.apkg`, or import it from Anki's **File → Import** menu. Each card's front shows the category (e.g. **Work**) and any tags; the back shows the memory content and capture date.

**Re-exporting is safe to re-import.** The deck ID is derived from `--deck-name` and each card's GUID from the memory's own `id`, so running this again — after new memories have been captured — and re-importing with Anki's "update notes" option updates existing cards in place instead of duplicating them.

**HTML safety:** memory content is HTML-escaped before being placed in the card (Anki fields render as HTML), so a memory containing `<`, `&`, or script-like text is always shown as plain text, never interpreted as markup. The converter refuses to overwrite an existing destination, and a failed save leaves no partial file behind.
