# Convert action items to an Anki deck (.apkg) for spaced-repetition review

Use this recipe when you want your open action items to actually resurface for review — via Anki's spaced-repetition scheduler — instead of getting buried in a list. It converts an action-items JSON export into an Anki deck: the front shows a due-date prompt for still-open items, the back shows the task description and status. It reads a saved JSON export, makes no network requests, and complements [`action_items_markdown.md`](action_items_markdown.md).

You need Python 3.10+, an authenticated `omi-cli` for the initial export, and [`genanki`](https://pypi.org/project/genanki/):

```sh
pip install genanki
```

Export your open action items:

```sh
omi --json action-item list --open > action_items.json
```

Run the converter:

```sh
python sdks/python-cli/examples/action_items_to_anki.py action_items.json action_items.apkg
```

Or name the deck explicitly (defaults to `Omi Action Items`):

```sh
python sdks/python-cli/examples/action_items_to_anki.py action_items.json action_items.apkg --deck-name "Omi / This Week"
```

Double-click `action_items.apkg`, or import it from Anki's **File → Import** menu. Completed items still get a card (back shows `Status: Done`) but their front doesn't nag you with a due date.

**Re-exporting is safe to re-import.** The deck ID is derived from `--deck-name` and each card's GUID from the item's own `id`, so re-exporting after tasks change — completed, rescheduled — and re-importing with Anki's "update notes" option updates existing cards in place instead of duplicating them.

**HTML safety:** the task description is HTML-escaped before being placed in the card (Anki fields render as HTML), so a description containing `<`, `&`, or script-like text is always shown as plain text, never interpreted as markup. The converter refuses to overwrite an existing destination, and a failed save leaves no partial file behind.
