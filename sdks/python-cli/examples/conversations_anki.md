# Convert conversations to an Anki deck (.apkg) for spaced-repetition review

Use this recipe when you want to actually remember what a past conversation was about — quizzed via Anki's spaced-repetition scheduler — instead of only searching for it when you already remember it happened. The front of each card asks what happened on a given date/category; the back reveals the conversation's title and summary. It reads a saved JSON export, makes no network requests, and complements [`conversations_markdown.md`](conversations_markdown.md).

You need Python 3.10+, an authenticated `omi-cli` for the initial export, and [`genanki`](https://pypi.org/project/genanki/):

```sh
pip install genanki
```

Export your conversations:

```sh
omi --json conversation list --limit 200 > conversations.json
```

Run the converter:

```sh
python sdks/python-cli/examples/conversations_to_anki.py conversations.json conversations.apkg
```

Or name the deck explicitly (defaults to `Omi Conversations`):

```sh
python sdks/python-cli/examples/conversations_to_anki.py conversations.json conversations.apkg --deck-name "Omi / September"
```

Double-click `conversations.apkg`, or import it from Anki's **File → Import** menu. Conversations without a processed `structured` summary yet still get a card (back shows "Untitled conversation") instead of being silently skipped.

**Re-exporting is safe to re-import.** The deck ID is derived from `--deck-name` and each card's GUID from the conversation's own `id`, so re-exporting after a summary is (re)generated and re-importing with Anki's "update notes" option updates existing cards in place instead of duplicating them.

**HTML safety:** the title and overview are HTML-escaped before being placed in the card (Anki fields render as HTML), so content containing `<`, `&`, or script-like text is always shown as plain text, never interpreted as markup. The converter refuses to overwrite an existing destination, and a failed save leaves no partial file behind.
