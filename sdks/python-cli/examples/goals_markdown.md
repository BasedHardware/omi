# Export goals to Markdown notes

Use this recipe to turn an `omi --json goal list` export into a folder of
Markdown notes for Obsidian, Notion, or a personal vault. Each goal becomes
one `.md` file with YAML frontmatter, an ASCII progress bar, and its metric
fields. It reads a saved JSON export, makes no network requests. You need
Python 3.9+ and an authenticated `omi-cli` for the initial export.

Export your goals:

```sh
omi --json goal list --include-inactive --limit 100 > goals.json
```

`--include-inactive` keeps completed and paused goals in the export —
`goal list` defaults to active-only; `--limit` raises the 10-per-page
default to the 100-per-page cap.

## The converter

The script lives at [`goals_to_markdown.py`](goals_to_markdown.py) in this
directory — stdlib-only, zero external dependencies.

Each note renders like:

```markdown
---
id: "g1"
goal_type: "numeric"
unit: "glasses"
is_active: true
created_at: "2026-10-01T00:00:00Z"
---

# Drink water

██████░░░░ 60%

**Status:** active
**Progress:** 6 / 10 glasses
**Type:** numeric
**Created:** 2026-10-01T00:00:00Z
**Omi ID:** `g1`
```

* **ASCII progress bar** (`██████░░░░ 60%`) for metric goals — blank for
  qualitative goals with no numeric target.
* **YAML frontmatter** — Obsidian reads it; Notion ignores it cleanly.
* **One note per goal**, filename slugged from the title (traversal-safe,
  duplicate slugs get `_2`, `_3`, …).

## Usage

```sh
python goals_to_markdown.py goals.json --output-dir ./vault/goals/
```

## Input tolerance

Unwraps `{"goals": [...]}`, `{"items": ...}`, `{"data": ...}`, a bare array,
or a single object; accepts UTF-8 BOM input.

## Safety

* `..` in `--output-dir` is refused.
* Exclusive `x` note creation — existing files are never overwritten; a
  failed write leaves no partial file.
* Malformed JSON or a missing input exits `2` with a clean message.
