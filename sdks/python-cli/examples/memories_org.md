# Turn memories and knowledge base into an Org-mode outline

Use this recipe to work through Omi's memories, facts, and learnings in Emacs Org mode, or in an Org app such as Orgzly or beorg. It reads a saved JSON export, makes no network requests, and writes structured `.org` files: each memory becomes an Org outline node with metadata properties (`:OMI_ID:`, `:CATEGORY:`, `:DATE:`, `:CREATED:`, `:VISIBILITY:`, `:TAGS:`), category or date group headings, and body content. You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export memories and knowledge base:

```sh
omi --json memory list --limit 500 > memories.json
```

Or pipe directly into the converter:

```sh
omi --json memory list | python memories_to_org.py -
```

Check that the command succeeded before converting the file. Add `--category` or `--visibility` to filter specific records.

Save the following as `memories_to_org.py` (the same script is kept next to this recipe as [`memories_to_org.py`](memories_to_org.py) and covered by `tests/test_memories_to_org.py`):

```python
"""Convert Omi memories JSON exports to Emacs Org-mode outline notes.

See memories_org.md for the full recipe.

Usage:
    # Pipe directly from omi CLI
    omi --json memory list | python memories_to_org.py -

    # Export to a specific Org-mode file
    python memories_to_org.py memories.json omi_memories.org --utc-offset +09:00

    # Export into category-specific or date-specific Org files in a directory
    python memories_to_org.py memories.json --output-dir ./org_memories/ --group-by category

    # Filter specific categories (e.g. work and learnings)
    python memories_to_org.py memories.json --category work,learnings
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple, Union

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
ZWSP = "​"  # zero-width space, Org's documented escape character

CATEGORY_META: Dict[str, Dict[str, str]] = {
    "work": {"label": "Work", "emoji": "💼"},
    "skills": {"label": "Skills", "emoji": "🎯"},
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

DEFAULT_CATEGORY_ORDER: List[str] = [
    "work", "skills", "learnings", "interests", "habits",
    "lifestyle", "hobbies", "core", "interesting", "workflow",
    "manual", "system", "other",
]


def one_line(value: Any) -> str:
    """Render one exported field as single-line text safely coercing non-strings."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(value.split())


def heading_text(value: Any) -> str:
    """Keep a memory content or title from being parsed as Org syntax inside a heading."""
    text = one_line(value) or "(Untitled memory)"
    if text.startswith("[#"):
        text = ZWSP + text  # prevent priority cookie
    text = re.sub(r"([<\[])(?=\d{4}-\d{2}-\d{2})", "\\1" + ZWSP, text)  # prevent stray agenda timestamps
    if re.search(r":[\w@#%:]+:\s*$", text):
        text = text.rstrip() + ZWSP  # prevent stray heading tags
    return text


def clean_org_tag(tag: Any) -> str:
    """Sanitize arbitrary strings into valid Org-mode tags."""
    if not tag:
        return ""
    clean = re.sub(r"[^\w@#%]", "_", str(tag)).strip("_")
    return clean


def parse_offset(text: Optional[str]) -> timezone:
    """Parse time zone offset in +HH:MM or -HH:MM format."""
    match = re.fullmatch(r"([+-])(\d{2}):(\d{2})", text or "")
    if not match or int(match.group(2)) > 14 or int(match.group(3)) > 59:
        raise argparse.ArgumentTypeError("use +HH:MM or -HH:MM between -14:00 and +14:00")
    delta = timedelta(hours=int(match.group(2)), minutes=int(match.group(3)))
    if delta > timedelta(hours=14):
        raise argparse.ArgumentTypeError("use +HH:MM or -HH:MM between -14:00 and +14:00")
    return timezone(delta if match.group(1) == "+" else -delta)


def local_time(value: Any, zone: timezone) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into local wall-clock time, or None if unusable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(zone)


def org_stamp(dt: datetime, active: bool = False) -> str:
    """Format a datetime into an Org inactive [YYYY-MM-DD Day HH:MM] or active timestamp."""
    body = f"{dt:%Y-%m-%d} {WEEKDAYS[dt.weekday()]} {dt:%H:%M}"
    return f"<{body}>" if active else f"[{body}]"


def extract_memories(data: Any) -> List[Dict[str, Any]]:
    """Unwrap memory records from bare arrays, wrapped envelopes, or single objects.

    Supports:
    - Bare arrays: [ {...}, {...} ]
    - Wrapped dicts: {"memories": [...]}, {"items": [...]}, {"data": [...]}
    - Single memory dict: { "id": "...", "content": "..." }

    Ensures that empty envelopes like {"memories": []} return an empty list
    instead of falling through and creating phantom untitled memories.
    """
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


def format_memory_entry(item: Dict[str, Any], zone: timezone, level: int = 1) -> str:
    """Format a single memory item as an Org-mode subtree at the given heading level."""
    mem_id = item.get("id") or "unknown"
    category = str(item.get("category") or "").strip().lower() or "other"
    visibility = item.get("visibility")
    created_at = item.get("created_at") or ""
    updated_at = item.get("updated_at") or ""

    raw_content = str(item.get("content") or "").strip()
    if not raw_content:
        raw_content = "(Untitled memory)"

    lines_in_content = raw_content.splitlines()
    first_line = lines_in_content[0].strip() if lines_in_content else "(Untitled memory)"

    if len(lines_in_content) > 1 or len(first_line) > 120:
        heading_title = heading_text(first_line[:117] + "..." if len(first_line) > 120 else first_line)
        body_text = raw_content
    else:
        heading_title = heading_text(raw_content)
        body_text = ""

    # Parse and sanitize tags
    raw_tags = item.get("tags")
    tags: List[str] = []
    if isinstance(raw_tags, list):
        for t in raw_tags:
            c = clean_org_tag(t)
            if c and c not in tags:
                tags.append(c)

    prefix = "*" * level
    tag_suffix = f" :{':'.join(tags)}:" if tags else ""
    lines: List[str] = [f"{prefix} {heading_title}{tag_suffix}"]

    # Properties Drawer
    lines.append(":PROPERTIES:")
    lines.append(f":OMI_ID: {one_line(mem_id)}")
    lines.append(f":CATEGORY: {one_line(category)}")

    created_dt = local_time(created_at, zone)
    if created_dt:
        lines.append(f":DATE: {org_stamp(created_dt, active=False)}")
        lines.append(f":CREATED: {org_stamp(created_dt, active=False)}")

    updated_dt = local_time(updated_at, zone)
    if updated_dt:
        lines.append(f":UPDATED: {org_stamp(updated_dt, active=False)}")

    if visibility:
        lines.append(f":VISIBILITY: {one_line(visibility).lower()}")

    if tags:
        lines.append(f":TAGS: {' '.join(tags)}")

    lines.append(":END:")

    if body_text:
        lines.append(body_text)

    return "\n".join(lines)


def get_category_heading(cat: str, level: int = 1) -> str:
    """Format category section heading with emoji and tag."""
    cat_lower = (cat or "").strip().lower()
    meta = CATEGORY_META.get(cat_lower)
    tag = clean_org_tag(cat_lower)
    tag_part = f" :{tag}:" if tag else ""
    prefix = "*" * level

    if meta:
        return f"{prefix} {meta['emoji']} {meta['label']}{tag_part}"
    formatted_label = cat.replace("_", " ").title() if cat else "Uncategorized"
    return f"{prefix} 📁 {formatted_label}{tag_part}"


def export_single_file(
    memories: List[Dict[str, Any]],
    destination: Path,
    zone: timezone,
    group_by: str = "category",
    title: str = "Omi Memories & Knowledge Base",
    overwrite: bool = False,
) -> int:
    """Export all memories into one consolidated Org-mode master file."""
    now_dt = datetime.now(zone)
    lines = [
        "# -*- mode: org; coding: utf-8 -*-",
        f"#+TITLE: {title}",
        "#+AUTHOR: Omi",
        f"#+DATE: {org_stamp(now_dt, active=False)}",
        "",
    ]

    if not memories:
        lines.append("* Empty Memory Vault")
        lines.append("No memories found matching criteria.")
        lines.append("")
    elif group_by == "category":
        category_groups: Dict[str, List[Dict[str, Any]]] = {}
        for it in memories:
            cat = str(it.get("category") or "").strip().lower()
            key = cat if cat else "other"
            category_groups.setdefault(key, []).append(it)

        ordered_keys = [k for k in DEFAULT_CATEGORY_ORDER if k in category_groups]
        for k in sorted(category_groups.keys()):
            if k not in ordered_keys:
                ordered_keys.append(k)

        for cat_key in ordered_keys:
            group_items = category_groups[cat_key]
            lines.append(get_category_heading(cat_key, level=1))
            for it in group_items:
                lines.append(format_memory_entry(it, zone, level=2))
            lines.append("")

    elif group_by == "date":
        date_groups: Dict[str, List[Dict[str, Any]]] = {}
        for it in memories:
            created_dt = local_time(it.get("created_at"), zone)
            key = created_dt.strftime("%Y-%m-%d") if created_dt else "Undated"
            date_groups.setdefault(key, []).append(it)

        for date_key in sorted(date_groups.keys(), reverse=True):
            lines.append(f"* 📅 {date_key}")
            for it in date_groups[date_key]:
                lines.append(format_memory_entry(it, zone, level=2))
            lines.append("")

    else:  # group_by == "none"
        for it in memories:
            lines.append(format_memory_entry(it, zone, level=1))
        lines.append("")

    payload = ("\n".join(lines).rstrip() + "\n").encode("utf-8")
    if not overwrite:
        try:
            output = destination.open("xb")
        except FileExistsError:
            raise FileExistsError(f"Refusing to overwrite existing {destination}") from None
    else:
        output = destination.open("wb")

    try:
        with output:
            output.write(payload)
    except OSError:
        destination.unlink(missing_ok=True)
        raise

    return len(memories)


def _sanitize_group_key(group_key: str) -> str:
    """Turn a group key (category or date) into a filesystem-safe slug."""
    return re.sub(r"[^\w-]", "_", group_key).strip("_") or "memories"


def _allocate_unique_filenames(safe_keys: Dict[str, str]) -> Dict[str, str]:
    """Map every group key to its own <slug>_memories.org filename with deterministic collision handling."""
    natural_names = {f"{safe_key}_memories.org".casefold() for safe_key in safe_keys.values()}
    used_names: Set[str] = set()
    filenames: Dict[str, str] = {}

    for group_key in sorted(safe_keys):
        safe_key = safe_keys[group_key]
        filename = f"{safe_key}_memories.org"
        if filename.casefold() in used_names:
            counter = 2
            while True:
                candidate = f"{safe_key}_{counter}_memories.org"
                folded = candidate.casefold()
                if folded not in used_names and folded not in natural_names:
                    break
                counter += 1
            filename = candidate
        used_names.add(filename.casefold())
        filenames[group_key] = filename

    return filenames


def export_directory(
    memories: List[Dict[str, Any]],
    output_dir: Path,
    zone: timezone,
    group_by: str = "category",
    title_prefix: str = "Omi Memories",
    overwrite: bool = False,
) -> List[Path]:
    """Export memories into individual .org files in output_dir grouped by category or date."""
    output_dir.mkdir(parents=True, exist_ok=True)
    resolved_dir = output_dir.resolve()
    written_files: List[Path] = []

    groups: Dict[str, List[Dict[str, Any]]] = {}
    if group_by == "date":
        for it in memories:
            created_dt = local_time(it.get("created_at"), zone)
            date_str = created_dt.strftime("%Y-%m-%d") if created_dt else "undated"
            groups.setdefault(date_str, []).append(it)
    else:
        for it in memories:
            cat = str(it.get("category") or "").strip().lower()
            key = cat if cat else "other"
            groups.setdefault(key, []).append(it)

    filenames = _allocate_unique_filenames({gk: _sanitize_group_key(gk) for gk in groups})

    for group_key, group_items in sorted(groups.items()):
        filename = filenames[group_key]
        target_path = (output_dir / filename).resolve()

        if not str(target_path).startswith(str(resolved_dir)):
            continue

        doc_title = f"{title_prefix} — {group_key.replace('_', ' ').title()}"
        export_single_file(
            group_items,
            target_path,
            zone,
            group_by="none",
            title=doc_title,
            overwrite=overwrite,
        )
        written_files.append(target_path)

    return written_files


def convert(
    source: Union[str, Path],
    destination: Union[str, Path],
    zone: timezone,
    output_dir: Optional[Union[str, Path]] = None,
    group_by: str = "category",
    category_filter: Optional[str] = None,
    visibility_filter: Optional[str] = None,
    overwrite: bool = False,
) -> int:
    """High-level conversion entrypoint."""
    if str(source) == "-":
        stream = getattr(sys.stdin, "buffer", sys.stdin)
        data = stream.read()
        raw_content = data.decode("utf-8-sig") if isinstance(data, bytes) else data
    else:
        source_path = Path(source)
        raw_content = source_path.read_bytes().decode("utf-8-sig")

    if not raw_content.strip():
        items: List[Dict[str, Any]] = []
    else:
        raw_json = json.loads(raw_content)
        items = extract_memories(raw_json)

    filtered = filter_memories(items, category_filter=category_filter, visibility_filter=visibility_filter)

    if output_dir:
        dest_dir = Path(output_dir)
        exported = export_directory(filtered, dest_dir, zone, group_by=group_by, overwrite=overwrite)
        return len(exported)

    dest_path = Path(destination)
    if dest_path.is_dir() or str(destination).endswith(("/", "\\")):
        exported = export_directory(filtered, dest_path, zone, group_by=group_by, overwrite=overwrite)
        return len(exported)

    return export_single_file(filtered, dest_path, zone, group_by=group_by, overwrite=overwrite)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert an Omi memories export to Emacs Org-mode outline notes.")
    parser.add_argument("source", help="JSON from omi --json memory list, or '-' for stdin pipe")
    parser.add_argument("destination", nargs="?", default="omi_memories.org",
                        help="new .org file to create, or directory (default: omi_memories.org)")
    parser.add_argument("--output-dir", help="export individual .org files into this directory")
    parser.add_argument("--group-by", choices=["category", "date", "none"], default="category",
                        help="group memories by 'category' (default), 'date', or 'none' (flat)")
    parser.add_argument("--category", help="filter memories by category (comma-separated, e.g. work,learnings)")
    parser.add_argument("--visibility", choices=["public", "private"], help="filter memories by visibility")
    parser.add_argument("--utc-offset", type=parse_offset, default=None,
                        help="format times at this offset (e.g. +09:00); default: computer's local time zone")
    parser.add_argument("--force", action="store_true", help="overwrite existing file(s)")
    args = parser.parse_args()

    zone = args.utc_offset or datetime.now().astimezone().tzinfo
    try:
        count = convert(
            args.source,
            args.destination,
            zone,
            output_dir=args.output_dir,
            group_by=args.group_by,
            category_filter=args.category,
            visibility_filter=args.visibility,
            overwrite=args.force,
        )
        print(f"Successfully exported {count} memory group(s)/file to Org-mode.")
    except (OSError, ValueError) as exc:
        sys.exit(f"Org export failed: {exc}")
```

Run the converter:

```sh
# Export into a single Org-mode master file
python memories_to_org.py memories.json omi_memories.org

# Export category-specific notes into a folder
python memories_to_org.py memories.json --output-dir ./org_notes/ --group-by category

# Filter for work and learning memories only
python memories_to_org.py memories.json omi_work.org --category work,learnings
```

## Org-mode Structure & Properties

Each memory is represented as an Org subtree node with an explicit `:PROPERTIES:` drawer:

```org
* 💼 Work :work:
** Specializes in distributed systems and consensus protocols. :distributed_systems:algorithms:raft:
:PROPERTIES:
:OMI_ID: mem_001
:CATEGORY: work
:DATE: [2026-09-28 Mon 09:30]
:CREATED: [2026-09-28 Mon 09:30]
:UPDATED: [2026-09-28 Mon 10:00]
:VISIBILITY: public
:TAGS: distributed_systems algorithms raft
:END:
```

### Key Capabilities

1. **Standard Org Metadata**:
   - `:OMI_ID:` preserves the unique Omi record identifier for retrieval via `omi memory get <id>`.
   - `:CATEGORY:` tags the conceptual domain (`work`, `skills`, `learnings`, `lifestyle`, etc.).
   - `:DATE:` and `:CREATED:` inactive timestamps integrate cleanly with Org agenda searches.
   - `:TAGS:` and headline tags (`:tag1:tag2:`) allow instant filtering with `org-match-sparse-tree` (`C-c \`).

2. **Grouping Options**:
   - `--group-by category` (default): Groups items under level-1 category headings with descriptive emoji icons.
   - `--group-by date`: Groups items under daily level-1 headings (`* 📅 YYYY-MM-DD`).
   - `--group-by none`: Outputs a flat level-1 list of memories.

3. **Envelope Unwrapping & Safety**:
   - Transparently handles bare arrays `[...]`, wrapped dicts `{"memories": [...]}`, `{"items": [...]}`, `{"data": [...]}`, or single memory objects.
   - Accurately identifies empty envelopes (`{"memories": []}`) without creating ghost or phantom records.
   - Protects against syntax collisions by injecting zero-width spaces (`\u200b`) in priority cookies (`[#A]`), stray timestamps, and trailing tag delimiters.
   - Resolves filename collisions deterministically with numeric suffixes when exporting to directory trees.
