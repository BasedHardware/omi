import csv
import io
import json
import sys
from pathlib import Path

FIELDS = (
    "id",
    "title",
    "goal_type",
    "current_value",
    "target_value",
    "progress_pct",
    "unit",
    "is_active",
    "created_at",
    "updated_at",
)


def spreadsheet_text(value):
    """Render one exported field as spreadsheet-safe text.

    Coerces non-null values safely to strings and escapes common formula
    prefixes (=, +, -, @) to prevent CSV injection vulnerabilities.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def boolean_text(value):
    """Render is_active status as clean boolean string ('true' or 'false')."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return "true" if value else "false"
    if isinstance(value, str):
        return "true" if value.strip().lower() in ("true", "1", "yes", "active") else "false"
    return "true"  # Default to active


def compute_progress_pct(current, target):
    """Calculate progress percentage safely as a clean string."""
    if current is None or target is None:
        return "0.0"
    try:
        c = float(current)
        t = float(target)
        if t <= 0:
            return "0.0"
        return str(round((c / t) * 100.0, 2))
    except (ValueError, TypeError, ZeroDivisionError):
        return "0.0"


def convert(source, destination):
    """Convert an Omi goals JSON export to a CSV file."""
    content = Path(source).read_bytes().decode("utf-8-sig")
    items = json.loads(content)
    if isinstance(items, dict):
        items = (
            items.get("goals")
            or items.get("items")
            or items.get("data")
            or [items]
        )
    if not isinstance(items, list):
        raise ValueError(f"{source}: expected a JSON array or object containing goals")

    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source}: each goal must be an object")
        item_id = item.get("id")
        if item_id is None or str(item_id).strip() == "":
            raise ValueError(f"{source}: goal is missing an id")

        title = item.get("title") or item.get("name") or item.get("description") or ""
        curr = item.get("current_value")
        target = item.get("target_value")
        progress_pct = compute_progress_pct(curr, target)
        is_active = boolean_text(item.get("is_active"))

        values = (
            item_id,
            title,
            item.get("goal_type"),
            curr,
            target,
            progress_pct,
            item.get("unit"),
            is_active,
            item.get("created_at"),
            item.get("updated_at"),
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
        sys.exit("Usage: python goals_to_csv.py INPUT.json OUTPUT.csv")
    try:
        convert(sys.argv[1], sys.argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"CSV export failed: {exc}")
