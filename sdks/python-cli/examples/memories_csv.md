# Convert a memory-list export to CSV

Use this recipe to review, sort and filter your Omi memories in a spreadsheet.
It reads a saved JSON export, makes no network requests, and writes one CSV row
per memory with the full content text. You need Python 3.10+ and an
authenticated `omi-cli` for the initial export.

Export up to 200 memories:

```sh
omi --json memory list --limit 200 --offset 0 > memories.json
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account backup. To retrieve another page, increase `--offset`
by 200 and use a different filename. Changes to the account between requests
can affect offset pagination; this recipe does not promise a consistent
snapshot. To export only some categories, add the server-side filter, for
example `--categories work,learnings`.

Save the following as `memories_to_csv.py`:

```python
import csv
import io
import json
import sys
from pathlib import Path

FIELDS = ("id", "category", "visibility", "content", "tags", "created_at", "updated_at",
          "manually_added", "reviewed")


def spreadsheet_text(value):
    """Render one exported field as spreadsheet-safe text.

    The dev API is loosely typed, so a field can arrive as a non-string even
    though the CLI models it as a string. One odd row must not destroy a whole
    export, so anything non-null is coerced rather than rejected.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    # Avoid treating common formula prefixes as formulas on spreadsheet import.
    # The apostrophe is intentional and may be visible in some importers.
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def tag_text(tags):
    """Join the tag list with '; ' so it stays a single cell; anything else is coerced."""
    if tags is None:
        return ""
    if isinstance(tags, list) and all(isinstance(tag, str) for tag in tags):
        return "; ".join(tags)
    return spreadsheet_text(tags)


def convert(source, destination):
    items = json.loads(Path(source).read_bytes())
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json memory list")
    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each memory must be an object")
        values = (item.get("id"), item.get("category"), item.get("visibility"), item.get("content"),
                  tag_text(item.get("tags")), item.get("created_at"), item.get("updated_at"),
                  item.get("manually_added"), item.get("reviewed"))
        rows.append([value if key == "tags" else spreadsheet_text(value) for key, value in zip(FIELDS, values)])
    # Format and encode the whole export before touching the filesystem, so a
    # conversion failure cannot leave a truncated CSV behind for the next run.
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(FIELDS)
    writer.writerows(rows)
    payload = buffer.getvalue().encode("utf-8-sig")
    output_path = Path(destination)
    # Exclusive creation still protects an existing export.
    try:
        output = output_path.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {output_path}") from None
    try:
        with output:
            output.write(payload)
    except OSError:
        # Leave no partial export behind when the write itself fails.
        output_path.unlink(missing_ok=True)
        raise
    return len(rows)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python memories_to_csv.py INPUT.json OUTPUT.csv")
    try:
        count = convert(sys.argv[1], sys.argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"CSV export failed: {exc}")
    print(f"{count} memory row(s) written")
```

Run the converter:

```sh
python memories_to_csv.py memories.json memories.csv
```

Import the result as UTF-8, comma-delimited text in Excel or another
spreadsheet application. Each row holds the full memory content (up to the
500-character limit the CLI enforces on writes), so filter the `category`
column to review one area at a time, or sort by `created_at` to see what Omi
learned recently. Tags are joined with `; ` in a single cell; `manually_added`
and `reviewed` are written as `true` / `false`. Missing fields become empty
cells; an empty list produces the column header only. The converter preserves
complete IDs, accents, quoted text and embedded newlines, refuses to overwrite
an existing destination, and a failed write leaves no partial file behind.
Treat the exported file as private data. For exact unmodified values, retain
the source JSON; the CSV adds an apostrophe to common formula-like values to
make their intended text interpretation explicit.
