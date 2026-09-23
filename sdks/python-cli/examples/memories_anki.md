# Export memories to Anki flashcards for spaced repetition

Convert Omi memories, insights, and key learnings into standard Anki-compatible TSV files for spaced-repetition study and knowledge retention.

## Overview

This recipe takes JSON exports from `omi memory list` and formats them into flashcard pairs:
- **Front**: Category title badge, date context, or active-recall question prompt.
- **Back**: The memory content / insight, sanitized with HTML line breaks (`<br>`) for clean rendering in Anki mobile and desktop apps.
- **Tags**: Space-separated tags including `omi_memory`, `category::<category_name>`, and any custom memory tags.
- **Directives**: Standard Anki file headers (`#separator:tab`, `#html:true`, `#deck:<deck_name>`, `#tags column:3`) for 1-click drag-and-drop import into Anki.

## Prerequisites

- Python 3.10+
- An authenticated `omi-cli` installation:
  ```sh
  omi auth status
  ```

## Quick Start

### 1. Direct Pipeline Export

Pipe directly from `omi` CLI into `memories_to_anki.py`:

```sh
omi --json memory list --limit 100 | python memories_to_anki.py - --output omi_memories.tsv
```

### 2. Export with a Dedicated Deck Name

Specify an Anki target deck (creates or appends to the deck in Anki):

```sh
omi --json memory list | python memories_to_anki.py - --output omi_flashcards.tsv --deck "Omi::Memories"
```

### 3. Filter Specific Knowledge Categories

Export only your key learnings and technical skills:

```sh
omi --json memory list | python memories_to_anki.py - --category learnings,skills,work --output learning_cards.tsv --deck "Omi::Learnings"
```

### 4. Active-Recall Question Prompts

Use the `--template prompt` flag to generate question-style cards instead of standard category badges:

```sh
omi --json memory list | python memories_to_anki.py - --template prompt --output active_recall_cards.tsv
```

## Importing into Anki

1. Open **Anki Desktop** (or AnkiMobile / AnkiDroid).
2. Click **File** -> **Import...** (or press `Ctrl+I` / `Cmd+I`).
3. Select the generated `.tsv` file (e.g. `omi_memories.tsv`).
4. Anki will automatically recognize the `#separator:tab`, `#html:true`, and `#tags column:3` headers.
5. Click **Import** to add the cards to your spaced repetition queue.

## CLI Options

| Option | Description |
|---|---|
| `input` | JSON input file path, or `-` to read from stdin |
| `-o`, `--output` | Destination `.tsv` file path (omitted writes to stdout) |
| `--deck` | Custom Anki deck name (e.g. `Omi::Knowledge`) |
| `--category` | Comma-separated list of categories to filter (e.g. `learnings,work`) |
| `--template` | Front prompt style: `category` (default), `prompt` (question), or `cloze` (summary lead) |
| `--no-tags` | Omit the tags column from export |
| `--tag` | Append custom tags to all generated cards (can be specified multiple times) |
| `--exclude-private` | Skip memories marked with `private` visibility |
