# Convert an action-items export to JSONL

Use this recipe when you want your action items as a UTF-8 JSON Lines (`.jsonl`) file — one item per line — for streaming into downstream tools (`jq`, log pipelines, ML/embedding ingestion) instead of loading a single large JSON array into memory. It reads a saved JSON export, makes no network requests, and complements [`action_items_markdown.md`](action_items_markdown.md).

You need Python 3.10+ and an authenticated `omi-cli` for the initial export (no extra dependencies — stdlib only).

Export your action items:

```sh
omi --json action-item list --limit 500 > action_items.json
```

Run the converter:

```sh
python sdks/python-cli/examples/action_items_to_jsonl.py action_items.json action_items.jsonl
```

Each line is the original action item object, byte-for-byte, with non-ASCII text preserved (`ensure_ascii=False`). The converter refuses to overwrite an existing destination, and a failed write leaves no partial file behind.
