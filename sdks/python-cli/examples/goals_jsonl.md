# Convert a goal-list export to JSONL (with computed progress)

Use this recipe when you want your tracked goals as a UTF-8 JSON Lines (`.jsonl`) file — one goal per line — for streaming into downstream tools (`jq`, log pipelines, ML/embedding ingestion) instead of loading a single large JSON array into memory. It reads a saved JSON export and makes no network requests.

You need Python 3.10+ and an authenticated `omi-cli` for the initial export (no extra dependencies — stdlib only).

Export tracked goals:

```sh
omi --json goal list --limit 100 --include-inactive > goals.json
```

Run the converter:

```sh
python sdks/python-cli/examples/goals_to_jsonl.py goals.json goals.jsonl
```

Each output line is the original goal object plus a computed `progress_pct` field (0.0–1.0), computed from `current_value / target_value`, falling back to the `min_value`–`max_value` range when `target_value` isn't usable. `progress_pct` is `null` when neither is computable.

The converter refuses to overwrite an existing destination, and a failed write leaves no partial file behind.
