# Turn Omi Memories and Facts into Anki Flashcards (.tsv)

Use this recipe to convert facts, learnings, vocabulary, and insights captured by your Omi wearable into an Anki-compatible `.tsv` (tab-separated values) flashcard deck for spaced repetition. It reads a saved JSON export, makes no network requests, and generates clean flashcards with structured tags (`omi`, category, year, and memory tags) ready for instant import into **Anki Desktop**, **AnkiMobile** (iOS), or **AnkiDroid** (Android).

---

## Prerequisites

Ensure you have the `omi` CLI installed and authenticated:

```sh
pip install omi-cli
omi auth login
```

Verify you can list your memories:

```sh
omi memory list
```

---

## Exporting Memories

Export up to 200 memories (open or past):

```sh
omi --json memory list --limit 200 > memories.json
```

To retrieve more items, paginate using `--offset` (e.g., `--limit 200 --offset 200 > memories_page2.json`). The converter accepts multiple JSON files at once and automatically deduplicates entries by memory `id`.

---

## Quickstart

Save the converter script as `memories_to_anki.py` (kept alongside this recipe at [`memories_to_anki.py`](memories_to_anki.py) and verified by `tests/test_memories_to_anki.py`).

### 1. Basic Export

Convert all memories to an Anki flashcards TSV file:

```sh
python memories_to_anki.py anki_deck.tsv memories.json
```

Output:
```text
Exported 42 Anki flashcard(s) to: anki_deck.tsv
```

### 2. Filter by Category

Export only specific categories, such as `learnings` or `skills`:

```sh
python memories_to_anki.py --category learnings deck_learnings.tsv memories.json
```

### 3. Filter by Tag

Filter cards by specific memory tag:

```sh
python memories_to_anki.py --tag python deck_python.tsv memories.json
```

### 4. Custom Front Prompt Template

Customize the question asked on the front of each card using the `{category}` placeholder:

```sh
python memories_to_anki.py --prompt "What insight did I capture about {category}?" custom_deck.tsv memories.json
```

### 5. Multi-Page Merge and Overwrite Protection

Combine multiple export pages into a single deck, using `--force` to overwrite existing files:

```sh
python memories_to_anki.py -f complete_deck.tsv memories_page1.json memories_page2.json
```

---

## Importing into Anki

### Anki Desktop (macOS, Windows, Linux)

1. Open Anki and select or create a target deck (e.g., **Omi Memories**).
2. Click **File** &rarr; **Import...** (or press `Ctrl+I` / `Cmd+I`).
3. Select your exported `.tsv` file (e.g., `anki_deck.tsv`).
4. In the Import Dialog:
   - **Type**: `Basic` (Front and Back card).
   - **Deck**: Choose your desired deck (e.g., `Omi Memories`).
   - **Field separator**: `Tab`.
   - **Field mapping**:
     - Field 1 &rarr; `Front`
     - Field 2 &rarr; `Back`
     - Field 3 &rarr; `Tags`
5. Click **Import**. Your flashcards are immediately available for daily review!

### AnkiMobile & AnkiDroid

- Sync via **AnkiWeb** after importing into Anki Desktop.
- Alternatively, import the `.tsv` file directly via AnkiWeb or file transfer into your mobile Anki app.

---

## CLI Options

| Argument / Flag | Description | Default |
| :--- | :--- | :--- |
| `destination` | Destination `.tsv` file to create | *(Required)* |
| `sources` | One or more JSON memory export files | *(Required)* |
| `--category` | Filter memories by category (case-insensitive) | `None` (all) |
| `--tag` | Filter memories by tag (case-insensitive) | `None` (all) |
| `--prompt` | Question template for the front of the card (`{category}` replaced with capitalized category) | `"What did I record regarding {category}?"` |
| `-f`, `--force` | Overwrite destination file if it already exists | `False` |

---

## Anki Card Structure

Each line in the resulting TSV file corresponds to one Anki card with three tab-delimited columns:

```tsv
Front	Back	Tags
```

- **Front**: Generated question prompt (e.g. `What did I record regarding Learnings?`).
- **Back**: The raw memory insight or fact content, with internal tabs and newlines normalized.
- **Tags**: Space-separated tags formatted for Anki:
  - `omi`: identifies device source.
  - Category tag (e.g. `work`, `learnings`, `skills`).
  - Memory tags attached to the item (e.g. `python`, `architecture`). Spaces are replaced with underscores.
  - Creation year tag (e.g. `year_2026`) when `created_at` timestamp is present.

### Sample Output

```tsv
What did I record regarding Learnings?	KiCad library table nicknames require escaping double quotes to avoid syntax errors.	omi learnings eda electronics year_2026
What did I record regarding Skills?	Proficient in Python standard library tool design and FastAPI backend development.	omi skills python fastapi year_2026
What did I record regarding Work?	Prefers asynchronous communication for architecture proposals and pull request reviews.	omi work workflow management year_2026
```

---

## Design Principles

- **Zero External Dependencies**: Pure Python standard library (`argparse`, `csv`, `datetime`, `io`, `json`, `pathlib`, `sys`).
- **Envelope Agnostic**: Handles raw lists, top-level arrays, single memory objects, and API response wrappers (`{"memories": [...]}`).
- **Data Integrity & Atomic Writes**: Refuses to overwrite existing files without `--force`, and never leaves corrupted or partial files on failure.
- **Deduplication**: Merges multi-page exports safely by unique `id`.
