"""Publish Omi action items as an Atom 1.0 syndication feed (RFC 4287).

Usage:
    # Print Atom XML feed to stdout from saved export
    python action_items_to_atom.py tasks.json

    # Write feed to file for NetNewsWire / Thunderbird subscription
    python action_items_to_atom.py tasks.json -o tasks.atom

    # Filter to open pending tasks only
    python action_items_to_atom.py tasks.json --status open -o open_tasks.atom

    # Pipeline stream from omi CLI
    omi --json action-item list --limit 200 | python action_items_to_atom.py - -o tasks.atom
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import quote
import uuid
from xml.sax.saxutils import escape

FEED_TITLE = "Omi Action Items"
FEED_ID = "urn:omi:action-items"
EPOCH = "1970-01-01T00:00:00Z"
DONE_WORDS = {"true", "yes", "1", "done", "completed", "x"}


def is_completed(value: Any) -> bool:
    """Normalize completion state handling booleans, numbers, and strings."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in DONE_WORDS
    return False


def xml_text(value: Any) -> str:
    """Render a field as XML-safe text, dropping C0 control codes and lone surrogates."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    collapsed = " ".join(value.split())
    return "".join(ch for ch in collapsed if ch >= " " and not "\ud800" <= ch <= "\udfff")


def parse_time(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None if unusable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
        return parsed
    except (ValueError, OverflowError):
        return None


def rfc3339(moment: datetime) -> str:
    """Atom timestamps must follow RFC 3339 formatted in UTC."""
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def unwrap_items(raw: Any, source_label: str) -> List[Any]:
    """Extract action items from various JSON envelopes or return bare list."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("action_items", "items", "data", "results"):
            val = raw.get(key)
            if isinstance(val, list):
                return val
        if any(k in raw for k in ("description", "completed", "due_at", "created_at")):
            return [raw]
        return []
    raise ValueError(f"{source_label}: expected JSON array or object containing action items")


def load(sources: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """Load and deduplicate action items from files or stdin."""
    items_by_id: Dict[str, Dict[str, Any]] = {}
    for source in sources:
        if source == "-":
            content = sys.stdin.buffer.read()
            source_label = "stdin"
        else:
            source_label = source
            content = Path(source).read_bytes()

        if not content.strip():
            continue

        raw = json.loads(content.decode("utf-8-sig"))
        items = unwrap_items(raw, source_label)
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"{source_label} item {idx}: each action item must be an object")
            item_id = item.get("id")
            if item_id is not None and str(item_id).strip():
                clean_id = str(item_id).strip()
            else:
                clean_id = f"auto_{uuid.uuid4().hex}"
                while clean_id in items_by_id:
                    clean_id = f"auto_{uuid.uuid4().hex}"
            items_by_id[clean_id] = item
    return items_by_id


def build_entries(items_by_id: Dict[str, Dict[str, Any]], status_filter: str = "all") -> List[Dict[str, Any]]:
    """Filter and build sorted Atom entry records from action items."""
    filter_mode = status_filter.strip().lower() if status_filter else "all"
    rows: List[Dict[str, Any]] = []

    for item_id, item in items_by_id.items():
        completed = is_completed(item.get("completed", False))
        if filter_mode == "open" and completed:
            continue
        if filter_mode == "completed" and not completed:
            continue

        created_dt = parse_time(item.get("created_at"))
        updated_dt = parse_time(item.get("updated_at")) or created_dt
        due_dt = parse_time(item.get("due_at"))

        desc = xml_text(item.get("description") or "Untitled task")
        status_label = "Completed" if completed else "Open"
        status_term = "completed" if completed else "open"
        prefix = "[DONE]" if completed else "[OPEN]"

        details = [f"Status: {status_label}"]
        if due_dt is not None:
            details.append(f"Due: {due_dt.strftime('%Y-%m-%d %H:%M UTC')}")
        if created_dt is not None:
            details.append(f"Created: {created_dt.strftime('%Y-%m-%d')}")
        conv_id = item.get("conversation_id")
        if conv_id and str(conv_id).strip():
            details.append(f"Conversation: {xml_text(str(conv_id).strip())}")

        sort_time = updated_dt or created_dt or due_dt or datetime.min.replace(tzinfo=timezone.utc)

        rows.append({
            "id": item_id,
            "title": f"{prefix} {desc}",
            "description": desc,
            "completed": completed,
            "status_term": status_term,
            "status_label": status_label,
            "published": created_dt,
            "updated": updated_dt or created_dt,
            "due": due_dt,
            "summary": " · ".join(details),
            "sort_time": sort_time,
        })

    rows.sort(key=lambda r: (r["sort_time"], r["id"]), reverse=True)
    return rows


def build_feed(rows: List[Dict[str, Any]], feed_title: str = FEED_TITLE) -> str:
    """Format entries into a valid RFC 4287 Atom XML document."""
    stamps = [rfc3339(row["updated"]) for row in rows if row.get("updated") is not None]
    feed_updated = max(stamps) if stamps else EPOCH

    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom">',
        f"  <title>{escape(feed_title)}</title>",
        f"  <id>{FEED_ID}</id>",
        f"  <updated>{feed_updated}</updated>",
        "  <author>",
        "    <name>Omi</name>",
        "  </author>",
        "  <generator uri=\"https://github.com/BasedHardware/omi\">omi-cli action_items_to_atom.py</generator>",
    ]

    for row in rows:
        clean_id = quote(str(row["id"]), safe="")
        updated_stamp = rfc3339(row["updated"]) if row.get("updated") is not None else EPOCH
        parts.append("  <entry>")
        parts.append(f"    <title>{escape(row['title'])}</title>")
        parts.append(f"    <id>urn:omi:action-item:{clean_id}</id>")
        parts.append(f"    <updated>{updated_stamp}</updated>")
        if row.get("published") is not None:
            parts.append(f"    <published>{rfc3339(row['published'])}</published>")
        parts.append(f'    <category term="{row["status_term"]}" label="{row["status_label"]}"/>')
        parts.append(f"    <summary type=\"text\">{escape(row['summary'])}</summary>")
        content_html = f"<p><strong>{escape(row['description'])}</strong></p><p>{escape(row['summary'])}</p>"
        parts.append(f"    <content type=\"html\">{escape(content_html)}</content>")
        parts.append("  </entry>")

    parts.append("</feed>\n")
    return "\n".join(parts)


def convert(
    sources: Sequence[str],
    destination: Optional[str] = None,
    status_filter: str = "all",
    feed_title: str = FEED_TITLE,
    overwrite: bool = False,
) -> int:
    """Load action items, build Atom XML feed, and write to destination file or stdout."""
    items = load(sources)
    entries = build_entries(items, status_filter=status_filter)
    xml_data = build_feed(entries, feed_title=feed_title)
    payload = xml_data.encode("utf-8")
    row_count = len(entries)

    if not destination or destination == "-":
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
        return row_count

    output_path = Path(destination)
    parent_dir = output_path.parent
    parent_dir.mkdir(parents=True, exist_ok=True)

    if not overwrite:
        try:
            output = output_path.open("xb")
        except FileExistsError:
            raise FileExistsError(
                f"Refusing to overwrite existing {output_path} (use --overwrite to replace)"
            ) from None
        try:
            with output:
                output.write(payload)
        except OSError:
            output_path.unlink(missing_ok=True)
            raise
    else:
        tmp_name = f".tmp_action_items_atom_{uuid.uuid4().hex}.xml"
        tmp_path = parent_dir / tmp_name
        try:
            with tmp_path.open("xb") as tmp_file:
                tmp_file.write(payload)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            tmp_path.replace(output_path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

    return row_count


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publish Omi action items JSON exports as an Atom 1.0 syndication feed."
    )
    parser.add_argument("inputs", nargs="+", help="One or more action items JSON export files, or '-' for stdin")
    parser.add_argument("-o", "--output", help="Destination Atom XML file path (defaults to stdout)")
    parser.add_argument(
        "--status",
        choices=["all", "open", "completed"],
        default="all",
        help="Filter items by status (default: all)",
    )
    parser.add_argument(
        "--title",
        default=FEED_TITLE,
        help=f"Feed title (default: '{FEED_TITLE}')",
    )
    parser.add_argument("--overwrite", action="store_true", help="Allow overwriting existing destination file")

    args = parser.parse_args(argv)

    try:
        count = convert(
            args.inputs,
            destination=args.output,
            status_filter=args.status,
            feed_title=args.title,
            overwrite=args.overwrite,
        )
        if args.output and args.output != "-":
            print(f"Atom feed written to {args.output} ({count} action items)")
        return 0
    except BrokenPipeError:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return 1
    except (OSError, ValueError) as exc:
        sys.exit(f"Atom feed generation failed: {exc}")


if __name__ == "__main__":
    sys.exit(main())
