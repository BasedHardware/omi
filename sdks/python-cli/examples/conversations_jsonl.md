# Convert a conversations export to JSONL

Use this recipe when you want your conversations as a UTF-8 JSON Lines (`.jsonl`) file — one conversation per line — for streaming into downstream tools (`jq`, log pipelines, ML/embedding ingestion) instead of loading a single large JSON array into memory. It reads a saved JSON export, makes no network requests, and complements [`conversations_markdown.md`](conversations_markdown.md).

You need Python 3.10+ and an authenticated `omi-cli` for the initial export (no extra dependencies — stdlib only).

Export your conversations:

```sh
omi --json conversation list --limit 200 > conversations.json
```

Run the converter:

```sh
python sdks/python-cli/examples/conversations_to_jsonl.py conversations.json conversations.jsonl
```

Each line is the original conversation object, unchanged, with non-ASCII text preserved (`ensure_ascii=False`). The converter refuses to overwrite an existing destination, and a failed write leaves no partial file behind.

This converts a single saved export, not a live paginated backup — for pulling more than one page with `--offset`, see the pagination guidance in [`conversations_sqlite.md`](conversations_sqlite.md).
