"""
Convert Omi memories JSON exports to CSV for spreadsheets, pandas, and imports.

Usage:
    # Pipe directly from omi CLI (memory list defaults to 25 records — pass
    # --limit 200 and page with --offset for larger accounts)
    omi --json memory list --limit 200 | python memories_to_csv.py - -o memories.csv
    omi --json memory list --limit 200 --offset 200 | python memories_to_csv.py - -o memories_2.csv

    # From a saved JSON export
    python memories_to_csv.py memories.json -o memories.csv

    # Filter categories, print to stdout instead of a file (stdout CSV has no
    # BOM; the BOM is only written for -o files so Excel opens them directly)
    omi --json memory list --limit 200 | python memories_to_csv.py - --category work,learnings

The converter is stdlib-only and makes no network requests. Rows are coerced
loosely (one odd record cannot crash the export), cell values are guarded
against formula injection on spreadsheet import, and the output is written as
UTF-8 with a BOM so Excel opens it correctly.
"""

import argparse
import codecs
import csv
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

FIELDS = ("id", "content", "category", "tags", "visibility", "created_at", "updated_at", "app_id")


def parse_datetime_utc(value: Any) -> Optional[str]:
    """Normalize a loosely typed timestamp to ISO-8601 UTC; None when unusable."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        try:
            dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        # Extreme but structurally valid timestamps (year 1 with an offset)
        # overflow the UTC conversion; keep the raw value instead of aborting.
        return None


def spreadsheet_text(value: Any) -> str:
    """Render a loosely typed cell value as one safe CSV text cell."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    # Avoid treating common formula prefixes as formulas on spreadsheet import.
    # The apostrophe is intentional and may be visible in some importers.
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def format_tags(tags: Any) -> str:
    """Render a loosely typed tags field as a pipe-joined cell."""
    if isinstance(tags, str):
        return tags.strip()
    if not isinstance(tags, list):
        return ""
    cleaned = [str(tag).strip() for tag in tags if tag is not None and str(tag).strip()]
    return "|".join(cleaned)


def memory_row(item: Any) -> Optional[List[str]]:
    """Coerce one memory record into a CSV row; None for unusable rows."""
    if not isinstance(item, dict):
        return None
    return [
        spreadsheet_text(item.get("id")),
        spreadsheet_text(item.get("content")),
        spreadsheet_text(item.get("category")),
        spreadsheet_text(format_tags(item.get("tags"))),
        spreadsheet_text(item.get("visibility")),
        spreadsheet_text(parse_datetime_utc(item.get("created_at")) or item.get("created_at")),
        spreadsheet_text(parse_datetime_utc(item.get("updated_at")) or item.get("updated_at")),
        spreadsheet_text(item.get("app_id") or item.get("source_app")),
    ]


def extract_memories(data: Any) -> List[Any]:
    """Unwrap memory records from bare arrays, wrapped envelopes, or single objects.

    Supports bare arrays, wrapped dicts (``memories``/``items``/``data``), and a
    single memory object. Envelopes that hold nothing memory-shaped (e.g. API
    error payloads like ``{"detail": "..."}``) return an empty list.
    """
    if isinstance(data, list):
        return list(data)
    if isinstance(data, dict):
        for key in ("memories", "items", "data"):
            val = data.get(key)
            if isinstance(val, list):
                return list(val)
        if any(key in data for key in ("content", "category", "id", "created_at")):
            return [data]
        return []
    return []


def filter_memories(
    items: List[Any],
    category_filter: Optional[str] = None,
    visibility_filter: Optional[str] = None,
) -> List[Any]:
    """Filter memory rows by category and/or visibility.

    Non-dict rows pass through untouched — ``memory_row`` drops them later — so
    one odd record cannot crash the filtered export either.
    """
    filtered = items

    if category_filter:
        target_cats = {c.strip().lower() for c in category_filter.split(",") if c.strip()}
        filtered = [
            it
            for it in filtered
            if not isinstance(it, dict) or str(it.get("category") or "").strip().lower() in target_cats
        ]

    if visibility_filter and visibility_filter.strip().lower() in {"public", "private"}:
        target_vis = visibility_filter.strip().lower()
        filtered = [
            it
            for it in filtered
            if not isinstance(it, dict) or str(it.get("visibility") or "").strip().lower() == target_vis
        ]

    return filtered


def csv_bytes(rows: List[List[str]]) -> bytes:
    """Serialize rows to deterministic CSV bytes (RFC-4180 quoting, UTF-8 BOM)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(FIELDS)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def convert(raw_json: str) -> bytes:
    """Parse raw JSON text and return the CSV export bytes (no filtering)."""
    return convert_filtered(raw_json)


def convert_filtered(raw_json: str, category: Optional[str] = None, visibility: Optional[str] = None) -> bytes:
    """Parse, unwrap, filter, and serialize memories to CSV bytes."""
    data = json.loads(raw_json)
    if not isinstance(data, (list, dict)):
        raise ValueError("Expected a JSON array of memories or an object containing 'memories'")
    items = filter_memories(extract_memories(data), category_filter=category, visibility_filter=visibility)
    rows = [row for row in (memory_row(item) for item in items) if row is not None]
    return csv_bytes(rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi memories JSON exports to CSV for spreadsheets and pandas."
    )
    parser.add_argument("input", help="Path to JSON file containing memories, or '-' to read from stdin.")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output CSV path (exclusive creation; refuses to overwrite an existing file). "
        "Defaults to stdout when omitted.",
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

    # Ensure stdout handles UTF-8 (e.g. on Windows default cp1252 consoles)
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

        payload_bytes = convert_filtered(
            raw_data,
            category=args.category,
            visibility=args.visibility if args.visibility != "all" else None,
        )
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"Error: Invalid JSON input: {exc}\n")
        return 1
    except ValueError as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 1
    except Exception as exc:  # noqa: BLE001 - one bad export must not traceback the user
        sys.stderr.write(f"Error during export: {exc}\n")
        return 1

    if args.output:
        # Format the whole export before touching the filesystem, so a
        # conversion failure cannot leave a truncated CSV behind; exclusive
        # creation protects an existing export from being clobbered. A failed
        # write removes the partial file and reports a clean error instead of
        # a traceback.
        try:
            with open(args.output, "xb") as fh:
                fh.write(payload_bytes)
        except FileExistsError:
            sys.stderr.write(f"Error: {args.output} already exists (move it aside and retry)\n")
            return 1
        except OSError as exc:
            try:
                args.output.unlink()
            except OSError:
                pass
            sys.stderr.write(f"Error: failed to write {args.output} ({exc})\n")
            return 1
        sys.stderr.write(f"Successfully exported memories to {args.output}\n")
    else:
        # Stdout is for piping into other tools: plain UTF-8 without the BOM.
        # Only -o files carry the BOM so spreadsheet apps open them directly.
        if payload_bytes.startswith(codecs.BOM_UTF8):
            payload_bytes = payload_bytes[len(codecs.BOM_UTF8) :]
        sys.stdout.buffer.write(payload_bytes)
        sys.stdout.buffer.flush()

    return 0


if __name__ == "__main__":
    sys.exit(main())
