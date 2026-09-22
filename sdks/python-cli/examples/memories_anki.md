# Convert memories export to Anki flashcards

Use this recipe to export Omi memories and knowledge into Anki-compatible TSV flashcards for spaced-repetition retention. You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export memories:

```sh
omi --json memory list --limit 200 > memories.json
```

Convert to Anki TSV:

```sh
python memories_to_anki.py memories.json memories_anki.tsv
```

In Anki, click **File -> Import**, select `memories_anki.tsv`, and map Field 1 to Front and Field 2 to Back.
