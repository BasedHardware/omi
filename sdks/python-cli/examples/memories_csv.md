# Convert a memory-list export to CSV

Use this recipe to review memory metadata and content in a spreadsheet. It reads
a saved JSON export, makes no network requests, and writes one CSV file. You
need Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export up to 200 memories (the CLI caps `--limit` at 200):

```sh
omi --json memory list --limit 200 --offset 0 > memories.json
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account backup. To retrieve another page, increase `--offset`
by 200 and use a different filename. Changes to the account between requests
can affect offset pagination; this recipe does not promise a consistent
snapshot.

Save the following as `memories_to_csv.py` (the same script is kept next to
this recipe as [`memories_to_csv.py`](memories_to_csv.py) and covered by
`tests/test_memories_to_csv.py`):

```python
import csv
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FIELDS = ("id", "category", "created_at", "manually_added", "content")


def spreadsheet_text(value):
    """Render one exported field as spreadsheet-safe text.

    The dev API is loosely typed, so a field can arrive as a non-string even
    though the CLI models it as Optional[str]. One odd row must not destroy a
    whole export, so anything non-null is coerced rather than rejected.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    # Avoid treating common formula prefixes as formulas on spreadsheet import.
    # The apostrophe is intentional and may be visible in some importers.
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def utc_text(value):
    """Render an ISO-8601 timestamp as UTC text, or keep it verbatim if unusable.

    Memories arrive with timestamps from several clients, so some carry an
    offset and some do not. A naive timestamp is read as UTC, which matches the
    server's own storage, and everything is rendered in one format so that
    spreadsheet sorting is stable.
    """
    if not isinstance(value, str) or not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def memory_content(item):
    """Return the memory text, or an empty string when it is absent.

    The list endpoint models the payload as `content: Optional[str]`, so a
    missing or null value becomes an empty cell rather than an error.
    """
    content = item.get("content")
    if isinstance(content, str) and content.strip():
        return content
    return ""


def convert(source, destination):
    items = json.loads(Path(source).read_bytes())
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json memory list")
    rows = []
    known_categories = set()
    undated = 0
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each memory must be an object")
        created = utc_text(item.get("created_at"))
        if not created:
            undated += 1
        category = item.get("category")
        if isinstance(category, str) and category:
            known_categories.add(category)
        values = (item.get("id"), category, created,
                  item.get("manually_added"), memory_content(item))
        rows.append([spreadsheet_text(value) for value in values])
    rows.sort(key=lambda row: (row[2] == "", row[2], row[0]))
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
    return len(rows), len(known_categories), undated


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python memories_to_csv.py INPUT.json OUTPUT.csv")
    try:
        written, categories, undated = convert(sys.argv[1], sys.argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"CSV export failed: {exc}")
    print(f"{written} memory row(s) written, {categories} category value(s), {undated} without a timestamp")
```

Run the converter:

```sh
python memories_to_csv.py memories.json memories.csv
```

Import the result as UTF-8, comma-delimited text in Excel or another
spreadsheet application. The converter preserves complete IDs, accents, quoted
text and embedded newlines. Rows are sorted by timestamp, then by ID, so two
exports of the same page compare directly; rows without a timestamp sort last
and are counted in the summary line. Missing fields become empty cells; an
empty list produces the column header only. It refuses to overwrite an
existing destination, and a failed write leaves no partial file behind. Treat
the exported file as private memory data. For exact unmodified values, retain
the source JSON; the CSV adds an apostrophe to common formula-like values to
make their intended text interpretation explicit.
