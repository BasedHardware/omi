# Convert a conversations export to JSONL

Use this recipe to convert a saved `omi --json conversations list` export into a
JSONL file. The script makes no network requests and never deletes data;
it only reads the local export and writes the target file.

Export a page of conversations:

```sh
omi --json conversations list --limit 200 --offset 0 > conversations_0.json
```

Check that the command exited 0 before converting — an empty or partial file is
not a backup. Page through more data by raising `--offset` (e.g. 200, 400…).

Install any needed dependency, then run:

```sh
python conversations_to_jsonl.py conversations_0.json conversations.jsonl
```

The converter validates the output path, normalises timestamps to UTC, drops
unpaired surrogates that would break UTF-8 encoders, and keeps the raw JSON per
row so nothing from the export is lost.
