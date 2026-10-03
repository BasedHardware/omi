"""
Convert Omi memories JSON exports to a clean CSV spreadsheet.

Complements memories_to_markdown.py with a tabular export for Excel, Google
Sheets, Numbers, and pandas. stdlib-only (csv module); no third-party deps.

Usage:
    # Pipe directly from omi CLI to stdout (with an explicit page limit)
    omi --json memory list --limit 100 | python memories_to_csv.py -

    # Export to a specific CSV file
    omi --json memory list --limit 100 | python memories_to_csv.py - --output memories.csv

    # Larger accounts: page through memories with --offset, then concatenate
    omi --json memory list --limit 100 --offset 0 | python memories_to_csv.py - --output page0.csv
    omi --json memory list --limit 100 --offset 100 | python memories_to_csv.py - --output page1.csv

    # Export a saved JSON export
    python memories_to_csv.py memories.json --output memories.csv

    # Filter specific categories and visibility
    omi --json memory list --limit 100 | python memories_to_csv.py - --category work,learnings --visibility private

Note: ``omi memory list`` returns only its default page (25 items) unless you
pass ``--limit``. Use ``--limit`` together with ``--offset`` to page through
larger accounts so older memories are not silently omitted.

Security: spreadsheet cells that would begin with ``=``, ``+``, ``-``, ``@``,
or a tab/CR are prefixed with a single quote (``'``) so that opening the file
in a spreadsheet cannot trigger formula injection. This matches the safeguard
in the action_items -> CSV recipe (#20288).
"""

import argparse
import csv
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


COLUMNS = ["id", "content", "category", "visibility", "tags", "created_at"]

# Characters that can turn a spreadsheet cell into a formula / command.
# Line feed is included because some spreadsheet applications treat a leading
# newline as the start of a formula context.
_FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r", "\n")


def parse_datetime(iso_str: Optional[str]) -> Optional[datetime]:
    """Safely parse an ISO-8601 datetime string and normalize to UTC."""
    if not iso_str or not isinstance(iso_str, str):
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception:
        return None


def sanitize_cell(value: str) -> str:
    """Neutralize spreadsheet formula injection for a single cell.

    Leading whitespace is stripped before testing so values such as
    ``" =1+1"`` are still guarded instead of slipping through as an
    executable formula.
    """
    if value.lstrip(" \t\r\n").startswith(_FORMULA_LEAD):
        return "'" + value
    return value


def _tags_str(item: Dict[str, Any]) -> str:
    tags = item.get("tags")
    if isinstance(tags, list):
        return ";".join(str(t) for t in tags if t)
    return ""


def format_row(item: Dict[str, Any]) -> Dict[str, str]:
    """Render one memory dict as a CSV row keyed by COLUMNS."""
    content = str(item.get("content") or "").strip()
    created_dt = parse_datetime(item.get("created_at"))
    return {
        "id": sanitize_cell(str(item.get("id") or "")),
        "content": sanitize_cell(content),
        "category": sanitize_cell(str(item.get("category") or "")),
        "visibility": sanitize_cell(str(item.get("visibility") or "")),
        "tags": sanitize_cell(_tags_str(item)),
        "created_at": created_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if created_dt else "",
    }


def extract_memories(data: Any) -> List[Dict[str, Any]]:
    """Unwrap memory records from bare arrays, wrapped envelopes, or single objects."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("memories", "items", "data"):
            val = data.get(key)
            if isinstance(val, list):
                return [item for item in val if isinstance(item, dict)]
        if any(key in data for key in ("content", "category", "id", "created_at")):
            return [data]
        return []
    return []


def filter_memories(
    items: List[Dict[str, Any]],
    category_filter: Optional[str] = None,
    visibility_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Filter memories by category and/or visibility."""
    filtered = items

    if category_filter:
        target_cats = {c.strip().lower() for c in category_filter.split(",") if c.strip()}
        filtered = [
            it for it in filtered
            if str(it.get("category") or "").strip().lower() in target_cats
        ]

    if visibility_filter:
        target_vis = visibility_filter.strip().lower()
        if target_vis in {"public", "private"}:
            filtered = [
                it for it in filtered
                if str(it.get("visibility") or "").strip().lower() == target_vis
            ]

    return filtered


def memories_to_csv(items: List[Dict[str, Any]]) -> str:
    """Render a list of memories into a CSV document (header + one row per memory)."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    for it in items:
        writer.writerow(format_row(it))
    return buf.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi memories JSON exports to a CSV spreadsheet."
    )
    parser.add_argument(
        "input",
        help="Path to JSON file containing memories, or '-' to read from stdin.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Path to output CSV file. Defaults to stdout if omitted.",
    )
    parser.add_argument(
        "--category",
        "-c",
        type=str,
        default=None,
        help="Filter by category (comma-separated list, e.g. 'work,skills,learnings').",
    )
    parser.add_argument(
        "--visibility",
        type=str,
        choices=["all", "public", "private"],
        default="all",
        help="Filter by visibility (default: all).",
    )

    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    try:
        if args.input == "-":
            raw_data = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
        else:
            input_path = Path(args.input)
            if not input_path.exists():
                sys.stderr.write(f"Error: Input file does not exist: {args.input}\n")
                return 1
            raw_data = input_path.read_bytes().decode("utf-8-sig", errors="replace")

        if not raw_data.strip():
            sys.stderr.write("Error: Input payload is empty.\n")
            return 1

        payload = json.loads(raw_data)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"Error: Invalid JSON input: {exc}\n")
        return 1
    except Exception as exc:
        sys.stderr.write(f"Error reading input: {exc}\n")
        return 1

    if not isinstance(payload, (list, dict)):
        sys.stderr.write("Error: Expected a JSON array of memories or object containing 'memories'.\n")
        return 1

    items = filter_memories(
        extract_memories(payload),
        category_filter=args.category,
        visibility_filter=args.visibility if args.visibility != "all" else None,
    )

    csv_doc = memories_to_csv(items)

    try:
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(csv_doc, encoding="utf-8")
            sys.stderr.write(f"Successfully exported {len(items)} memory/memories to {args.output}\n")
        else:
            try:
                sys.stdout.write(csv_doc)
            except UnicodeEncodeError:
                sys.stdout.buffer.write(csv_doc.encode("utf-8", errors="replace"))
        return 0
    except Exception as exc:
        sys.stderr.write(f"Error during export: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
