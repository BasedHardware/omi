"""Export Omi action items to CSV or TSV spreadsheets with security hygiene.

Converts action item JSON exports into CSV/TSV format suitable for importing
into Todoist, Notion Database, Google Sheets, Microsoft Excel, or Unix text pipelines.

Features:
- Reads from file path or stdin stream (omi --json action-item list | python action_items_to_csv.py -).
- Spreadsheet formula injection defense (escapes =, +, -, @ prefixes on text fields).
- Status filtering (--status open | completed | all).
- Flexible sorting (--sort-by due_at | created_at | updated_at | status).
- UTF-8 with BOM support (--excel-bom) for seamless opening in Excel without encoding issues.
- TSV mode (--tsv) for unix pipeline integration (awk, cut, grep).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

DEFAULT_COLUMNS = [
    "id",
    "description",
    "completed",
    "due_at_utc",
    "created_at_utc",
    "updated_at_utc",
    "conversation_id",
]

INJECTION_CHARS = ("=", "+", "-", "@", "\t", "\r")


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


def format_datetime_utc(iso_str: Optional[str]) -> str:
    """Format an ISO datetime string into UTC 'YYYY-MM-DD HH:MM:SS' or empty string."""
    dt = parse_datetime(iso_str)
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def sanitize_cell(value: Any, defend_formula_injection: bool = True) -> str:
    """Sanitize cell value and protect against spreadsheet formula injection."""
    if value is None:
        return ""
    text = str(value)

    if defend_formula_injection and text.startswith(INJECTION_CHARS):
        # Allow bare negative or positive integers/floats without prefix escaping
        if not re.match(r"^[-+]?\d+(\.\d+)?$", text):
            text = f"'{text}"

    return text


def load_items(source: str) -> List[Dict[str, Any]]:
    """Load action items from a file path or stdin string."""
    if source == "-":
        content = sys.stdin.read()
    else:
        content = Path(source).read_bytes().decode("utf-8-sig")

    if not content.strip():
        return []

    data = json.loads(content)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    elif isinstance(data, dict):
        if "action_items" in data and isinstance(data["action_items"], list):
            return [item for item in data["action_items"] if isinstance(item, dict)]
        if "items" in data and isinstance(data["items"], list):
            return [item for item in data["items"] if isinstance(item, dict)]
        # Single item payload
        if "description" in data or "id" in data:
            return [data]
        return []
    return []


def filter_and_sort_items(
    items: List[Dict[str, Any]],
    status_filter: str = "all",
    sort_by: str = "none",
    reverse: bool = False,
) -> List[Dict[str, Any]]:
    """Filter action items by completion status and sort by specified key."""
    status_lower = (status_filter or "all").lower().strip()
    if status_lower in ("open", "pending", "todo"):
        filtered = [it for it in items if not it.get("completed")]
    elif status_lower in ("completed", "done", "closed"):
        filtered = [it for it in items if bool(it.get("completed"))]
    else:
        filtered = list(items)

    sort_lower = (sort_by or "none").lower().strip()
    if sort_lower in ("due_at", "due"):
        filtered.sort(
            key=lambda x: parse_datetime(x.get("due_at")) or datetime.max.replace(tzinfo=timezone.utc),
            reverse=reverse,
        )
    elif sort_lower in ("created_at", "created"):
        filtered.sort(
            key=lambda x: parse_datetime(x.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=reverse,
        )
    elif sort_lower in ("updated_at", "updated"):
        filtered.sort(
            key=lambda x: parse_datetime(x.get("updated_at")) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=reverse,
        )
    elif sort_lower in ("status", "completed"):
        filtered.sort(key=lambda x: bool(x.get("completed")), reverse=reverse)
    elif sort_lower in ("id",):
        filtered.sort(key=lambda x: str(x.get("id") or ""), reverse=reverse)
    elif reverse:
        filtered.reverse()

    return filtered


def item_to_row(
    item: Dict[str, Any],
    bool_format: str = "true_false",
    defend_formula_injection: bool = True,
    flatten_newlines: bool = True,
) -> List[str]:
    """Convert an action item dictionary into a sanitized CSV row list."""
    item_id = str(item.get("id") or "").strip()

    raw_desc = str(item.get("description") or "").strip()
    if flatten_newlines:
        raw_desc = " ".join(raw_desc.splitlines())

    completed_val = bool(item.get("completed", False))
    bool_fmt = (bool_format or "true_false").lower().strip()
    if bool_fmt == "check":
        completed_str = "[x]" if completed_val else "[ ]"
    elif bool_fmt == "boolean":
        completed_str = "true" if completed_val else "false"
    elif bool_fmt in ("int", "numeric", "0_1"):
        completed_str = "1" if completed_val else "0"
    else:
        completed_str = "TRUE" if completed_val else "FALSE"

    due_at_utc = format_datetime_utc(item.get("due_at"))
    created_at_utc = format_datetime_utc(item.get("created_at"))
    updated_at_utc = format_datetime_utc(item.get("updated_at"))
    conv_id = str(item.get("conversation_id") or "").strip()

    row = [
        sanitize_cell(item_id, defend_formula_injection),
        sanitize_cell(raw_desc, defend_formula_injection),
        completed_str,
        due_at_utc,
        created_at_utc,
        updated_at_utc,
        sanitize_cell(conv_id, defend_formula_injection),
    ]
    return row


def export_csv(
    items: List[Dict[str, Any]],
    output_path: Optional[str] = None,
    delimiter: str = ",",
    include_header: bool = True,
    bool_format: str = "true_false",
    defend_formula_injection: bool = True,
    flatten_newlines: bool = True,
    excel_bom: bool = False,
) -> str:
    """Export action items into CSV/TSV formatted string or write to file."""
    rows: List[List[str]] = []
    if include_header:
        rows.append(DEFAULT_COLUMNS)

    for item in items:
        rows.append(
            item_to_row(
                item,
                bool_format=bool_format,
                defend_formula_injection=defend_formula_injection,
                flatten_newlines=flatten_newlines,
            )
        )

    import io

    output_stream = io.StringIO()
    writer = csv.writer(output_stream, delimiter=delimiter, lineterminator="\n")
    writer.writerows(rows)
    content = output_stream.getvalue()

    if output_path:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        encoding = "utf-8-sig" if excel_bom else "utf-8"
        out_file.write_text(content, encoding=encoding)

    return content


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert Omi action items JSON exports into clean CSV or TSV spreadsheets."
    )
    parser.add_argument(
        "source",
        nargs="?",
        default="-",
        help="Path to action items JSON file or '-' to read from standard input (default: -).",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Path to output file. If omitted, prints directly to stdout.",
    )
    parser.add_argument(
        "--status",
        choices=["all", "open", "completed"],
        default="all",
        help="Filter items by status: 'all', 'open', or 'completed' (default: all).",
    )
    parser.add_argument(
        "--sort-by",
        choices=["none", "due_at", "created_at", "updated_at", "status", "id"],
        default="none",
        help="Sort items by specified field (default: none).",
    )
    parser.add_argument(
        "--reverse",
        action="store_true",
        help="Reverse sorting order.",
    )
    parser.add_argument(
        "--tsv",
        action="store_true",
        help="Output tab-separated values (TSV) instead of comma-separated (CSV).",
    )
    parser.add_argument(
        "--delimiter",
        default=",",
        help="Custom delimiter character (ignored if --tsv is set).",
    )
    parser.add_argument(
        "--no-header",
        action="store_true",
        help="Omit the header row from the exported CSV/TSV.",
    )
    parser.add_argument(
        "--bool-format",
        choices=["true_false", "boolean", "check", "int"],
        default="true_false",
        help="Format for completed column: 'true_false' (TRUE/FALSE), 'boolean' (true/false), 'check' ([x]/[ ]), 'int' (1/0).",
    )
    parser.add_argument(
        "--no-formula-defense",
        action="store_true",
        help="Disable formula injection escaping prefix (') on =, +, -, @ strings.",
    )
    parser.add_argument(
        "--excel-bom",
        action="store_true",
        help="Include UTF-8 BOM when saving to file for older Excel compatibility.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        raw_items = load_items(args.source)
    except Exception as exc:
        sys.stderr.write(f"Error reading action items input: {exc}\n")
        return 1

    processed_items = filter_and_sort_items(
        raw_items,
        status_filter=args.status,
        sort_by=args.sort_by,
        reverse=args.reverse,
    )

    delimiter = "\t" if args.tsv else args.delimiter

    csv_content = export_csv(
        processed_items,
        output_path=args.output,
        delimiter=delimiter,
        include_header=not args.no_header,
        bool_format=args.bool_format,
        defend_formula_injection=not args.no_formula_defense,
        excel_bom=args.excel_bom,
    )

    if not args.output:
        sys.stdout.write(csv_content)

    return 0


if __name__ == "__main__":
    sys.exit(main())
