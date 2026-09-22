# Exporting OMI Memories to an Obsidian Vault

The **`memories_to_obsidian.py`** script turns a JSON export of OMI memories into a
set of markdown files that can be dropped straight into an Obsidian vault.

## What the script does

* **One file per memory** – each memory becomes a separate `*.md` file.
* **YAML front‑matter** – the file starts with a front‑matter block containing
  `title`, `date`, and optional `tags`.  Obsidian reads this automatically.
* **Wikilinks** – any occurrence of another memory’s title inside a memory’s
  content is replaced with an Obsidian wikilink (`[[Title]]`), allowing you to
  navigate between notes instantly.
* **Atomic writes** – files are written to a temporary location first and then
  renamed, guaranteeing that partially‑written files never appear in your vault.

## Prerequisites

* Python 3.9+ (the repository targets Python 3.13, but any recent version works).
* A JSON export of your memories. The expected format is an array of objects,
  each with at least `title` and `content`. Optional fields are `tags` (list of
  strings) and `created_at` (ISO‑8601 timestamp).

### Example JSON

