# Export Omi Conversations to JSON Lines (JSONL)

Use this recipe to turn a `conversation list` JSON export into JSON Lines: one
normalized, self-contained JSON object per line — ready for `jq`, `grep`,
pandas/Spark `read_json(lines=True)`, vector-store ingestion, and LLM
fine-tuning pipelines. The converter is stdlib-only and makes no network
requests.

## Requirements

- Python 3.10+ (stdlib only — no `pip install` needed)
- An authenticated `omi-cli` (`omi auth login`) for the initial export

## Quickstart

### Option 1: Pipe straight from the CLI

`conversation list` defaults to 25 records, so pass `--limit 200` explicitly;
page with `--offset` for larger accounts.

```bash
omi --json conversation list --limit 200 | python conversations_to_jsonl.py - -o conversations.jsonl
omi --json conversation list --limit 200 --offset 200 | python conversations_to_jsonl.py - -o conversations_2.jsonl
```

### Option 2: From a saved JSON export

```bash
omi --json conversation list --limit 200 > conversations.json
python conversations_to_jsonl.py conversations.json -o conversations.jsonl
```

### Option 3: Include full transcript segments

Transcript segments are excluded by default to keep lines small. Add
`--include-transcript` to embed normalized
`{speaker, start, end, text}` segments per line:

```bash
omi --json conversation list --include-transcript --limit 200 | python conversations_to_jsonl.py - --include-transcript -o conversations_full.jsonl
```

### Option 4: Filter by category

```bash
omi --json conversation list --limit 200 | python conversations_to_jsonl.py - --category work,personal -o work_and_personal.jsonl
```

## Line Schema

Each line is one JSON object:

```json
{"id": "…", "title": "…", "category": "…", "started_at": "2026-09-30T10:00:00+00:00", "finished_at": "…", "source": "omi", "overview": "…", "action_items": [{"description": "…", "completed": true}]}
```

- `started_at`/`finished_at` are normalized to ISO-8601 UTC; unusable values
  become `null` (a boundary-overflow timestamp is kept raw instead of aborting
  the export).
- `title`/`category`/`source` fall back to safe defaults for legacy rows.
- `action_items` is always a list of `{description, completed}` dicts, coerced
  from objects or plain strings.
- With `--include-transcript`, `transcript_segments` is a list of
  `{speaker, start, end, text}` dicts.

## Robustness Guarantees

- **No BOM, compact output** — every line is plain UTF-8 JSON, safe for line
  oriented text tools.
- **Envelope unwrapping** — accepts bare arrays, `{"conversations": [...]}`,
  `{"items": ...}`, `{"data": ...}`, `{"results": ...}`, or a single
  conversation object; error payloads like `{"detail": "..."}` yield empty
  output instead of a phantom row.
- **Loose row coercion** — one odd record (a string, a number, a `None` row,
  garbage transcript segments) is skipped or coerced; it cannot crash the
  export, filtered or not.
- **Exclusive creation** — `-o` refuses to overwrite an existing file, the
  complete export is built before the filesystem is touched, and a write error
  mid-file removes the partial output and reports a clean error.
- **BOM-tolerant input** — saved exports from editors that add a BOM and piped
  stdin both work.
