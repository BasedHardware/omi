# Convert a goals export to TODOTXT

Use this recipe to convert a saved `omi --json goals list` export into a
TODOTXT file. The script makes no network requests and never deletes data;
it only reads the local export and writes the target file.

Export a page of goals:

```sh
omi --json goals list --limit 200 --offset 0 > goals_0.json
```

Check that the command exited 0 before converting — an empty or partial file is
not a backup. Page through more data by raising `--offset` (e.g. 200, 400…).

Install any needed dependency, then run:

```sh
python goals_to_todotxt.py goals_0.json goals.txt
```

The converter validates the output path, normalises timestamps to UTC, drops
unpaired surrogates that would break UTF-8 encoders, and keeps the raw JSON per
row so nothing from the export is lost.
