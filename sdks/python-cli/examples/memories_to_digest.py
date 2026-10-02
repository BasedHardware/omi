"""Generate a concise Markdown digest of Omi memories, categories, and knowledge clusters.

Usage:
    # Print digest to stdout from saved export
    python memories_to_digest.py memories.json

    # Write digest to file with local timezone offset
    python memories_to_digest.py memories.json -o digest.md --utc-offset +09:00

    # Pipeline stream from omi CLI
    omi --json memory list --limit 200 | python memories_to_digest.py - -o digest.md
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple
import uuid

CATEGORY_META: Dict[str, Dict[str, str]] = {
    "work": {"label": "Work", "emoji": "💼"},
    "skills": {"label": "Skills", "emoji": "🎯"},
    "personal": {"label": "Personal", "emoji": "👤"},
    "learnings": {"label": "Learnings", "emoji": "🧠"},
    "interests": {"label": "Interests", "emoji": "💡"},
    "habits": {"label": "Habits", "emoji": "⚡"},
    "lifestyle": {"label": "Lifestyle", "emoji": "🌿"},
    "hobbies": {"label": "Hobbies", "emoji": "🎨"},
    "core": {"label": "Core Facts", "emoji": "📌"},
    "interesting": {"label": "Interesting", "emoji": "✨"},
    "manual": {"label": "Manual Notes", "emoji": "✍️"},
    "workflow": {"label": "Workflow", "emoji": "🔄"},
    "system": {"label": "System", "emoji": "⚙️"},
    "other": {"label": "Other Facts", "emoji": "📝"},
}


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


def parse_offset(value: str) -> timedelta:
    """Turn '+09:00' / '-05:30' into a timedelta with strict boundary checking (-14:00 to +14:00)."""
    if len(value) != 6 or value[0] not in "+-" or value[3] != ":" or not (value[1:3] + value[4:]).isdigit():
        raise ValueError(f"UTC offset must look like +09:00 or -05:00, got {value!r}")
    hours = int(value[1:3])
    minutes = int(value[4:])
    if minutes > 59 or hours > 14 or (hours == 14 and minutes > 0):
        raise ValueError(f"UTC offset {value!r} out of valid range (-14:00 to +14:00)")
    delta = timedelta(hours=hours, minutes=minutes)
    return -delta if value[0] == "-" else delta


def clean_markdown_cell(value: Any) -> str:
    """Sanitize arbitrary user strings for safe Markdown table and list rendering."""
    if value is None:
        return ""
    text = str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    text = text.replace("\\", "\\\\")
    for char in ("|", "*", "_", "`", "[", "]", "<", ">", "#"):
        text = text.replace(char, f"\\{char}")
    return " ".join(text.split())


def extract_tags(raw_tags: Any) -> List[str]:
    """Normalize tags into a clean deduplicated list of alphanumeric strings."""
    if raw_tags is None:
        return []
    seen: set[str] = set()
    tags_list: List[str] = []
    candidates: List[Any] = []
    if isinstance(raw_tags, list):
        candidates = raw_tags
    elif isinstance(raw_tags, str):
        candidates = raw_tags.split(",")
    for item in candidates:
        if item is not None:
            cleaned = re.sub(r"[^\w-]", "", str(item)).strip().lower()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                tags_list.append(cleaned)
    return tags_list


def is_memory_record(raw: Any) -> bool:
    """Check whether a dictionary represents an Omi memory record."""
    if not isinstance(raw, dict):
        return False
    return any(key in raw for key in ("content", "category", "structured", "created_at"))


def unwrap_memories(raw: Any, source_label: str) -> List[Any]:
    """Extract memory records from various JSON envelopes or return the bare list."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("memories", "items", "data", "results"):
            val = raw.get(key)
            if isinstance(val, list):
                return val
        if is_memory_record(raw):
            return [raw]
        return []
    raise ValueError(f"{source_label}: expected JSON array or object containing memories")


def load(sources: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """Load and deduplicate memories from files or stdin."""
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
        items = unwrap_memories(raw, source_label)
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"{source_label} item {idx}: each memory must be an object")
            item_id = item.get("id")
            if item_id is not None and str(item_id).strip():
                clean_id = str(item_id).strip()
            else:
                clean_id = f"auto_{uuid.uuid4().hex}"
                while clean_id in items_by_id:
                    clean_id = f"auto_{uuid.uuid4().hex}"
            items_by_id[clean_id] = item
    return items_by_id


def build_digest(
    items_by_id: Dict[str, Dict[str, Any]],
    offset: timedelta = timedelta(0),
    offset_label: str = "",
    category_filter: Optional[str] = None,
    now: Optional[datetime] = None,
) -> str:
    """Generate Markdown digest with category breakdowns, tag clusters, and timeline analytics."""
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    filter_cat = category_filter.strip().lower() if category_filter else None

    # Filter items
    active_items: List[Tuple[str, Dict[str, Any]]] = []
    for item_id, item in items_by_id.items():
        cat = str(item.get("category") or "other").strip().lower()
        if filter_cat and cat != filter_cat:
            continue
        active_items.append((item_id, item))

    total = len(active_items)
    if total == 0:
        return "# Omi Memories Digest\n\n_No memories found matching the export criteria._\n"

    # Aggregations
    by_category: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    tag_counter: Counter[str] = Counter()
    per_month: Counter[str] = Counter()
    tagged_count = 0
    private_count = 0
    dated_items: List[Tuple[datetime, str, str, str]] = []  # (dt, content, cat, id)

    for item_id, item in active_items:
        cat = str(item.get("category") or "other").strip().lower()
        by_category[cat].append(item)

        tags = extract_tags(item.get("tags"))
        if tags:
            tagged_count += 1
            for t in tags:
                tag_counter[t] += 1

        vis = str(item.get("visibility") or "").strip().lower()
        if vis == "private" or item.get("private") is True:
            private_count += 1

        dt = parse_time(item.get("created_at"))
        content = clean_markdown_cell(item.get("content") or "Untitled memory")
        if dt is not None:
            local_dt = dt + offset
            per_month[local_dt.strftime("%Y-%m")] += 1
            dated_items.append((dt, content, cat, item_id))

    dated_items.sort(key=lambda x: (x[0], x[3]), reverse=True)

    lines: List[str] = [
        "# Omi Memories Digest",
        "",
        (
            f"**Total Memories:** {total} · **Categories:** {len(by_category)} · "
            f"**Tagged:** {tagged_count} ({(tagged_count / total * 100.0):.1f}%) · "
            f"**Private:** {private_count} ({(private_count / total * 100.0):.1f}%)"
        ),
        "",
        "## Summary",
        "",
        "| Metric | Count | Ratio |",
        "|---|---:|---:|",
        f"| Total Memories | {total} | 100.0% |",
        f"| Unique Categories | {len(by_category)} | - |",
        f"| Tagged Memories | {tagged_count} | {(tagged_count / total * 100.0):.1f}% |",
        f"| Private Memories | {private_count} | {(private_count / total * 100.0):.1f}% |",
        f"| Unique Tags Identified | {len(tag_counter)} | - |",
        "",
        "## Categories Breakdown",
        "",
        "| Category | Memories | Share | Top Tags |",
        "|---|---:|---:|---|",
    ]

    # Sort categories by count descending, then name
    sorted_cats = sorted(by_category.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    for cat_name, cat_items in sorted_cats:
        meta = CATEGORY_META.get(cat_name, {"label": cat_name.replace("_", " ").title(), "emoji": "📁"})
        clean_label = clean_markdown_cell(meta["label"])
        cat_tag_counter: Counter[str] = Counter()
        for it in cat_items:
            for t in extract_tags(it.get("tags")):
                cat_tag_counter[t] += 1
        top_tags_str = ", ".join(f"`#{t}`" for t, _ in cat_tag_counter.most_common(3)) or "_none_"
        share = len(cat_items) / total * 100.0
        lines.append(f"| {meta['emoji']} {clean_label} | {len(cat_items)} | {share:.1f}% | {top_tags_str} |")

    if tag_counter:
        lines += [
            "",
            "## Top Knowledge Tags",
            "",
            "| Tag | Mentions | Share |",
            "|---|---:|---:|",
        ]
        for tag_name, count in tag_counter.most_common(10):
            share = count / total * 100.0
            lines.append(f"| `#{tag_name}` | {count} | {share:.1f}% |")

    if per_month:
        lines += [
            "",
            "## Monthly Capture Cadence",
            "",
            "| Month | Memories Recorded |",
            "|---|---:|",
        ]
        for month_str in sorted(per_month.keys(), reverse=True):
            lines.append(f"| {month_str} | {per_month[month_str]} |")

    if dated_items:
        lines += [
            "",
            "## Recent Memory Highlights",
            "",
        ]
        for dt, content, cat, item_id in dated_items[:5]:
            local_dt = dt + offset
            meta = CATEGORY_META.get(cat, {"label": cat.replace("_", " ").title(), "emoji": "📁"})
            clean_label = clean_markdown_cell(meta["label"])
            clean_content = clean_markdown_cell(content)
            preview = (clean_content[:117] + "...") if len(clean_content) > 120 else clean_content
            lines.append(
                f"- **{meta['emoji']} {clean_label}**: {preview} "
                f"· _({local_dt.strftime('%Y-%m-%d %H:%M')})_ · `{item_id}`"
            )

    time_note = f" at {offset_label}" if offset_label else " in UTC"
    ref_time_str = (now + offset).strftime("%Y-%m-%d %H:%M:%S")
    lines += ["", f"_Digest generated based on reference time {ref_time_str}{time_note}._\n"]
    return "\n".join(lines)


def convert(
    sources: Sequence[str],
    destination: Optional[str] = None,
    offset: timedelta = timedelta(0),
    offset_label: str = "",
    category_filter: Optional[str] = None,
    overwrite: bool = False,
    now: Optional[datetime] = None,
) -> int:
    """Load memories from sources, generate Markdown digest, and write to destination or stdout."""
    items = load(sources)
    digest_text = build_digest(
        items,
        offset=offset,
        offset_label=offset_label,
        category_filter=category_filter,
        now=now,
    )
    payload = digest_text.encode("utf-8")

    filter_cat = category_filter.strip().lower() if category_filter else None
    row_count = sum(
        1
        for item in items.values()
        if not filter_cat or str(item.get("category") or "other").strip().lower() == filter_cat
    )

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
        # Atomic write to temporary file in same directory with default permissions, then replace destination
        tmp_name = f".tmp_memories_digest_{uuid.uuid4().hex}.md"
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
        description="Convert Omi memories JSON exports into a Markdown digest."
    )
    parser.add_argument("inputs", nargs="+", help="One or more memory JSON export files, or '-' for stdin")
    parser.add_argument("-o", "--output", help="Destination Markdown file path (defaults to stdout)")
    parser.add_argument(
        "--category",
        default=None,
        help="Filter memories by category (e.g. work, skills, learnings)",
    )
    parser.add_argument(
        "--utc-offset",
        default="",
        help="Local UTC offset, e.g. +09:00 or --utc-offset=-05:00",
    )
    parser.add_argument("--overwrite", action="store_true", help="Allow overwriting existing destination file")

    args = parser.parse_args(argv)

    offset = timedelta(0)
    offset_label = ""
    if args.utc_offset:
        try:
            offset = parse_offset(args.utc_offset)
            offset_label = args.utc_offset
        except ValueError as exc:
            sys.exit(f"Digest failed: {exc}")

    try:
        count = convert(
            args.inputs,
            destination=args.output,
            offset=offset,
            offset_label=offset_label,
            category_filter=args.category,
            overwrite=args.overwrite,
        )
        if args.output and args.output != "-":
            print(f"Digest written to {args.output} ({count} memories)")
        return 0
    except BrokenPipeError:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        sys.exit(1)
    except (OSError, ValueError) as exc:
        sys.exit(f"Digest failed: {exc}")


if __name__ == "__main__":
    sys.exit(main())
