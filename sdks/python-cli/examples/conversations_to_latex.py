"""Convert Omi conversation JSON exports to LaTeX report (.tex) files.

See conversations_latex.md for the full recipe.

Usage:
    omi --json conversation list --include-transcript > conversations.json
    python conversations_to_latex.py conversations.json omi_conversations.tex
    omi --json conversation list | python conversations_to_latex.py - omi_conversations.tex
    python conversations_to_latex.py conversations.json "" --output-dir reports/
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Union

# The ten characters that are special in the LaTeX body text and the source
# snippet we emit. Replacements are applied in a single pass over the *original*
# characters, so any character an escape introduces (for example the braces in
# \textbackslash{}) is never re-processed. That single-pass rule is what keeps
# the escaper from corrupting its own output.
_LATEX_SPECIALS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


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


def escape_latex(value: Any) -> str:
    """Return a LaTeX-safe, single-line rendering of an exported field.

    Whitespace is collapsed to single spaces and every one of the ten special
    characters is escaped. The escape table is applied in one pass over the
    original characters, so escapes never feed back into each other.
    """
    text = one_line(value)
    return "".join(_LATEX_SPECIALS.get(ch, ch) for ch in text)


def slugify(text: str) -> str:
    """Create a filesystem-safe filename slug."""
    text = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[-\s]+", "_", text)[:50] or "conversation"


def format_timestamp(seconds: float | int | None) -> str | None:
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
    if not math.isfinite(seconds) or seconds < 0:
        return None
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def is_completed(value: Any) -> bool:
    """Normalize a loosely-typed completion flag to a boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "done", "completed"}
    return False


def extract_conversations(data: Any) -> List[Dict[str, Any]]:
    """Unwrap conversation list from bare arrays, wrapped dictionaries, or single objects.

    Supports:
    - Bare arrays: [ {...}, {...} ]
    - Wrapped dicts: {"conversations": [...]}, {"items": [...]}, {"data": [...]}, {"results": [...]}
    - Single conversation dict: { "id": "...", ... }

    Ensures that empty envelopes or invalid dict payloads (such as API error
    responses like {"detail": "..."}) return an empty list instead of falling
    through and creating phantom sections.
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
                "speaker": escape_latex(speaker),
                "start": format_timestamp(seg.get("start")),
                "end": format_timestamp(seg.get("end")),
                "text": escape_latex(" ".join(str(text).split()) if text is not None else ""),
            }
        )
    return rows


def _metadata_items(conv: Dict[str, Any], index: int, rows: List[Dict[str, Any]]) -> List[str]:
    """The description-environment items describing one conversation header."""
    conv_id = one_line(conv.get("id")) or f"conversation-{index}"
    lines = [r"\item[ID] \texttt{" + escape_latex(conv_id) + "}"]
    date_str = conversation_date_str(conv)
    if date_str:
        lines.append(r"\item[Started] " + escape_latex(date_str))
    source = one_line(conv.get("source"))
    if source:
        lines.append(r"\item[Source] \texttt{" + escape_latex(source) + "}")
    structured = conv.get("structured")
    structured = structured if isinstance(structured, dict) else {}
    category = one_line(structured.get("category"))
    if category:
        lines.append(r"\item[Category] \texttt{" + escape_latex(category) + "}")
    speakers = {row["speaker"] for row in rows if row["speaker"]}
    transcript_note = str(len(rows)) + " segment(s)" + (f", {len(speakers)} speaker(s)" if speakers else "")
    lines.append(r"\item[Transcript] " + escape_latex(transcript_note))
    return lines


def _action_item_lines(conv: Dict[str, Any]) -> List[str]:
    r"""Render action items as itemize lines using \checkmark / \square bullets."""
    structured = conv.get("structured")
    structured = structured if isinstance(structured, dict) else {}
    items = structured.get("action_items")
    if not isinstance(items, list):
        return []
    lines = []
    for item in items:
        if isinstance(item, dict):
            desc = one_line(item.get("description") or item.get("title")) or "Untitled action item"
            bullet = r"\checkmark" if is_completed(item.get("completed")) else r"\square"
            lines.append(r"\item " + bullet + r"{} " + escape_latex(desc))
        elif isinstance(item, str) and item.strip():
            lines.append(r"\item " + r"\square{} " + escape_latex(item.strip()))
    return lines


def conversation_block(conv: Dict[str, Any], index: int) -> str:
    """LaTeX for one conversation: a section plus summary, action items, transcript."""
    title = conversation_title(conv)
    rows = transcript_rows(conv)
    lines: List[str] = []
    lines.append(f"\\section{{{index}. {escape_latex(title)}}}")
    lines.append(r"\begin{description}")
    lines.extend(_metadata_items(conv, index, rows))
    lines.append(r"\end{description}")
    lines.append("")

    structured = conv.get("structured")
    structured = structured if isinstance(structured, dict) else {}
    overview = one_line(structured.get("overview"))
    if overview:
        lines.append("\\subsection{Summary}")
        lines.append(escape_latex(overview))
        lines.append("")

    action_lines = _action_item_lines(conv)
    if action_lines:
        lines.append("\\subsection{Action items}")
        lines.append(r"\begin{itemize}")
        lines.extend(action_lines)
        lines.append(r"\end{itemize}")
        lines.append("")

    if rows:
        lines.append("\\subsection{Transcript}")
        lines.append(r"\begin{quote}")
        for row in rows:
            stamp = row["start"] or "00:00"
            lines.append("\\textbf{" + row["speaker"] + "} \\texttt{[" + stamp + "]}" + ": " + row["text"] + "\\par")
        # Replace the trailing \par on the final line so the quote closes cleanly.
        lines[-1] = lines[-1][: -len("\\par")]
        lines.append(r"\end{quote}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_document(items: List[Dict[str, Any]]) -> str:
    """Build the full standalone LaTeX source for a conversation export."""
    head = [
        r"\documentclass[11pt]{article}",
        r"\usepackage{iftex}",
        r"\ifPDFTeX",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\else",
        r"\usepackage{fontspec}",
        r"\fi",
        r"\usepackage[margin=1in]{geometry}",
        r"\usepackage{amsmath,amssymb}",
        r"\usepackage{hyperref}",
        r"\pagestyle{plain}",
        r"",
        r"\title{Omi Conversations}",
        r"\author{}",
        r"\date{" + str(len(items)) + " conversation(s) exported from \\texttt{omi --json conversation list}}",
        r"",
        r"\begin{document}",
        r"\maketitle",
        r"",
    ]
    body: List[str]
    if not items:
        body = ["\\noindent\\textit{No conversations in this export.}", ""]
    else:
        body = []
        for index, conv in enumerate(items, start=1):
            body.append(conversation_block(conv, index))
    tail = [r"\end{document}"]
    return "\n".join(head + body + tail).rstrip() + "\n"


def latex_payload(items: List[Dict[str, Any]]) -> bytes:
    """Deterministic UTF-8 bytes for a standalone LaTeX document of the export."""
    return build_document(items).encode("utf-8")


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
    return f"{name}.tex"


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
    payload = latex_payload(items)

    if output_dir:
        out_dir = Path(output_dir)
        _check_destination(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        used: set = set()
        written = 0
        for index, conv in enumerate(items, start=1):
            name = conversation_output_name(conv, index, used)
            path = out_dir / name
            # One standalone document per conversation: each file holds only its own section.
            split_payload = latex_payload([conv])
            # Exclusive creation protects an existing file; a failed write leaves no partial file.
            try:
                with path.open("xb") as handle:
                    handle.write(split_payload)
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
        tmp: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=output_path.parent,
                prefix=f".{output_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                tmp = Path(handle.name)
                handle.write(payload)
            tmp.replace(output_path)
        except OSError:
            if tmp is not None:
                tmp.unlink(missing_ok=True)
            raise
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
    parser = argparse.ArgumentParser(description="Convert an omi conversation export to LaTeX report (.tex) files.")
    parser.add_argument("source", help="JSON from omi --json conversation list, or '-' for stdin")
    parser.add_argument(
        "destination",
        nargs="?",
        default="omi_conversations.tex",
        help="new .tex file to create (omit or '' when using --output-dir)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="write one standalone .tex document per conversation into this directory instead of one master report",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace the destination document if it already exists (default: refuse)",
    )
    args = parser.parse_args()
    if bool(args.output_dir) == bool(args.destination.strip()):
        parser.error("provide exactly one of destination or --output-dir")
    try:
        written = convert(args.source, args.destination, output_dir=args.output_dir, overwrite=args.overwrite)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        sys.exit(f"LaTeX export failed: {exc}")
    if args.output_dir:
        print(f"{written} LaTeX document(s) written to {args.output_dir}")
    else:
        print(f"{written} conversation(s) written to {args.destination}")
