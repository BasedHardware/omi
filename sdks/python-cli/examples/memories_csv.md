# Convert a memory and facts export to CSV

Use this recipe to review your Omi memories, facts, and learnings in a spreadsheet. It reads a
saved JSON export, makes no network requests, and does not require third-party packages.
You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export up to 200 memories:

```sh
omi --json memory list --limit 200 --offset 0 > memories.json
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account backup. To retrieve another page, increase `--offset`
by 200 and use a different filename. Changes to the account between requests
can affect offset pagination; this recipe does not promise a consistent
snapshot.

Save the following as `memories_to_csv.py`:

```python
import csv
import io
import json
import sys
from pathlib import Path

FIELDS = ("id", "content", "category", "visibility", "created_at", "tags")


def spreadsheet_text(value):
    """Render one exported field as spreadsheet-safe text.

    The dev API is loosely typed, so a field can arrive as a non-string even
    though the CLI models it as Optional[str]. One odd row must not destroy a
    whole export, so anything non-null is coerced rather than rejected.
    """
    if value is None:
        return ""
    if isinstance(value, list):
        # Format tags or arrays as semicolon-separated items
        value = "; ".join(str(item) for item in value)
    elif isinstance(value, dict):
        value = json.dumps(value, ensure_ascii=False)
    elif not isinstance(value, str):
        value = str(value)
    # Avoid treating common formula prefixes as formulas on spreadsheet import.
    # The apostrophe is intentional and may be visible in some importers.
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def convert(source, destination):
    items = json.loads(Path(source).read_bytes())
    if isinstance(items, dict):
        items = items.get("memories") or items.get("items") or items.get("data") or [items]
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json memory list")
    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each memory must be an object")
        values = (
            item.get("id"),
            item.get("content") or item.get("text") or item.get("title"),
            item.get("category"),
            item.get("visibility") or ("private" if item.get("is_private") else "public"),
            item.get("created_at") or item.get("createdAt"),
            item.get("tags") or [],
        )
        rows.append([spreadsheet_text(value) for value in values])
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


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python memories_to_csv.py INPUT.json OUTPUT.csv")
    try:
        convert(sys.argv[1], sys.argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"CSV export failed: {exc}")
```

Run the converter:

```sh
python memories_to_csv.py memories.json memories.csv
```

Open `memories.csv` in Excel, LibreOffice Calc, or Google Sheets. Columns are:

* `id` — unique Omi memory identifier.
* `content` — the recorded memory, fact, or insight text.
* `category` — memory category (e.g. `work`, `skills`, `learnings`).
* `visibility` — visibility status (`public` or `private`).
* `created_at` — ISO-8601 creation timestamp.
* `tags` — semicolon-separated tags for categorization and search.

Treat the exported file as private personal knowledge data. The CSV file contains
identifying memory records that should not be shared publicly without prior review.
