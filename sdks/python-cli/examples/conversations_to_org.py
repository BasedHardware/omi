"""Convert Omi conversation JSON exports to Emacs Org-mode outline notes.

See conversations_org.md for the full recipe.

Usage:
    omi --json conversation list --include-transcript > conversations.json
    python conversations_to_org.py conversations.json omi_conversations.org --utc-offset +09:00
    python conversations_to_org.py conversations.json --output-dir ./org_notes/
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
DONE_WORDS = {"true", "yes", "1", "done", "completed"}
ZWSP = "​"  # zero-width space, Org's documented escape character


def one_line(value: Any) -> str:
    """Render one exported field as single-line text.

    Coerces non-strings safely without raising errors for unexpected field types.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(value.split())


def heading_text(value: Any) -> str:
    """Keep a description or title from being parsed as Org syntax inside a heading."""
    text = one_line(value) or "(Untitled Conversation)"
    if text.startswith("[#"):
        text = ZWSP + text  # would otherwise become a priority cookie
    text = re.sub(r"([<\[])(?=\d{4}-\d{2}-\d{2})", "\\1" + ZWSP, text)  # prevent stray agenda timestamps
    if re.search(r":[\w@#%:]+:\s*$", text):
        text = text.rstrip() + ZWSP  # prevent stray heading tags
    return text


def is_completed(value: Any) -> bool:
    """Normalize completion state handling booleans, numbers, and loose string representations."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in DONE_WORDS
    return False


def format_timestamp(seconds: Union[float, int, None]) -> str:
    """Format seconds into MM:SS or HH:MM:SS string."""
    if seconds is None:
        return "00:00"
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def slugify(text: str) -> str:
    """Create a filesystem-safe filename slug."""
    text = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[-\s]+", "_", text)[:50] or "conversation"


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


def extract_conversations(data: Any) -> List[Dict[str, Any]]:
    """Unwrap conversation records from bare lists or wrapped dictionary envelopes."""
    if isinstance(data, list):
        return [c for c in data if isinstance(c, dict)]
    if isinstance(data, dict):
        # Match documented wrapper precedence: conversations, items, data
        for key in ("conversations", "items", "data"):
            val = data.get(key)
            if isinstance(val, list):
                return [c for c in val if isinstance(c, dict)]
        # Single conversation payload
        if "id" in data or "structured" in data or "transcript_segments" in data:
            return [data]
        return []
    return []


def conversation_to_org_entry(conv: Dict[str, Any], zone: timezone, level: int = 1) -> str:
    """Format a single conversation as an Org-mode subtree at the given heading level."""
    conv_id = conv.get("id", "unknown")
    started_at = conv.get("started_at") or ""
    created_at = conv.get("created_at") or ""
    source = conv.get("source") or "omi"

    structured = conv.get("structured") or {}
    if not isinstance(structured, dict):
        structured = {}

    title = structured.get("title") or "Untitled Conversation"
    category = structured.get("category") or "general"
    overview = structured.get("overview") or ""
    action_items = structured.get("action_items") or []
    transcript_segments = conv.get("transcript_segments") or []

    prefix = "*" * level
    sub_prefix = "*" * (level + 1)

    lines: List[str] = [f"{prefix} {heading_text(title)}"]

    # Properties Drawer
    lines.append(":PROPERTIES:")
    lines.append(f":OMI_ID: {one_line(conv_id)}")
    started_dt = local_time(started_at, zone)
    if started_dt:
        lines.append(f":DATE: {org_stamp(started_dt, active=False)}")
    if category:
        lines.append(f":CATEGORY: {one_line(category)}")
    if source:
        lines.append(f":SOURCE: {one_line(source)}")
    created_dt = local_time(created_at, zone)
    if created_dt:
        lines.append(f":CREATED: {org_stamp(created_dt, active=False)}")
    lines.append(":END:")

    # Summary Section
    if overview and str(overview).strip():
        lines.append(f"{sub_prefix} Summary")
        lines.append(str(overview).strip())

    # Action Items Checklist Section
    if action_items and isinstance(action_items, list):
        action_lines = []
        for item in action_items:
            if isinstance(item, dict):
                desc = str(item.get("description") or item.get("title") or "").strip().replace("\r\n", " ").replace("\n", " ")
                if not desc:
                    desc = "(Untitled action item)"
                completed = is_completed(item.get("completed", False))
                box = "[X]" if completed else "[ ]"
                action_lines.append(f"- {box} {desc}")
            elif isinstance(item, str) and item.strip():
                action_lines.append(f"- [ ] {item.strip()}")
        if action_lines:
            lines.append(f"{sub_prefix} Action Items")
            lines.extend(action_lines)

    # Transcript Section
    if transcript_segments and isinstance(transcript_segments, list):
        transcript_lines = []
        for seg in transcript_segments:
            if not isinstance(seg, dict):
                continue
            speaker = seg.get("speaker", "Speaker")
            if isinstance(speaker, int):
                speaker_label = f"Speaker {speaker}"
            else:
                speaker_label = str(speaker) if speaker else "Speaker"

            start_time = format_timestamp(seg.get("start"))
            text = (seg.get("text") or "").strip()
            if text:
                transcript_lines.append(f"- [{start_time}] *{speaker_label}:* {text}")
        if transcript_lines:
            lines.append(f"{sub_prefix} Transcript")
            lines.extend(transcript_lines)

    return "\n".join(lines)


def export_single_file(conversations: List[Dict[str, Any]], destination: Path, zone: timezone, overwrite: bool = False) -> int:
    """Export all conversations into one consolidated Org-mode master file."""
    lines = [
        "# -*- mode: org; coding: utf-8 -*-",
        "#+TITLE: Omi Conversations",
        "#+AUTHOR: Omi",
        "",
    ]
    for conv in conversations:
        entry = conversation_to_org_entry(conv, zone, level=1)
        lines.append(entry)
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

    return len(conversations)


def export_directory(conversations: List[Dict[str, Any]], output_dir: Path, zone: timezone, overwrite: bool = False) -> List[Path]:
    """Export conversations into individual .org files in output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    exported: List[Path] = []
    used_paths: set[Path] = set()

    for count, conv in enumerate(conversations):
        conv_id = conv.get("id", f"conv_{count}")
        started_at = conv.get("started_at") or ""
        date_match = re.match(r"^(\d{4}-\d{2}-\d{2})", str(started_at))
        date_prefix = date_match.group(1) if date_match else "undated"

        structured = conv.get("structured") or {}
        title = structured.get("title") if isinstance(structured, dict) else ""
        slug = slugify(title or "conversation")
        short_id = re.sub(r"[^\w-]", "", str(conv_id))[:8] or f"{count:03d}"

        filepath = output_dir / f"{date_prefix}_{slug}_{short_id}.org"
        if not overwrite:
            counter = 1
            while filepath in used_paths or filepath.exists():
                counter += 1
                filepath = output_dir / f"{date_prefix}_{slug}_{short_id}_{counter}.org"
        used_paths.add(filepath)

        header = [
            "# -*- mode: org; coding: utf-8 -*-",
            f"#+TITLE: {heading_text(title or 'Untitled Conversation')}",
            "",
        ]
        body = conversation_to_org_entry(conv, zone, level=1)
        payload = ("\n".join(header) + body + "\n").encode("utf-8")
        filepath.write_bytes(payload)
        exported.append(filepath)

    return exported


def convert(source: Union[str, Path], destination: Union[str, Path], zone: timezone, output_dir: Optional[Union[str, Path]] = None, overwrite: bool = False) -> int:
    """High-level conversion entrypoint."""
    source_path = Path(source)
    raw_content = source_path.read_bytes().decode("utf-8-sig")
    raw_json = json.loads(raw_content)

    items = extract_conversations(raw_json)

    if output_dir:
        dest_dir = Path(output_dir)
        exported = export_directory(items, dest_dir, zone, overwrite=overwrite)
        return len(exported)

    dest_path = Path(destination)
    if dest_path.is_dir() or str(destination).endswith(("/", "\\")):
        exported = export_directory(items, dest_path, zone, overwrite=overwrite)
        return len(exported)

    return export_single_file(items, dest_path, zone, overwrite=overwrite)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert an Omi conversation export to Emacs Org-mode notes.")
    parser.add_argument("source", help="JSON from omi --json conversation list --include-transcript")
    parser.add_argument("destination", nargs="?", default="omi_conversations.org",
                        help="new .org file to create, or directory (default: omi_conversations.org)")
    parser.add_argument("--output-dir", help="export individual .org files into this directory")
    parser.add_argument("--utc-offset", type=parse_offset, default=None,
                        help="format times at this offset (e.g. +09:00); default: computer's local time zone")
    parser.add_argument("--force", action="store_true", help="overwrite existing file(s)")
    args = parser.parse_args()

    zone = args.utc_offset or datetime.now().astimezone().tzinfo
    try:
        count = convert(args.source, args.destination, zone, output_dir=args.output_dir, overwrite=args.force)
        print(f"Successfully exported {count} conversation(s) to Org-mode.")
    except (OSError, ValueError) as exc:
        sys.exit(f"Org export failed: {exc}")
