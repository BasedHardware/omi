# Convert goals to an Anki deck (.apkg) for spaced-repetition check-ins

Use this recipe when you want a periodic nudge to check in on your tracked goals — via Anki's spaced-repetition scheduler — instead of only looking at them when you remember to open the app. The front asks "What's my progress on this goal?"; the back reveals the current/target values and percentage complete. It reads a saved JSON export, makes no network requests, and complements [`goals_html.md`](goals_html.md).

You need Python 3.10+, an authenticated `omi-cli` for the initial export, and [`genanki`](https://pypi.org/project/genanki/):

```sh
pip install genanki
```

Export your tracked goals:

```sh
omi --json goal list --limit 100 --include-inactive > goals.json
```

Run the converter:

```sh
python sdks/python-cli/examples/goals_to_anki.py goals.json goals.apkg
```

Or name the deck explicitly (defaults to `Omi Goals`):

```sh
python sdks/python-cli/examples/goals_to_anki.py goals.json goals.apkg --deck-name "Omi / Q4"
```

Double-click `goals.apkg`, or import it from Anki's **File → Import** menu. Progress uses the same `current_value / target_value` convention as [`goals_csv.md`](goals_csv.md), falling back to the `min_value`–`max_value` range when `target_value` isn't usable.

**Re-exporting is safe to re-import.** The deck ID is derived from `--deck-name` and each card's GUID from the goal's own `id`, so re-exporting as progress changes and re-importing with Anki's "update notes" option updates existing cards in place instead of duplicating them.

**HTML safety:** the goal title and unit are HTML-escaped before being placed in the card (Anki fields render as HTML), so a title containing `<`, `&`, or script-like text is always shown as plain text, never interpreted as markup. The converter refuses to overwrite an existing destination, and a failed save leaves no partial file behind.
