#!/usr/bin/env python3
"""
conversations_to_jsonl.py

A small utility that converts a plain‑text conversation transcript into a
JSONL file suitable for LLM fine‑tuning or Retrieval‑Augmented Generation (RAG).

Expected input format (one utterance per line):
    USER: Hello, how are you?
    ASSISTANT: I'm fine, thanks! How can I help you today?
    ...

Each line is split on the first ':' character; the part before the colon is
treated as the speaker role (case‑insensitive) and the remainder as the content.

The output JSONL contains one JSON object per line:
    {"role": "user", "content": "Hello, how are you?"}
    {"role": "assistant", "content": "I'm fine, thanks! How can I help you today?"}
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Iterable, Tuple


def _parse_line(line: str, line_no: int) -> Tuple[str, str]:
    """
    Parse a single transcript line into a (role, content) tuple.

    Args:
        line: The raw line from the transcript file.
        line_no: The line number (used for error messages).

    Returns:
        A tuple of (role, content).

    Raises:
        ValueError: If the line does not contain a ':' separator or is otherwise malformed.
    """
    if ':' not in line:
        raise ValueError(f"Line {line_no}: missing ':' separator.")
    role, content = line.split(':', 1)
    role = role.strip().lower()
    content = content.strip()
    if not role:
        raise ValueError(f"Line {line_no}: empty role before ':'")
    if not content:
        raise ValueError(f"Line {line_no}: empty content after ':'")
    return role, content


def _read_transcript(path: Path) -> Iterable[Tuple[str, str]]:
    """
    Yield parsed (role, content) tuples from a transcript file.

    Args:
        path: Path to the transcript file.

    Yields:
        Tuples of (role, content) for each valid line.

    Raises:
        IOError: If the file cannot be opened.
        ValueError: If any line is malformed.
    """
    with path.open('r', encoding='utf-8') as f:
        for line_no, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:  # skip empty lines
                continue
            yield _parse_line(line, line_no)


def _write_jsonl(
    records: Iterable[Tuple[str, str]],
    destination: Path,
) -> None:
    """
    Write the given records to ``destination`` as JSONL using an atomic write.

    Args:
        records: Iterable of (role, content) tuples.
        destination: Target file path.

    Raises:
        OSError: If the temporary file cannot be written or renamed.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)

    # Create a temporary file in the same directory to guarantee atomic rename.
    with tempfile.NamedTemporaryFile(
        mode='w',
        encoding='utf-8',
        delete=False,
        dir=str(destination.parent),
        prefix=f".{destination.name}.tmp.",
    ) as tmp_file:
        tmp_path = Path(tmp_file.name)
        for role, content in records:
            json_line = json.dumps({"role": role, "content": content}, ensure_ascii=False)
            tmp_file.write(json_line + "\n")
        tmp_file.flush()
        os.fsync(tmp_file.fileno())

    # Atomic replace
    os.replace(str(tmp_path), str(destination))


def convert_transcript_to_jsonl(
    src: Path,
    dst: Path,
) -> None:
    """
    High‑level helper that reads ``src`` and writes the JSONL to ``dst``.
    """
    records = list(_read_transcript(src))
    _write_jsonl(records, dst)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert a plain‑text conversation transcript to JSONL."
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to the transcript file (plain text).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help=(
            "Destination JSONL file. If omitted, the output will be written to "
            "`<input>.jsonl` in the same directory."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    input_path: Path = args.input
    if not input_path.is_file():
        print(f"Error: input file '{input_path}' does not exist or is not a file.", file=sys.stderr)
        return 1

    output_path: Path = args.output or input_path.with_suffix(".jsonl")

    try:
        convert_transcript_to_jsonl(input_path, output_path)
    except Exception as exc:  # pragma: no cover – top‑level guard
        print(f"Failed to convert transcript: {exc}", file=sys.stderr)
        return 1

    print(f"Successfully wrote JSONL to: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
