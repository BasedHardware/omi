# Export every action item to JSONL (full, paginated backup)

`omi action-item list` caps out at `--limit 500` per call, so a full-account export needs pagination. [`export_action_items.py`](export_action_items.py) drives the CLI as a subprocess, pages through **every** action item — open and completed — and writes one JSON object per line to a UTF-8 JSON Lines (`.jsonl`) file, streaming well into downstream tools (`jq`, log pipelines, ML/embedding ingestion) without loading the whole export into memory.

This is a full-account backup across all states (open and completed).

```sh
python sdks/python-cli/examples/export_action_items.py action_items.jsonl
# exported 318 action item(s) to action_items.jsonl
```

## How it works

- Pages through `omi --json action-item list --limit 500 --offset N`, requesting 500 (the CLI's `--limit` maximum) per call and continuing until an empty page.
- Every page is validated strictly: the CLI must exit `0`, the body must be valid UTF-8 JSON, a JSON array, and every record a JSON object. Any violation aborts the export before anything is written.
- The output file is written **atomically**: records stream to a temporary file next to the destination and replace it only after every page succeeds. A failed export leaves the previous file untouched and no temp file behind.
- Non-ASCII text round-trips losslessly (`ensure_ascii=False`).

## Caveats

- **Offset pagination is not a snapshot**: If action items are created or completed while the export runs, pages can shift and the result may skip or repeat an item. Run the export while the account is quiet, or re-run it, if you need a guaranteed-complete set.
- **Short pages do not signal the end**: The developer API filters locked or malformed records after pagination, so a page can legitimately return fewer than 500 items while subsequent pages still contain data. The exporter continues until an empty page is returned.

## Environment

- `OMI_BIN` — how to invoke the CLI (default `omi`). Useful for wrappers or virtualenvs, e.g. `OMI_BIN="python -m omi_cli"`.

Exit codes: `0` success · `2` the omi CLI failed · `3` the CLI returned invalid output · `1` usage or I/O error.
