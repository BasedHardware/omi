# Example: export all open action items to JSONL

[`export_open_action_items.py`](export_open_action_items.py) fetches every
**open** action item from your Omi account and writes them to a UTF-8 JSON
Lines (`.jsonl`) file, one JSON object per line:

```sh
python export_open_action_items.py open_action_items.jsonl
# exported 42 open action item(s) to open_action_items.jsonl
```

## How it works

The script drives the same CLI surface documented in
[`agent_quickstart.md`](agent_quickstart.md):

```sh
omi --json action-item list --open --limit 500 --offset N
```

- It requests pages of 500 (the `--limit` maximum) and stops at the first
  short or empty page.
- Every page is validated strictly: exit status must be 0, the body must be
  valid UTF-8 JSON, a JSON array, and every record a JSON object. Any
  violation aborts the export.
- The output file is written **atomically**: results go to a temporary file
  next to the destination and replace it only after all pages succeed. A
  failed export leaves the previous file untouched.
- Non-ASCII text (e.g. item descriptions in any language) survives the
  round-trip: the CLI is run with UTF-8 decoding and the file is written
  with `ensure_ascii=False`.

## Caveat: not a consistent snapshot

Offset pagination is not a snapshot. If items are created or completed while
the export is running, pages shift and the result may skip or repeat items.
For a stable set, run the export while nothing else is writing action items
(scripts, automations, the Omi apps) and re-run it if you need to be sure.

## Environment

- `OMI_BIN` — how to invoke the CLI (default `omi`). Useful for wrappers or
  virtualenvs, e.g. `OMI_BIN="python -m omi_cli"`.

Exit codes: `0` success · `2` the omi CLI failed · `3` the CLI returned
invalid output · `1` usage or I/O error.
