"""
Convert Omi conversation JSON exports to Jupyter notebooks (.ipynb) for data analysis with pandas.

Usage:
  # Export all conversations into a single combined notebook:
  python conversations_to_jupyter.py conversations.json -o analysis.ipynb

  # Export one notebook per conversation:
  python conversations_to_jupyter.py conversations.json --output-dir ./notebooks/

  # Pipe directly from omi CLI:
  omi --json conversation list --include-transcript | python conversations_to_jupyter.py - -o out.ipynb
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Union


DONE_WORDS = {"true", "yes", "1", "done", "completed"}


def is_completed(value: Any) -> bool:
    """Normalize completed status for loosely typed API / LLM exports."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in DONE_WORDS
    return False


def format_timestamp(seconds: float | int | None) -> str:
    """Format seconds into MM:SS or HH:MM:SS format."""
    if seconds is None:
        return "00:00"
    try:
        total_seconds = int(seconds)
    except (ValueError, TypeError):
        return "00:00"
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


def extract_conversations(data: Any) -> List[Dict[str, Any]]:
    """Unwrap conversation list from bare arrays, wrapped dictionaries, or single objects.

    Supports:
    - Bare arrays: [ {...}, {...} ]
    - Wrapped dicts: {"conversations": [...]}, {"items": [...]}, {"data": [...]}, {"results": [...]}
    - Single conversation dict: { "id": "...", ... }
    """
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("conversations", "items", "data", "results"):
            val = data.get(key)
            if isinstance(val, list):
                return [item for item in val if isinstance(item, dict)]
        if any(key in data for key in ("id", "transcript_segments", "structured", "started_at", "created_at")):
            return [data]
        return []
    return []


def create_markdown_cell(source: Union[str, List[str]]) -> Dict[str, Any]:
    """Create an nbformat-4 markdown cell."""
    if isinstance(source, str):
        lines = [line + "\n" for line in source.split("\n")]
        if lines and lines[-1] == "\n":
            lines[-1] = ""
        source_lines = lines
    else:
        source_lines = source

    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": source_lines,
    }


def create_code_cell(source: Union[str, List[str]]) -> Dict[str, Any]:
    """Create an nbformat-4 code cell."""
    if isinstance(source, str):
        lines = [line + "\n" for line in source.split("\n")]
        if lines and lines[-1] == "\n":
            lines[-1] = ""
        source_lines = lines
    else:
        source_lines = source

    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source_lines,
    }


def conversation_to_notebook_cells(conv: Dict[str, Any], include_header: bool = True) -> List[Dict[str, Any]]:
    """Convert a single Omi conversation dictionary into nbformat cells."""
    cells: List[Dict[str, Any]] = []

    conv_id = conv.get("id", "unknown")
    started_at = conv.get("started_at") or ""
    source = conv.get("source") or "omi"

    structured = conv.get("structured") or {}
    if not isinstance(structured, dict):
        structured = {}

    title = structured.get("title") or "Untitled Conversation"
    category = structured.get("category") or "general"
    overview = structured.get("overview") or ""
    action_items = structured.get("action_items") or []
    transcript_segments = conv.get("transcript_segments") or []

    date_str = ""
    if started_at:
        try:
            dt = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            date_str = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except Exception:
            date_str = str(started_at)

    # 1. Conversation Header & Overview
    md_lines = [
        f"## {title}\n",
        f"- **ID:** `{conv_id}`\n",
        f"- **Date:** {date_str or 'N/A'}\n",
        f"- **Category:** `{category}`\n",
        f"- **Source:** `{source}`\n",
    ]

    if overview:
        md_lines.extend([
            "\n",
            "### Summary\n",
            f"{overview.strip()}\n",
        ])

    if action_items and isinstance(action_items, list):
        md_lines.extend([
            "\n",
            "### Action items\n",
        ])
        for item in action_items:
            if isinstance(item, dict):
                desc = str(item.get("description") or item.get("title") or "").strip().replace("\r\n", " ").replace("\n", " ")
                if not desc:
                    desc = "Untitled action item"
                completed = is_completed(item.get("completed", False))
                box = "[x]" if completed else "[ ]"
                md_lines.append(f"- {box} {desc}\n")
            elif isinstance(item, str) and item.strip():
                md_lines.append(f"- [ ] {item.strip()}\n")

    cells.append(create_markdown_cell(md_lines))

    # 2. Transcript Code Cell (Data analysis ready for pandas)
    normalized_transcript: List[Dict[str, Any]] = []
    for seg in transcript_segments:
        if not isinstance(seg, dict):
            continue
        speaker = seg.get("speaker", "Speaker")
        speaker_label = f"Speaker {speaker}" if isinstance(speaker, int) else (str(speaker) if speaker else "Speaker")
        start = seg.get("start", 0.0)
        end = seg.get("end", 0.0)
        text = str(seg.get("text") or "").strip()
        normalized_transcript.append({
            "speaker": speaker_label,
            "start": start,
            "end": end,
            "text": text,
        })

    transcript_json = json.dumps(normalized_transcript, ensure_ascii=False, indent=2)
    code_lines = [
        "# Transcript data for analysis (e.g. import pandas as pd; df = pd.DataFrame(transcript))\n",
        f"transcript = {transcript_json}\n",
        "len(transcript)\n",
    ]
    cells.append(create_code_cell(code_lines))

    return cells


def build_notebook(cells: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Wrap cells into a valid nbformat v4 notebook structure."""
    return {
        "cells": cells,
        "metadata": {
            "language_info": {
                "name": "python",
                "version": "3",
            }
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def export_notebooks(
    items: List[Dict[str, Any]],
    output_dir: Path,
    overwrite: bool = False,
) -> List[Path]:
    """Export each conversation into its own .ipynb file in output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    exported_paths: List[Path] = []
    used_paths: set[Path] = set()

    for count, conv in enumerate(items):
        if not isinstance(conv, dict):
            continue
        conv_id = conv.get("id", f"conv_{count}")
        started_at = conv.get("started_at") or ""

        date_match = re.match(r"^(\d{4}-\d{2}-\d{2})", str(started_at))
        date_prefix = date_match.group(1) if date_match else "undated"

        structured = conv.get("structured") or {}
        title = structured.get("title") if isinstance(structured, dict) else ""
        slug = slugify(title or "conversation")
        short_id = re.sub(r"[^\w-]", "", str(conv_id))[:8] or f"{count:03d}"

        base_name = f"{date_prefix}_{slug}_{short_id}"
        filepath = output_dir / f"{base_name}.ipynb"

        if not overwrite:
            counter = 1
            while filepath in used_paths or filepath.exists():
                counter += 1
                filepath = output_dir / f"{base_name}_{counter}.ipynb"

        used_paths.add(filepath)

        cells = [
            create_markdown_cell(f"# Omi Conversation: {title or 'Untitled'}\n\nExported on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}."),
        ]
        cells.extend(conversation_to_notebook_cells(conv))
        nb = build_notebook(cells)

        filepath.write_text(json.dumps(nb, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Exported: {filepath}")
        exported_paths.append(filepath)

    return exported_paths


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi conversation JSON exports to Jupyter notebook (.ipynb) files."
    )
    parser.add_argument(
        "input",
        help="Path to JSON file (or '-' for stdin).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Path to output a single combined .ipynb notebook.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to write one .ipynb notebook per conversation.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=False,
        help="Overwrite existing .ipynb files if filenames collide (default: False).",
    )
    args = parser.parse_args()

    # Read input with UTF-8 BOM protection
    if args.input == "-":
        raw_data = sys.stdin.read().lstrip("\ufeff")
    else:
        raw_data = Path(args.input).read_text(encoding="utf-8-sig")

    try:
        data = json.loads(raw_data)
    except Exception as exc:
        sys.exit(f"Error: Invalid JSON input: {exc}")

    if not isinstance(data, (list, dict)):
        sys.exit("Error: Expected JSON object or array.")

    items = extract_conversations(data)
    if not items:
        print("No conversations found in input.")
        return

    if args.output_dir:
        exported = export_notebooks(items, output_dir=args.output_dir, overwrite=args.overwrite)
        print(f"\nSuccessfully exported {len(exported)} notebook(s) to {args.output_dir}/")
    else:
        out_file = args.output or Path("conversations.ipynb")
        if out_file.exists() and not args.overwrite:
            sys.exit(f"Error: Output file {out_file} already exists. Pass --overwrite to replace it.")

        all_cells = [
            create_markdown_cell(f"# Omi Conversations Analysis\n\nExported {len(items)} conversation(s) on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}."),
        ]
        for conv in items:
            all_cells.extend(conversation_to_notebook_cells(conv))

        nb = build_notebook(all_cells)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(nb, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Exported combined notebook with {len(items)} conversation(s) to {out_file}")


if __name__ == "__main__":
    main()
