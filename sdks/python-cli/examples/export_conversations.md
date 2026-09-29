# Export every conversation to JSONL (full, paginated backup)

`omi conversation list` caps out at `--limit 200` per call, so a full-account export needs pagination. [`export_conversations.py`](export_conversations.py) drives the CLI as a subprocess, pages through every conversation, and writes one JSON object per line to a UTF-8 JSON Lines (`.jsonl`) file — a format that streams well into downstream tools (`jq`, log pipelines, ML/embedding ingestion) without loading the whole export into memory.

```sh
python sdks/python-cli/examples/export_conversations.py conversations.jsonl
# exported 842 conversation(s) to conversations.jsonl
```

Include full transcript segments (slower per page, since the CLI caps transcript pages at 25):

```sh
python sdks/python-cli/examples/export_conversations.py conversations.jsonl --include-transcript
```

## How it works

- Pages through `omi --json conversation list --limit 200 --offset N [--include-transcript]`, requesting 200 (the CLI's `--limit` maximum) per call and stopping at the first short or empty page.
- Every page is validated strictly: the CLI must exit `0`, the body must be valid UTF-8 JSON, a JSON array, and every record a JSON object. Any violation aborts the export before anything is written.
- The output file is written **atomically**: records stream to a temporary file next to the destination and replace it only after every page succeeds. A failed export leaves the previous file untouched and no temp file behind.
- Non-ASCII text round-trips losslessly (`ensure_ascii=False`), so titles or content in any language, including emoji, are preserved.

## Caveat: not a consistent snapshot

Offset pagination is not a snapshot. If conversations are created while the export runs, pages can shift and the result may skip or repeat a conversation. Run the export while the account is quiet, or re-run it, if you need a guaranteed-complete set.

## Environment

- `OMI_BIN` — how to invoke the CLI (default `omi`). Useful for wrappers or virtualenvs, e.g. `OMI_BIN="python -m omi_cli"`.

Exit codes: `0` success · `2` the omi CLI failed · `3` the CLI returned invalid output · `1` usage or I/O error.
