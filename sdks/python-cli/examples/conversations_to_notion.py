#!/usr/bin/env python3
"""
conversations_to_notion.py

A CLI utility that converts a conversation JSON file into a Notion API
compatible block payload. The input file is expected to contain a list of
messages, each with a `role` (e.g. "user", "assistant") and a `content`
string. The output is a JSON array of Notion block objects that can be
directly sent to the Notion API via the `blocks` endpoint.

The script writes the output to a temporary file and atomically replaces
the target file to avoid partial writes.

Usage:
    python conversations_to_notion.py <input.json> <output.json>
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List


def _validate_message(msg: Dict[str, Any]) -> None:
    """Validate that a message dict contains the required keys."""
    if not isinstance(msg, dict):
        raise ValueError(f"Message is not a dict: {msg!r}")
    if "role" not in msg or "content" not in msg:
        raise ValueError(f"Message missing required keys: {msg!r}")


def _convert_message_to_block(msg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a single conversation message into a Notion paragraph block.
    The role is prefixed to the content for clarity.
    """
    role = msg["role"]
    content = msg["content"]
    text = f"{role}: {content}"
    block = {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "text": [
                {
                    "type": "text",
                    "text": {"content": text},
                    "annotations": {"bold": False, "italic": False, "strikethrough": False, "underline": False, "code": False, "color": "default"},
                    "plain_text": text,
                    "href": None,
                }
            ]
        },
    }
    return block


def convert_conversation_to_notion_blocks(conversation: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert a list of conversation messages into Notion block payloads.

    Parameters
    ----------
    conversation : List[Dict[str, Any]]
        List of message dictionaries with `role` and `content`.

    Returns
    -------
    List[Dict[str, Any]]
        List of Notion block objects.
    """
    blocks: List[Dict[str, Any]] = []
    for msg in conversation:
        _validate_message(msg)
        block = _convert_message_to_block(msg)
        blocks.append(block)
    return blocks


def _write_atomic(path: Path, data: Any) -> None:
    """
    Write JSON data to a temporary file and atomically replace the target file.
    """
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp_file:
            json.dump(data, tmp_file, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        # Clean up temp file on failure
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def main(argv: List[str]) -> None:
    if len(argv) != 3:
        print("Usage: python conversations_to_notion.py <input.json> <output.json>", file=sys.stderr)
        sys.exit(1)

    input_path = Path(argv[1])
    output_path = Path(argv[2])

    try:
        with input_path.open("r", encoding="utf-8") as f:
            conversation = json.load(f)
    except FileNotFoundError:
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse JSON from {input_path}: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(conversation, list):
        print(f"Error: Expected a list of messages in {input_path}", file=sys.stderr)
        sys.exit(1)

    try:
        blocks = convert_conversation_to_notion_blocks(conversation)
    except ValueError as e:
        print(f"Error: Invalid conversation format: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        _write_atomic(output_path, blocks)
    except Exception as e:
        print(f"Error: Failed to write output file {output_path}: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Successfully wrote {len(blocks)} Notion blocks to {output_path}")


if __name__ == "__main__":
    main(sys.argv)
