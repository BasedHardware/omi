# Convert a action items export to CSV

Use this recipe to convert a saved `omi --json action-items list` export into a
CSV file. The script makes no network requests and never deletes data;
it only reads the local export and writes the target file.

Export a page of action items:

```sh
omi --json action-items list --limit 200 --offset 0 > action_items_0.json
```

Check that the command exited 0 before converting — an empty or partial file is
not a backup. Page through more data by raising `--offset` (e.g. 200, 400…).

Install any needed dependency, then run:

```sh
python action_items_to_csv.py action_items_0.json action_items.csv
```

The converter validates the output path, normalises timestamps to UTC, drops
unpaired surrogates that would break UTF-8 encoders, and keeps the raw JSON per
row so nothing from the export is lost.
