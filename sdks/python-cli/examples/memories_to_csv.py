import csv
import io
import json
import sys
from pathlib import Path

FIELDS = ("id", "category", "visibility", "content", "tags", "created_at")


def spreadsheet_text(value):
    """Render one exported field as spreadsheet-safe text.

    Avoid treating common formula prefixes as formulas on spreadsheet import.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def convert(source, destination):
    items = json.loads(Path(source).read_bytes())
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json memory list")

    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each memory must be an object")

        tags = item.get("tags")
        if isinstance(tags, list):
            tags_str = ", ".join(str(t) for t in tags if t)
        elif tags is None:
            tags_str = ""
        else:
            tags_str = str(tags)

        values = (
            item.get("id"),
            item.get("category"),
            item.get("visibility"),
            item.get("content"),
            tags_str,
            item.get("created_at"),
        )
        rows.append([spreadsheet_text(v) for v in values])

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(FIELDS)
    writer.writerows(rows)
    payload = buffer.getvalue().encode("utf-8-sig")

    output_path = Path(destination)
    try:
        output = output_path.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {output_path}") from None
    try:
        with output:
            output.write(payload)
    except OSError:
        output_path.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python memories_to_csv.py INPUT.json OUTPUT.csv")
    try:
        convert(sys.argv[1], sys.argv[2])
    except Exception as exc:
        sys.exit(f"Error: {exc}")
