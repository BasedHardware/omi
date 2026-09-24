# Export memories to Anki spaced-repetition flashcards

Use this recipe to convert Omi memories, facts, and learnings into Anki flashcard decks (`.tsv` / `.txt`). Spaced repetition with Anki helps you commit key details, names, meeting notes, and facts captured by your Omi device to long-term memory.

It formats cards with HTML line breaks, organizes cards into subdecks by category (`Omi::Memories::Skills`), attaches topic tags, and includes Anki import metadata directives (`#separator:tab`, `#html:true`).

## Exporting Memories

Fetch memories with `omi-cli`:

```bash
omi --json memory list --limit 200 > memories.json
```

Or pipe directly into the converter:

```bash
omi --json memory list | python memories_to_anki.py - -o omi_deck.tsv
```

## Running the Exporter

Convert saved memories to an Anki deck:

```bash
python memories_to_anki.py memories.json -o omi_deck.tsv
```

Filter by specific categories:

```bash
python memories_to_anki.py memories.json -o work_deck.tsv --category work,skills
```

Custom base deck name:

```bash
python memories_to_anki.py memories.json -o cards.tsv --deck "SecondBrain"
```

## Importing into Anki

1. Open **Anki Desktop** (or AnkiMobile / AnkiDroid).
2. Click **File -> Import...** and select `omi_deck.tsv`.
3. Anki automatically reads the `#separator:tab` and `#deck column:3` directives.
4. Click **Import** to start studying your Omi memories!
