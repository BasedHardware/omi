"""Convert Omi conversation JSON exports to Jupyter notebook (.ipynb) files.

See conversations_jupyter.md for the full recipe.

Usage:
    omi --json conversation list --include-transcript > conversations.json
    python conversations_to_jupyter.py conversations.json omi_conversations.ipynb
    omi --json conversation list | python conversations_to_jupyter.py - omi_conversations.ipynb
    python conversations_to_jupyter.py conversations.json "" --output-dir notebooks/
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Union

NBFORMAT = 4
NBFORMAT_MINOR = 4


def one_line(value: Any) -> str:
    """Render one exported field as single-line text.

    The dev API is loosely typed, so a field can arrive as a non-string; anything
    non-null is coerced rather than rejected, so one odd row cannot break the file.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(value.split())


def slugify(text: str) -> str:
    """Create a filesystem-safe filename slug."""
    text = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[-\s]+", "_", text)[:50] or "conversation"


def format_timestamp(seconds: float | int | None) -> str:
    """Format seconds into MM:SS or HH:MM:SS, or None without a usable value."""
    if seconds is None:
        return None
    if isinstance(seconds, str):
        try:
            seconds = float(seconds)
        except ValueError:
            return None
    if not isinstance(seconds, (int, float)):
        return None
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def extract_conversations(data: Any) -> List[Dict[str, Any]]:
    """Unwrap conversation list from bare arrays, wrapped dictionaries, or single objects.

    Supports:
    - Bare arrays: [ {...}, {...} ]
    - Wrapped dicts: {"conversations": [...]}, {"items": [...]}, {"data": [...]}, {"results": [...]}
    - Single conversation dict: { "id": "...", ... }

    Ensures that empty envelopes or invalid dict payloads (such as API error responses
    like {"detail": "..."}) return an empty list instead of falling through and
    creating phantom notebook cells.
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


def conversation_title(conv: Dict[str, Any]) -> str:
    structured = conv.get("structured")
    if isinstance(structured, dict):
        return one_line(structured.get("title")) or "Untitled Conversation"
    return "Untitled Conversation"


def conversation_date_str(conv: Dict[str, Any]) -> str:
    started_at = conv.get("started_at") or ""
    if not started_at:
        return ""
    try:
        dt = datetime.fromisoformat(one_line(started_at).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except ValueError:
        return one_line(started_at)


def transcript_rows(conv: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One loose-typed-safe row per transcript segment: speaker, start, end, text."""
    segments = conv.get("transcript_segments")
    if not isinstance(segments, list):
        return []
    rows = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        speaker = seg.get("speaker")
        if speaker is None or str(speaker).strip() == "":
            speaker = "Speaker"
        elif isinstance(speaker, int):
            speaker = f"Speaker {speaker}"
        text = seg.get("text")
        rows.append(
            {
                "speaker": str(speaker).strip() if isinstance(speaker, str) else speaker,
                "start": format_timestamp(seg.get("start")),
                "end": format_timestamp(seg.get("end")),
                "text": " ".join(str(text).split()) if text is not None else "",
            }
        )
    return rows


def py_literal(value: Any, indent: int = 0) -> str:
    """Render a value as a valid, readable Python literal.

    The transcript cell must be pastable Python, so JSON syntax is not enough:
    ``null``/``true``/``false`` are not Python. Strings stay double-quoted and
    keep non-ASCII characters readable (ensure_ascii=False); nested dicts and
    lists are indented for a Jupyter-friendly layout.
    """
    pad = "  " * indent
    if isinstance(value, dict):
        if not value:
            return "{}"
        inner = ",\n".join(
            f"{pad}  {json.dumps(str(k), ensure_ascii=False)}: {py_literal(v, indent + 1)}" for k, v in value.items()
        )
        return f"{{\n{inner}\n{pad}}}"
    if isinstance(value, (list, tuple)):
        if not value:
            return "[]"
        inner = ",\n".join(f"{pad}  {py_literal(item, indent + 1)}" for item in value)
        return f"[\n{inner}\n{pad}]"
    if value is None:
        return "None"
    if value is True:
        return "True"
    if value is False:
        return "False"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float)):
        return repr(value)
    return json.dumps(value, ensure_ascii=False)


def markdown_cell(text: str) -> Dict[str, Any]:
    lines = text.split("\n")
    source = [line + "\n" for line in lines[:-1]]
    if lines[-1]:
        source.append(lines[-1])
    return {"cell_type": "markdown", "metadata": {}, "source": source}


def code_cell(text: str) -> Dict[str, Any]:
    lines = text.split("\n")
    source = [line + "\n" for line in lines[:-1]]
    if lines[-1]:
        source.append(lines[-1])
    return {"cell_type": "code", "metadata": {}, "source": source, "execution_count": None, "outputs": []}


def conversation_cells(conv: Dict[str, Any], index: int) -> List[Dict[str, Any]]:
    """Notebook cells for one conversation: section header, summary, action items, transcript."""
    conv_id = one_line(conv.get("id")) or f"conversation-{index}"
    title = conversation_title(conv)
    structured = conv.get("structured")
    structured = structured if isinstance(structured, dict) else {}
    overview = one_line(structured.get("overview"))
    action_items = structured.get("action_items")
    if not isinstance(action_items, list):
        action_items = []
    rows = transcript_rows(conv)

    header_lines = [f"## {index}. {title}", "", f"- **ID:** `{conv_id}`"]
    date_str = conversation_date_str(conv)
    if date_str:
        header_lines.append(f"- **Started:** {date_str}")
    source = one_line(conv.get("source"))
    if source:
        header_lines.append(f"- **Source:** `{source}`")
    category = one_line(structured.get("category"))
    if category:
        header_lines.append(f"- **Category:** `{category}`")
    speakers = {str(row["speaker"]) for row in rows if row["speaker"]}
    header_lines.append(
        f"- **Transcript:** {len(rows)} segment(s)" + (f", {len(speakers)} speaker(s)" if speakers else "")
    )
    cells = [markdown_cell("\n".join(header_lines))]

    if overview:
        cells.append(markdown_cell("### Summary\n\n" + overview))

    if action_items:
        lines = ["### Action items", ""]
        for item in action_items:
            if isinstance(item, dict):
                desc = one_line(item.get("description") or item.get("title")) or "Untitled action item"
                done = "x" if item.get("completed") in (True, "true", "yes", 1, "1") else " "
                lines.append(f"- [{done}] {desc}")
            elif isinstance(item, str) and item.strip():
                lines.append(f"- [ ] {item.strip()}")
        if len(lines) > 2:
            cells.append(markdown_cell("\n".join(lines)))

    literal = py_literal(rows)
    code_lines = [f"# Omi conversation {index} ({conv_id})", f"transcript = {literal}"]
    code_lines.append("len(transcript)")
    cells.append(code_cell("\n".join(code_lines)))
    return cells


def build_notebook(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build the nbformat-4 notebook document for a conversation export."""
    header = "\n".join(
        [
            "# Omi conversations",
            "",
            f"{len(items)} conversation(s) exported from `omi --json conversation list`.",
            "",
            "Open this notebook in [Jupyter](https://jupyter.org), JupyterLab, or VS Code. Each section shows the",
            "conversation summary and action items; the `transcript` variable holds the segments as a list of",
            "`{speaker, start, end, text}` dicts you can slice with pandas:",
            "",
            "```python",
            "import pandas as pd",
            "",
            "pd.DataFrame(transcript)",
            "```",
        ]
    )
    cells: List[Dict[str, Any]] = [markdown_cell(header)]
    if not items:
        cells.append(markdown_cell("*No conversations in this export.*"))
    for index, conv in enumerate(items, start=1):
        cells.extend(conversation_cells(conv, index))
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3"},
            "omi": {"source": "omi --json conversation list", "conversation_count": len(items)},
        },
        "nbformat": NBFORMAT,
        "nbformat_minor": NBFORMAT_MINOR,
    }


def notebook_payload(items: List[Dict[str, Any]]) -> bytes:
    return (json.dumps(build_notebook(items), indent=1, ensure_ascii=False) + "\n").encode("utf-8")


def conversation_output_name(conv: Dict[str, Any], index: int, used: set) -> str:
    """Deterministic filename; collisions append -2, -3, ... in export order."""
    started_at = conv.get("started_at") or ""
    date_match = re.match(r"^(\d{4}-\d{2}-\d{2})", one_line(started_at))
    date_prefix = date_match.group(1) if date_match else "undated"
    slug = slugify(conversation_title(conv))
    short_id = re.sub(r"[^\w-]", "", one_line(conv.get("id")))[:8] or f"{index:03d}"
    base = f"{date_prefix}_{slug}_{short_id}"
    name, n = base, 2
    while name in used:
        name = f"{base}-{n}"
        n += 1
    used.add(name)
    return f"{name}.ipynb"


def _read_source(source: str) -> Any:
    text = Path(source).read_bytes().decode("utf-8-sig") if source != "-" else sys.stdin.read()
    return json.loads(text)


def _check_destination(destination: Union[str, Path]) -> None:
    parts = Path(destination).parts
    if ".." in parts:
        raise ValueError(f"Refusing output destination with path traversal: {destination}")


def convert(
    source: str,
    destination: str,
    output_dir: str | None = None,
    overwrite: bool = False,
) -> int:
    raw = _read_source(source)
    items = extract_conversations(raw)
    payload = notebook_payload(items)

    if output_dir:
        out_dir = Path(output_dir)
        _check_destination(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        used: set = set()
        written = 0
        for index, conv in enumerate(items, start=1):
            name = conversation_output_name(conv, index, used)
            path = out_dir / name
            # One notebook per conversation: each file holds only its own section.
            payload = notebook_payload([conv])
            # Exclusive creation protects an existing file; a failed write leaves no partial file.
            try:
                with path.open("xb") as handle:
                    handle.write(payload)
            except FileExistsError:
                raise
            except OSError:
                path.unlink(missing_ok=True)
                raise
            written += 1
        return written

    output_path = Path(destination)
    _check_destination(output_path)
    if overwrite:
        tmp = output_path.with_suffix(output_path.suffix + ".tmp")
        tmp.write_bytes(payload)
        tmp.replace(output_path)
        return len(items)
    # Exclusive creation protects an existing file; a failed write leaves no partial file.
    try:
        with output_path.open("xb") as handle:
            handle.write(payload)
    except FileExistsError:
        raise FileExistsError(
            f"Refusing to overwrite existing {output_path} (pass --overwrite to replace it)"
        ) from None
    except OSError:
        output_path.unlink(missing_ok=True)
        raise
    return len(items)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert an omi conversation export to Jupyter notebook (.ipynb) files."
    )
    parser.add_argument("source", help="JSON from omi --json conversation list, or '-' for stdin")
    parser.add_argument(
        "destination",
        nargs="?",
        default="omi_conversations.ipynb",
        help="new .ipynb file to create (omit or '' when using --output-dir)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="write one .ipynb file per conversation into this directory instead of one master notebook",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace the destination notebook if it already exists (default: refuse)",
    )
    args = parser.parse_args()
    if bool(args.output_dir) == bool(args.destination.strip()):
        parser.error("provide exactly one of destination or --output-dir")
    try:
        written = convert(args.source, args.destination, output_dir=args.output_dir, overwrite=args.overwrite)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        sys.exit(f"Jupyter export failed: {exc}")
    if args.output_dir:
        print(f"{written} notebook(s) written to {args.output_dir}")
    else:
        print(f"{written} conversation(s) written to {args.destination}")
