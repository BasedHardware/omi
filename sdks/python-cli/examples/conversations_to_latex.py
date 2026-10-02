"""
Convert Omi conversation JSON exports to a self-compiling LaTeX report (.tex).

Usage:
  python conversations_to_latex.py input.json --output out.tex
  omi --json conversation list --include-transcript | python conversations_to_latex.py - out.tex
  python conversations_to_latex.py input.json --output-dir ./reports/   # one standalone document per conversation

stdlib-only. Every field is escaped in a single pass, so titles like
``C++ & Rust: 100%`` cannot break the build.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# The ten LaTeX special characters and their escapes. Built as one pass
# (backslash first, then the rest) so an escape can never feed back into
# another — the classic sequential-replace corruption bug is impossible.
_ESCAPE_PAIRS: List[Tuple[str, str]] = [
    ("\\", r"\textbackslash{}"),
    ("&", r"\&"),
    ("%", r"\%"),
    ("$", r"\$"),
    ("#", r"\#"),
    ("_", r"\_"),
    ("{", r"\{"),
    ("}", r"\}"),
    ("~", r"\textasciitilde{}"),
    ("^", r"\textasciicircum{}"),
]

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


def escape_latex(text: Any) -> str:
    """Escape all ten LaTeX special characters in a single pass."""
    out: List[str] = []
    for ch in str(text):
        for src, repl in _ESCAPE_PAIRS:
            if ch == src:
                out.append(repl)
                break
        else:
            out.append(ch)
    return "".join(out)


def format_timestamp(seconds: Union[float, int, None]) -> str:
    """Format seconds into MM:SS or HH:MM:SS."""
    if seconds is None:
        return "00:00"
    total = int(seconds)
    hours, rem = divmod(max(total, 0), 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def slugify(text: str) -> str:
    """Create a filesystem-safe filename slug."""
    text = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[-\s]+", "_", text)[:50] or "conversation"


def sanitize_component(text: Any) -> str:
    """Filename-safe component: no separators, no traversal, bounded length."""
    text = str(text)
    text = re.sub(r"[^A-Za-z0-9_-]", "", text)[:40]
    return text or "conversation"


def conversation_title(conv: Dict[str, Any]) -> str:
    structured = conv.get("structured")
    if isinstance(structured, dict):
        title = structured.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()
    return "Untitled Conversation"


def utc_date_str(started_at: Any) -> str:
    if not started_at:
        return ""
    try:
        dt = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return str(started_at)


def action_item_text(item: Dict[str, Any]) -> str:
    desc = str(item.get("description") or item.get("title") or "").strip()
    return desc.replace("\r\n", " ").replace("\n", " ")


def conversation_body_lines(conv: Dict[str, Any]) -> List[str]:
    """Render the inner body of one conversation (sections, no preamble)."""
    structured = conv.get("structured")
    if not isinstance(structured, dict):
        structured = {}
    overview = structured.get("overview") or ""
    action_items = structured.get("action_items") or []
    if not isinstance(action_items, list):
        action_items = []

    conv_id = conv.get("id", "unknown")
    started_at = conv.get("started_at") or ""
    source = conv.get("source") or "omi"
    date_str = utc_date_str(started_at) or "N/A"

    lines: List[str] = [
        escape_latex(conversation_title(conv)),
        r"\label{sec:" + sanitize_component(str(conv_id)) + "}",
        "",
        escape_latex(date_str) + r" \quad| source: " + escape_latex(str(source)),
        "",
    ]

    if str(overview).strip():
        lines.extend([r"\subsection*{Summary}", "", escape_latex(overview.strip()), ""])

    if action_items:
        lines.extend([r"\subsection*{Action items}", "", r"\begin{itemize}", ""])
        for item in action_items:
            if isinstance(item, dict):
                desc = action_item_text(item)
                if not desc:
                    desc = "Untitled action item"
                box = r"\checkmark" if is_completed(item.get("completed", False)) else r"$\square$"
                lines.append(r"  \item " + box + " " + escape_latex(desc))
            elif isinstance(item, str) and item.strip():
                lines.append(r"  \item $\square$ " + escape_latex(item.strip()))
        lines.extend(["", r"\end{itemize}", ""])

    segments = conv.get("transcript_segments") or []
    if isinstance(segments, list):
        seg_lines: List[str] = []
        first = True
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            speaker = seg.get("speaker", "Speaker")
            if isinstance(speaker, int):
                speaker_label = f"Speaker {speaker}"
            else:
                speaker_label = str(speaker) if speaker else "Speaker"
            text = str(seg.get("text") or "").strip()
            if not text:
                continue
            if not first:
                seg_lines.append("")
                seg_lines.append(r"\medskip")
                seg_lines.append("")
            stamp = format_timestamp(seg.get("start"))
            seg_lines.append(
                r"\textbf{"
                + escape_latex(speaker_label)
                + r"} \texttt{["
                + escape_latex(stamp)
                + "]}: "
                + escape_latex(text)
            )
            first = False
        if seg_lines:
            lines.extend([r"\subsection*{Transcript}", "", r"\begin{quote}", ""])
            lines.extend(seg_lines)
            lines.extend(["", r"\end{quote}", ""])

    return lines


def document_preamble() -> List[str]:
    return [
        r"\documentclass[11pt]{article}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage[a4paper,margin=2.5cm]{geometry}",
        r"\usepackage{amsmath,amssymb}",
        r"\usepackage{hyperref}",
        "",
        r"\title{Omi Conversations Report}",
        r"\author{omi}",
        "",
        r"\begin{document}",
        r"\maketitle",
        "",
    ]


PREAMBLE_LINES = document_preamble()


def render_master_document(items: List[Dict[str, Any]]) -> str:
    """Render all conversations into one standalone .tex document."""
    lines = list(PREAMBLE_LINES)
    lines.append(r"\tableofcontents")
    lines.append("")
    lines.append(r"\newpage")
    lines.append("")
    rendered = 0
    for conv in items:
        if not isinstance(conv, dict):
            continue
        lines.append(r"\section{" + escape_latex(conversation_title(conv)) + "}")
        lines.extend(conversation_body_lines(conv))
        rendered += 1
    if rendered == 0:
        lines.append(r"\section{No conversations}")
        lines.append("")
        lines.append("The export contained no conversations.")
        lines.append("")
    lines.append(r"\end{document}")
    return "\n".join(lines) + "\n"


def render_single_document(conv: Dict[str, Any], conv_id: Any) -> str:
    lines = list(PREAMBLE_LINES)
    lines.pop(-1)  # drop \maketitle for single documents
    lines.append(r"\section{" + escape_latex(conversation_title(conv)) + "}")
    lines.extend(conversation_body_lines(conv))
    lines.append(r"\end{document}")
    _ = conv_id
    return "\n".join(lines) + "\n"


def safe_output_path(output_dir: Path, name: str, suffix: str) -> Path:
    """Resolve an output path inside output_dir, refusing traversal."""
    resolved_root = output_dir.resolve()
    candidate = (output_dir / name).resolve()
    if not str(candidate).startswith(str(resolved_root)):
        raise SystemExit(f"Error: refusing to write outside {resolved_root}: {name}")
    return candidate


def unique_path(path: Path, overwrite: bool, used: set) -> Path:
    if overwrite:
        return path
    candidate = path
    counter = 1
    while candidate in used or candidate.exists():
        counter += 1
        candidate = path.with_name(f"{path.stem}-{counter}{path.suffix}")
    return candidate


def extract_conversations(data: Any) -> List[Dict[str, Any]]:
    """Unwrap conversation list from bare arrays, envelopes, or single objects."""
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


def export_master(items: List[Dict[str, Any]], output: Path, overwrite: bool) -> Path:
    output = safe_output_path(output.parent, output.name, ".tex")
    path = unique_path(output, overwrite, set())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_master_document(items), encoding="utf-8")
    print(f"Exported: {path}")
    return path


def export_split(items: List[Dict[str, Any]], output_dir: Path, overwrite: bool) -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    used: set = set()
    for count, conv in enumerate(items):
        if not isinstance(conv, dict):
            continue
        conv_id = conv.get("id", f"conv_{count}")
        started_at = conv.get("started_at") or ""
        date_match = re.match(r"^(\d{4}-\d{2}-\d{2})", str(started_at))
        date_prefix = date_match.group(1) if date_match else "undated"
        short_id = sanitize_component(str(conv_id))[:8] or f"{count:03d}"
        base = f"{date_prefix}_{slugify(conversation_title(conv))}_{short_id}"
        path = safe_output_path(output_dir, f"{base}.tex", ".tex")
        path = unique_path(path, overwrite, used)
        used.add(path)
        path.write_text(render_single_document(conv, conv_id), encoding="utf-8")
        print(f"Exported: {path}")
        paths.append(path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert Omi conversation JSON exports to a LaTeX (.tex) report.")
    parser.add_argument("input", help="Path to JSON file (or '-' for stdin).")
    parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="Master output .tex path (same as --output).",
    )
    parser.add_argument("--output", "-o", dest="output_flag", type=Path, default=None, help="Master output .tex path.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to write one standalone .tex per conversation.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=False,
        help="Overwrite existing files on collision (default: exclusive-creation).",
    )
    args = parser.parse_args()

    if args.output is None and args.output_flag is not None:
        args.output = args.output_flag
    if args.output is None and args.output_dir is None:
        args.output = Path("conversations_report.tex")
    if args.output is not None and not isinstance(args.output, Path):
        args.output = Path(args.output)

    if args.input == "-":
        raw_data = sys.stdin.read().lstrip("\ufeff")
    else:
        raw_data = Path(args.input).read_text(encoding="utf-8-sig")

    try:
        data = json.loads(raw_data)
    except json.JSONDecodeError as exc:
        sys.exit(f"Error: invalid JSON: {exc}")
    if not isinstance(data, (list, dict)):
        sys.exit("Error: Expected JSON object or array.")

    items = extract_conversations(data)
    if args.output is not None:
        # Master output wins when both a positional/--output path and --output-dir are given.
        path = export_master(items, args.output, args.overwrite)
        print(f"\nSuccessfully exported {len(items)} conversation(s) to {path}")
    elif args.output_dir is not None:
        paths = export_split(items, args.output_dir, args.overwrite)
        print(f"\nSuccessfully exported {len(paths)} document(s) to {args.output_dir}/")
    else:
        assert args.output is not None
        path = export_master(items, args.output, args.overwrite)
        print(f"\nSuccessfully exported {len(items)} conversation(s) to {path}")


if __name__ == "__main__":
    main()
