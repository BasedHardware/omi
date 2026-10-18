# Convert a conversation-list export to JSON Lines (JSONL)

Use this recipe when the next step is a pipeline: `jq`/`grep` filtering,
`pandas.read_json(lines=True)` / Spark, a vector-store loader, or an LLM
fine-tuning dataset. It reads a saved JSON export, makes no network requests,
and keeps transcripts out of the output unless you opt in. You need
Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export up to 200 conversations:

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account backup. To retrieve another page, increase `--offset`
by 200 and use a different filename — feed both files through separate runs of
the converter and `cat` the outputs together, or concatenate the export files
into one JSON array first. Changes to the account between requests can affect
offset pagination; this recipe does not promise a consistent snapshot.

## The converter

The script lives at [`conversations_to_jsonl.py`](conversations_to_jsonl.py)
in this directory — stdlib-only, no third-party packages. Each output line is
one normalized, self-contained JSON object:

```json
{"id":"conv_123","title":"Planning session","category":"work","started_at":"2026-10-17T10:00:00Z","finished_at":"2026-10-17T10:42:11Z","source":"omi","overview":"...","action_items":[{"description":"...","completed":false}]}
```

Stable schema: `id`, `title`, `category`, `started_at`, `finished_at`,
`source`, `overview`, `action_items` (`{description, completed}` dicts
coerced from objects or bare strings). Timestamps are normalized to ISO-8601
UTC; unparseable or boundary-overflow values keep their raw text instead of
aborting the export. Output is compact-separator JSONL with no BOM and
`ensure_ascii=False` (raw UTF-8, not `\uXXXX` escapes).

## Usage

Convert a saved export to a file (exclusive-create — never overwrites):

```sh
python conversations_to_jsonl.py conversations.json -o conversations.jsonl
```

Stream straight to stdout for a pipeline:

```sh
omi --json conversation list --limit 200 | python conversations_to_jsonl.py | jq -r '.category'
```

Filter by category (comma-separated, case-insensitive):

```sh
python conversations_to_jsonl.py conversations.json --category personal,work -o filtered.jsonl
```

Embed normalized transcript segments (`{speaker, start, end, text}`) when a
dataset needs them — off by default so lines stay small:

```sh
python conversations_to_jsonl.py conversations.json --include-transcript -o full.jsonl
```

## Input tolerance

The reader unwraps every CLI export shape — `{"conversations": [...]}`,
`{"items": ...}`, `{"data": ...}`, `{"results": ...}`, a bare array, or a
single object — accepts UTF-8 BOM on file input, and treats error payloads
(`{"error": ...}`) as an empty export rather than a phantom row.

## Output guarantees

* **Atomic-ish `-o` writes.** The complete export is rendered before the
  filesystem is touched; the destination is opened exclusively (`-o` refuses
  to overwrite), and a write error removes the partial file and reports a
  clean message. Exit code `2` signals any input/output failure.
* **One odd row cannot kill the export.** Non-dict records pass through
  untouched when no filter is active; with `--category`, a row without a
  category simply doesn't match and is skipped.

## pandas / Spark ingestion

```python
import pandas as pd
df = pd.read_json("conversations.jsonl", lines=True)
```

```python
spark.read.json("conversations.jsonl")  # Spark infers lines=True for JSONL
```
