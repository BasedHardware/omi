#!/usr/bin/env python3
"""Convert Omi memory JSON exports into standard RFC 5545 iCalendar (.ics) timeline files.

Features:
- Maps memory timestamps into calendar timeline events (15-minute slot by default).
- Rich event descriptions with tags, categories, visibility, and memory identifiers.
- Multi-file ingestion with automatic ID deduplication (latest updated_at/created_at wins).
- Resilient envelope extraction (raw lists, or wrapped in "memories", "items", "data", "results").
- Strict RFC 5545 text escaping and 75-octet UTF-8 safe line folding.
- Category and tag filtering (--category, --tag).
- Path traversal protection and atomic non-destructive writes (-f/--force).
- Zero third-party dependencies: strictly Python standard library.

Usage:
    # Stream directly from omi CLI export into an iCalendar file
    omi --json memory list --limit 200 | python memories_to_ics.py - -o memories.ics

    # Convert a saved file with a custom duration and calendar title
    python memories_to_ics.py memories.json --duration-minutes 30 --name "My Personal Learnings" -o learnings.ics

    # Filter memories by category with overwrite flag
    python memories_to_ics.py memories.json --category work,skills -o work_memories.ics --force
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple

PRODID = "-//Omi Community//Omi Memories Exporter 1.0//EN"
DEFAULT_EVENT_DURATION = timedelta(minutes=15)


def ics_escape(value: Any) -> str:
    """Escape text for an iCalendar property value (RFC 5545 §3.3.11).

    Coerces arbitrary types and escapes backslashes, semicolons, commas, and line breaks.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        else:
            value = str(value)

    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\r", "\\n")
        .replace("\n", "\\n")
    )


def ics_datetime(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp string into an aware UTC datetime, or None if invalid."""
    if not isinstance(value, str) or not value.strip():
        return None
    clean_val = value.strip()
    if clean_val.endswith(("Z", "z")):
        clean_val = clean_val[:-1] + "+00:00"
    if len(clean_val) == 10 and clean_val.count("-") == 2:
        clean_val += "T00:00:00+00:00"
    try:
        dt = datetime.fromisoformat(clean_val)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def stamp_utc(dt: datetime) -> str:
    """Format an aware datetime as an RFC 5545 UTC timestamp (YYYYMMDDTHHMMSSZ)."""
    return dt.strftime("%Y%m%dT%H%M%SZ")


def fold_line(line: str, max_octets: int = 75) -> List[str]:
    """Fold an iCalendar content line at max_octets according to RFC 5545 §3.1.

    Guarantees that multi-byte UTF-8 sequences are never split across line folds.
    Continuation lines are prefixed by a single ASCII space.
    """
    encoded = line.encode("utf-8")
    if len(encoded) <= max_octets:
        return [line]

    result: List[str] = []
    chunk: List[bytes] = []
    current_len = 0
    limit = max_octets

    for char in line:
        char_bytes = char.encode("utf-8")
        if current_len + len(char_bytes) > limit:
            result.append(b"".join(chunk).decode("utf-8"))
            chunk = [b" ", char_bytes]
            current_len = 1 + len(char_bytes)
            limit = max_octets
        else:
            chunk.append(char_bytes)
            current_len += len(char_bytes)

    if chunk:
        result.append(b"".join(chunk).decode("utf-8"))

    return result


def extract_memories(data: Any) -> List[Dict[str, Any]]:
    """Unwrap arbitrary Omi memory export payloads into a flat list of memory dicts."""
    if data is None:
        return []

    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    if isinstance(data, dict):
        for key in ("memories", "items", "data", "results"):
            candidate = data.get(key)
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, dict)]
        if "content" in data or "id" in data:
            return [data]

    return []


def parse_memory_input(source: str) -> List[Dict[str, Any]]:
    """Parse JSON text or stream from standard input or a filesystem path."""
    if source == "-":
        content = sys.stdin.read()
    else:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {source}")
        content = path.read_text(encoding="utf-8-sig")

    if not content.strip():
        return []

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON input from {source}: {exc}") from exc

    return extract_memories(parsed)


def _generate_synthetic_id(memory: Dict[str, Any]) -> str:
    """Generate a stable synthetic ID for memories without an explicit ID."""
    hasher = hashlib.sha256()
    hasher.update(str(memory.get("content", "")).encode("utf-8"))
    hasher.update(str(memory.get("created_at", "")).encode("utf-8"))
    hasher.update(str(memory.get("category", "")).encode("utf-8"))
    return f"syn_{hasher.hexdigest()[:16]}"


def _sort_timestamp_key(memory: Dict[str, Any]) -> Tuple[int, str]:
    """Extract a canonical timestamp key for conflict resolution using aware UTC datetimes."""
    raw = str(memory.get("updated_at") or memory.get("created_at") or "")
    dt = ics_datetime(raw)
    return (int(dt.timestamp()) if dt else -1, raw)


def deduplicate_memories(memories_list: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate memories by ID, preferring the most recently updated record.

    Anonymous memories derive a deterministic synthetic ID so identical records merge
    instead of producing duplicate UIDs that violate RFC 5545 §3.8.4.7.
    """
    seen: Dict[str, Dict[str, Any]] = {}
    ordered_ids: List[str] = []

    for memory in memories_list:
        raw_id = memory.get("id")
        mem_id = str(raw_id).strip() if raw_id is not None else None
        if not mem_id:
            mem_id = _generate_synthetic_id(memory)

        if mem_id in seen:
            existing = seen[mem_id]
            if _sort_timestamp_key(memory) > _sort_timestamp_key(existing):
                seen[mem_id] = memory
        else:
            seen[mem_id] = memory
            ordered_ids.append(mem_id)

    return [seen[k] for k in ordered_ids]


def memory_to_vevent(
    memory: Dict[str, Any],
    now_stamp: str,
    duration: timedelta = DEFAULT_EVENT_DURATION,
) -> Optional[List[str]]:
    """Convert an individual memory dict into RFC 5545 VEVENT content lines."""
    created_dt = ics_datetime(memory.get("created_at"))
    if created_dt is None:
        return None

    raw_id = memory.get("id")
    memory_id = str(raw_id).strip() if raw_id is not None else ""
    if not memory_id:
        memory_id = _generate_synthetic_id(memory)

    content_raw = memory.get("content")
    content_str = str(content_raw).strip() if content_raw is not None else ""

    if content_str:
        first_line = content_str.splitlines()[0].strip()
        summary = first_line[:60].strip()
        if len(first_line) > 60:
            summary += "..."
    else:
        summary = "(untitled memory)"

    try:
        end_dt = created_dt + duration
    except OverflowError:
        end_dt = datetime.max.replace(tzinfo=timezone.utc)

    dtstart = stamp_utc(created_dt)
    dtend = stamp_utc(end_dt)

    description_lines = []
    if content_str:
        description_lines.append(content_str)
    description_lines.append(f"Memory ID: {memory_id}")

    category = memory.get("category")
    if category:
        description_lines.append(f"Category: {category}")

    tags = memory.get("tags")
    clean_tags: List[str] = []
    if isinstance(tags, list):
        clean_tags = [str(t).strip() for t in tags if t is not None and str(t).strip()]
        if clean_tags:
            description_lines.append(f"Tags: {', '.join(clean_tags)}")

    visibility = memory.get("visibility")
    if visibility:
        description_lines.append(f"Visibility: {visibility}")

    if memory.get("updated_at"):
        description_lines.append(f"Updated At: {memory.get('updated_at')}")

    categories = ["Omi", "Memories"]
    if category:
        categories.append(str(category).capitalize())
    for t in clean_tags:
        categories.append(t)

    categories_val = ",".join(ics_escape(c) for c in categories)
    description_val = ics_escape("\n".join(description_lines))
    summary_val = ics_escape(summary)

    lines = [
        "BEGIN:VEVENT",
        f"UID:omi-memory-{memory_id}@omi-cli",
        f"DTSTAMP:{now_stamp}",
        f"DTSTART:{dtstart}",
        f"DTEND:{dtend}",
        f"SUMMARY:{summary_val}",
        f"DESCRIPTION:{description_val}",
        "STATUS:CONFIRMED",
        f"CATEGORIES:{categories_val}",
        "END:VEVENT",
    ]
    return lines


def generate_ics(
    memories: Sequence[Dict[str, Any]],
    calendar_name: str = "Omi Memories",
    category_filter: Optional[Sequence[str]] = None,
    tag_filter: Optional[Sequence[str]] = None,
    duration: timedelta = DEFAULT_EVENT_DURATION,
) -> Tuple[str, int, int]:
    """Generate RFC 5545 iCalendar data from memories.

    Returns:
        Tuple of (ics_text, written_events_count, skipped_count).
    """
    now_stamp = stamp_utc(datetime.now(timezone.utc))

    cat_set = {c.strip().lower() for c in category_filter if c.strip()} if category_filter else None
    tag_set = {t.strip().lower() for t in tag_filter if t.strip()} if tag_filter else None

    body_lines: List[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{ics_escape(calendar_name)}",
    ]

    written_count = 0
    skipped_count = 0

    for memory in memories:
        if cat_set:
            mem_cat = str(memory.get("category") or "").strip().lower()
            if mem_cat not in cat_set:
                continue

        if tag_set:
            mem_tags = memory.get("tags")
            mem_tags_set = (
                {str(t).strip().lower() for t in mem_tags if t is not None}
                if isinstance(mem_tags, list)
                else set()
            )
            if not mem_tags_set.intersection(tag_set):
                continue

        event_lines = memory_to_vevent(memory, now_stamp, duration)
        if event_lines is None:
            skipped_count += 1
            continue

        body_lines.extend(event_lines)
        written_count += 1

    body_lines.append("END:VCALENDAR")

    folded_lines: List[str] = []
    for line in body_lines:
        folded_lines.extend(fold_line(line))

    ics_content = "\r\n".join(folded_lines) + "\r\n"
    return ics_content, written_count, skipped_count


def write_ics(output_path_str: str, ics_content: str, force: bool = False) -> None:
    """Atomically write iCalendar content to destination with path traversal protection."""
    if ".." in Path(output_path_str).parts or ".." in output_path_str:
        raise ValueError(f"Path traversal detected: refusing relative path containing '..' ({output_path_str})")

    destination = Path(output_path_str).resolve()

    if destination.exists() and not force:
        raise FileExistsError(
            f"Destination file already exists: {destination}. Use -f/--force to overwrite."
        )

    destination.parent.mkdir(parents=True, exist_ok=True)

    temp_fd, temp_path = tempfile.mkstemp(
        prefix="omi_memories_",
        suffix=".tmp",
        dir=str(destination.parent),
    )
    f = os.fdopen(temp_fd, "wb")
    try:
        f.write(ics_content.encode("utf-8"))
        f.flush()
        os.fsync(f.fileno())
        f.close()
        os.replace(temp_path, destination)
    except Exception:
        try:
            f.close()
        except Exception:
            pass
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Convert Omi memory JSON exports to standard iCalendar (.ics) timeline files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="One or more input JSON files, or '-' to read from standard input.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Destination .ics file path, or '-' for standard output (default: '-').",
    )
    parser.add_argument(
        "--name",
        default="Omi Memories",
        help="Calendar display name (default: 'Omi Memories').",
    )
    parser.add_argument(
        "--category",
        help="Filter by comma-separated memory categories (e.g. 'work,skills').",
    )
    parser.add_argument(
        "--tag",
        help="Filter by comma-separated memory tags (e.g. 'python,ai').",
    )
    parser.add_argument(
        "--duration-minutes",
        type=int,
        default=15,
        help="Duration in minutes assigned to each memory event slot (default: 15).",
    )
    parser.add_argument(
        "-f",
        "--force",
        "--overwrite",
        dest="force",
        action="store_true",
        help="Overwrite destination file if it already exists.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Command-line entrypoint for the memories to iCalendar converter."""
    parser = build_parser()
    args = parser.parse_args(argv)

    raw_memories: List[Dict[str, Any]] = []
    for source in args.inputs:
        try:
            items = parse_memory_input(source)
            raw_memories.extend(items)
        except Exception as exc:
            sys.stderr.write(f"Error reading {source}: {exc}\n")
            return 1

    memories = deduplicate_memories(raw_memories)

    cat_filter = [c.strip() for c in args.category.split(",")] if args.category else None
    tag_filter = [t.strip() for t in args.tag.split(",")] if args.tag else None
    duration = timedelta(minutes=max(1, args.duration_minutes))

    ics_data, written, skipped = generate_ics(
        memories,
        calendar_name=args.name,
        category_filter=cat_filter,
        tag_filter=tag_filter,
        duration=duration,
    )

    if args.output == "-":
        try:
            # Use binary buffer write to prevent Windows C-runtime CRLF expansion to CRCRLF
            sys.stdout.buffer.write(ics_data.encode("utf-8"))
            sys.stdout.buffer.flush()
        except BrokenPipeError:
            return 0
    else:
        try:
            write_ics(args.output, ics_data, force=args.force)
        except Exception as exc:
            sys.stderr.write(f"Error writing iCalendar output: {exc}\n")
            return 1

        sys.stderr.write(
            f"Successfully exported {written} memory event(s) ({skipped} skipped without created_at) to {args.output}\n"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
