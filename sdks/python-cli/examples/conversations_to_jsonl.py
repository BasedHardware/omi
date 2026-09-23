#!/usr/bin/env python3
"""
conversations_to_jsonl.py

A small utility that converts a plain‑text conversation transcript into a
JSONL file suitable for LLM fine‑tuning or Retrieval‑Augmented Generation (RAG).

Typical transcript format (one utterance per line, prefixed by the speaker):
    User: How do I bake a cake?
    Assistant: First, pre‑heat your oven...

The script groups alternating *User*/*Assistant* turns into a single JSON
object with a ``messages`` list, writes each object as a line in the output
file, and replaces the target file atomically.

Usage
-----
    python conversations_to_jsonl.py \
        --input path/to/transcript.txt \
        --output path/to/output.jsonl

The ``--output`` argument is optional; if omitted the script will write to
``<input‑stem>.jsonl`` in the same directory as the input file.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import List, Dict, Tuple

# --------------------------------------------------------------------------- #
# Helper functions
# --------------------------------------------------------------------------- #


def _parse_line(line: str) -> Tuple[str, str]:
    """
    Parse a single line of the transcript.

    Expected format: ``<Speaker>: <utterance>``.
    Returns a tuple ``(speaker, utterance)`` with whitespace stripped.

    Raises:
        ValueError: If the line does not contain a colon separator.
    """
    if ":" not in line:
        raise ValueError(f"Line does not contain a speaker delimiter ':': {line!r}")

    speaker, utterance = line.split(":", 1)
    return speaker.strip().lower(), utterance.strip()


def _group_conversations(
    parsed_lines: List[Tuple[str, str]]
) -> List[List[Dict[str, str]]]:
    """
    Convert a flat list of ``(speaker, utterance)`` tuples into a list of
    conversations, each represented as a list of message dictionaries.

    The function assumes that a conversation starts with a *user* turn and
    alternates between *user* and *assistant*. If the alternation breaks,
    the current conversation is closed and a new one starts.

    Returns:
        List of conversations, where each conversation is a list of dicts:
        ``[{"role": "user", "content": "..."},
            {"role": "assistant", "content": "..."}]``
    """
    conversations: List[List[Dict[str, str]]] = []
    current: List[Dict[str, str]] = []

    expected_role = "user"  # we start expecting a user turn

    role_map = {"user": "user", "assistant": "assistant"}

    for speaker, utterance in parsed_lines:
        # Normalise speaker name
        role = role_map.get(speaker, None)

        if role is None:
            # Unknown speaker – treat as a break in the conversation
            if current:
                conversations.append(current)
                current = []
            expected_role = "user"
            continue

        if role != expected_role:
            # Break in alternation – start a new conversation
            if current:
                conversations.append(current)
                current = []
            # Reset expectation based on the current role
            expected_role = "assistant" if role == "user" else "user"

        current.append({"role": role, "content": utterance})
        # Flip expectation for next turn
        expected_role = "assistant" if role == "user" else "user"

    if current:
        conversations.append(current)

    return conversations


def _write_jsonl_atomic(conversations: List[List[Dict[str, str]]], target_path: Path) -> None:
    """
    Write the list of conversations to ``target_path`` as JSONL, using an
    atomic replace to avoid partial writes.

    Each line is a JSON object with a single key ``messages``.
    """
    # Ensure parent directory exists
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to a temporary file in the same directory
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        delete=False,
        dir=str(target_path.parent),
        suffix=".tmp",
    ) as tmp_file:
        for conv in conversations:
            json_line = json.dumps({"messages": conv}, ensure_ascii=False)
            tmp_file.write(json_line + "\n")
        tmp_file.flush()
        os.fsync(tmp_file.fileno())

    # Atomically replace the target file
    os.replace(tmp_file.name, target_path)


# --------------------------------------------------------------------------- #
# Main CLI
# --------------------------------------------------------------------------- #


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert a plain‑text conversation transcript to JSONL."
    )
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        required=True,
        help="Path to the input transcript file (UTF‑8 text).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help=(
            "Path to the output JSONL file. If omitted, the output will be "
            "`<input‑stem>.jsonl` in the same directory as the input."
        ),
    )
    return parser


def main(argv: List[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    input_path: Path = args.input
    if not input_path.is_file():
        sys.stderr.write(f"Error: Input file does not exist: {input_path}\n")
        return 1

    output_path: Path = args.output or input_path.with_suffix(".jsonl")

    try:
        # ------------------------------------------------------------------- #
        # Read & parse the transcript
        # ------------------------------------------------------------------- #
        raw_lines = input_path.read_text(encoding="utf-8").splitlines()
        parsed: List[Tuple[str, str]] = [_parse_line(line) for line in raw_lines if line.strip()]

        # ------------------------------------------------------------------- #
        # Group into conversations
        # ------------------------------------------------------------------- #
        conversations = _group_conversations(parsed)

        if not conversations:
            sys.stderr.write("Warning: No valid conversations were detected.\n")

        # ------------------------------------------------------------------- #
        # Write output atomically
        # ------------------------------------------------------------------- #
        _write_jsonl_atomic(conversations, output_path)

        print(f"✅ Successfully wrote {len(conversations)} conversation(s) to {output_path}")
        return 0

    except Exception as exc:  # pylint: disable=broad-except
        sys.stderr.write(f"Error while processing: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
