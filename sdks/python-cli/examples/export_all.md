# One-shot snapshot: memories, conversations, action items, and goals

Use this recipe when you want a quick overview snapshot of your whole Omi account in a single file and a single command, instead of running four separate exports. [`export_all.py`](export_all.py) fetches memories, conversations, action items, and goals in one pass and bundles them into one JSON file with a metadata header (timestamp, per-resource counts).

```sh
python sdks/python-cli/examples/export_all.py snapshot.json
# exported snapshot to snapshot.json (memories=42, conversations=18, action_items=9, goals=3)
```

Adjust how many records per resource to fetch (default 100):

```sh
python sdks/python-cli/examples/export_all.py snapshot.json --limit 50
```

`--limit` is passed as-is to all four resources, so it must be a value every
resource accepts. Per-resource caps today: memories 200, conversations 200,
action items 500, goals 100 — so keep `--limit` at 100 or below, or the
`goal list` fetch will fail and abort the whole export.

## Scope: overview snapshot, not a guaranteed-complete backup

This is a **single page per resource** (bounded by `--limit`), not a paginated export — it's meant for a quick "what does my account look like right now" snapshot. If you need a guaranteed-complete backup of a single resource with an account beyond the page limit, use a dedicated paginated exporter for that resource instead.

## How it works

- Runs `omi --json <resource> list --limit N` once per resource (`memory`, `conversation`, `action-item`, `goal`).
- Every response is validated strictly: the CLI must exit `0`, the body must be valid UTF-8 JSON, a JSON array, and every record a JSON object. Any violation aborts the export before anything is written — a failed resource fetch never produces a partial bundle.
- The output file is written **atomically**: the bundle is written to a temporary file next to the destination and replaces it only via `os.replace` after every resource succeeds.
- The output bundle's keys are `memories`, `conversations`, `action_items`, `goals`, plus `exported_at`, `limit_per_resource`, and `counts`.

## Environment

- `OMI_BIN` — how to invoke the CLI (default `omi`). Useful for wrappers or virtualenvs, e.g. `OMI_BIN="python -m omi_cli"`.

Exit codes: `0` success · `2` the omi CLI failed · `3` the CLI returned invalid output · `1` usage or I/O error.
