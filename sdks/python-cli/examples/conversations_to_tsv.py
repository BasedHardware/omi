#!/usr/bin/env python3
"""Convert Omi conversation JSON exports into Tab-Separated Values (TSV) format.

Optimized for command-line text processing (`grep`, `awk`, `cut`, `sed`).
Multi-line summaries and transcripts have newlines and tabs escaped safely to
guarantee strictly 1 line per record.

Features:
- Zero external dependencies: Python standard library only.
- Unwraps bare JSON arrays or envelope objects (`conversations`, `items`, `data`, `results`).
- Supports reading from files or standard input (`-`).
- Supports writing to files or standard output (`-`).
- Path traversal guard refusing '..' in destination paths.
- Exclusive creation by default to avoid accidental overwrites, with `-f` / `--force` to override.
"""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Core schema contract for exported TSV columns
FIELDS: Tuple[str, ...] = (
    "id",
    "started_at",
    "title",
    "category",
    "source",
    "overview",
    "transcript",
)


def escape_tsv_field(value: Any) -> str:
    """Safely escape field value into plain text conforming to the TSV single-line constraint.

    Rules:
    1. None returns an empty string;
    2. Non-string objects are JSON-encoded or converted to strings;
    3. Newlines (\\r\\n, \\r, \\n) are normalized and escaped to literal '\\n';
    4. Tabs (\\t) are escaped to literal '\\t';
    5. Neutralizes control characters to preserve single-line TSV record integrity.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        if isinstance(value, (dict, list)):
            text = json.dumps(value, ensure_ascii=False)
        else:
            text = str(value)
    else:
        text = value

    # Normalize CRLF and tabs to guarantee single-line record format
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", "\\t")
    text = text.replace("\n", "\\n")
    return text


def extract_transcript(item: Dict[str, Any]) -> str:
    """Extract transcript text from conversation item, handling top-level strings or segments arrays."""
    transcript_val = item.get("transcript")
    if isinstance(transcript_val, str) and transcript_val.strip():
        return transcript_val

    # Support segment/transcripts arrays
    segments = item.get("segments") or item.get("transcripts")
    if isinstance(segments, list):
        parts: List[str] = []
        for seg in segments:
            if isinstance(seg, dict):
                speaker = seg.get("speaker") or seg.get("speaker_label")
                text = seg.get("text") or seg.get("content") or ""
                if text:
                    if speaker:
                        parts.append(f"{speaker}: {text}")
                    else:
                        parts.append(str(text))
            elif isinstance(seg, str) and seg.strip():
                parts.append(seg.strip())
        if parts:
            return " ".join(parts)

    return ""


def unwrap_conversations(data: Any, source_name: str = "input") -> List[Dict[str, Any]]:
    """Unwrap and validate JSON data, supporting bare lists or enveloped dictionaries."""
    if isinstance(data, dict):
        for envelope_key in ("conversations", "items", "data", "results"):
            candidate = data.get(envelope_key)
            if isinstance(candidate, list):
                data = candidate
                break

    if not isinstance(data, list):
        raise ValueError(
            f"{source_name}: expected a JSON array or envelope object containing 'conversations', 'items', 'data', or 'results'"
        )

    conversations: List[Dict[str, Any]] = []
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"{source_name}: conversation at index {idx} must be a JSON object, got {type(item).__name__}")
        conversations.append(item)

    return conversations


def validate_destination_path(destination: str, force: bool = False) -> Path:
    """Validate destination path safety, defending against path traversal and accidental overwrite."""
    path = Path(destination)
    if ".." in path.parts:
        raise ValueError(f"Output path {destination!r} contains '..'; refusing to write outside intended directory.")

    if path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite existing file: {destination}. Use -f/--force to overwrite.")

    return path


def conversations_to_tsv_string(conversations: Iterable[Dict[str, Any]]) -> str:
    """Format an iterable of conversation dicts into a strict single-line TSV string."""
    output = io.StringIO()
    # Write TSV header row
    output.write("\t".join(FIELDS) + "\n")

    for item in conversations:
        structured = item.get("structured")
        if not isinstance(structured, dict):
            structured = {}

        conv_id = item.get("id") or ""
        started_at = item.get("started_at") or item.get("created_at") or ""
        title = structured.get("title") or item.get("title") or ""
        category = structured.get("category") or item.get("category") or ""
        source = item.get("source") or ""
        overview = structured.get("overview") or item.get("overview") or ""
        transcript = extract_transcript(item)

        row_values = [
            escape_tsv_field(conv_id),
            escape_tsv_field(started_at),
            escape_tsv_field(title),
            escape_tsv_field(category),
            escape_tsv_field(source),
            escape_tsv_field(overview),
            escape_tsv_field(transcript),
        ]
        output.write("\t".join(row_values) + "\n")

    return output.getvalue()


def convert(source: str, destination: Optional[str] = None, force: bool = False) -> str:
    """Execute TSV conversion pipeline.

    If destination is None or '-', returns the TSV string directly for streaming stdout.
    """
    # 1. Read input data
    if source == "-":
        raw_text = sys.stdin.read()
        source_name = "<stdin>"
    else:
        source_path = Path(source)
        if not source_path.is_file():
            raise FileNotFoundError(f"Input file not found: {source}")
        raw_text = source_path.read_text(encoding="utf-8").lstrip("\ufeff")
        source_name = str(source_path)

    # 2. Parse JSON
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON in {source_name}: {exc}") from exc

    # 3. Unwrap conversations array
    conversations = unwrap_conversations(data, source_name=source_name)

    # 4. Generate TSV representation
    tsv_content = conversations_to_tsv_string(conversations)

    # 5. Output handling
    if destination is None or destination == "-":
        return tsv_content

    dest_path = validate_destination_path(destination, force=force)
    # Create parent directories if needed
    if dest_path.parent and not dest_path.parent.exists():
        dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Write output file
    dest_path.write_text(tsv_content, encoding="utf-8")
    return tsv_content


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Convert Omi conversation JSON exports into Tab-Separated Values (TSV) format."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="-",
        help="Input JSON file or '-' for stdin (default: '-')",
    )
    parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="Output TSV file or '-' for stdout (default: stdout if omitted)",
    )
    parser.add_argument(
        "-o",
        "--output-file",
        dest="opt_output",
        help="Alternative flag to specify output TSV file",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing output file without confirmation",
    )

    args = parser.parse_args(argv)
    dest = args.opt_output or args.output

    try:
        result = convert(source=args.input, destination=dest, force=args.force)
        if dest is None or dest == "-":
            sys.stdout.write(result)
            sys.stdout.flush()
        return 0
    except Exception as exc:
        sys.stderr.write(f"TSV export failed: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
