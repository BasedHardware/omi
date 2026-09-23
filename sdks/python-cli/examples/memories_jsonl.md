# Convert a memories export to JSONL

Use this recipe when you want your memories as a UTF-8 JSON Lines (`.jsonl`) file — one memory per line — for streaming into downstream tools (`jq`, log pipelines, ML/embedding ingestion) instead of loading a single large JSON array into memory. It reads a saved JSON export, makes no network requests, and complements [`memories_markdown.md`](memories_markdown.md).

You need Python 3.10+ and an authenticated `omi-cli` for the initial export (no extra dependencies — stdlib only).

Export your memories:

```sh
omi --json memory list --limit 200 > memories.json
```

Run the converter:

```sh
python sdks/python-cli/examples/memories_to_jsonl.py memories.json memories.jsonl
```

Each line is the original memory object, byte-for-byte, with non-ASCII text preserved (`ensure_ascii=False`). The converter refuses to overwrite an existing destination, and a failed write leaves no partial file behind.
