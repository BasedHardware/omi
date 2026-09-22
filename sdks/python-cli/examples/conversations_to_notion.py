#!/usr/bin/env python3
"""
conversations_to_notion.py

A small utility that converts a conversation JSON payload (as produced by
`sdks/python-cli/examples/conversations_to_json.py` or similar) into a list of
Notion API‑compatible block objects.

The script can be used as a stand‑alone CLI:

    python conversations_to_notion.py INPUT_JSON OUTPUT_JSON

* INPUT_JSON  – Path to a JSON file containing a list of conversation entries.
* OUTPUT_JSON – Path where the Notion block payload will be written.

The conversion rules are intentionally simple and aim to be useful out‑of‑the‑box:

* Each conversation entry becomes a **paragraph** block.
* If an entry contains an ``action_items`` list, each item is rendered as a
  **bulleted_list_item** block placed directly after the paragraph.

The output file is written atomically (via a temporary file + ``os.replace``) to
avoid partially‑written results on failure.

Error handling is defensive: malformed input, missing keys, or I/O problems are
reported with clear messages and a non‑zero exit status.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

# --------------------------------------------------------------------------- #
# Logging configuration
# --------------------------------------------------------------------------- #
LOGGER = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter("%(levelname)s – %(message)s")
handler.setFormatter(formatter)
LOGGER.addHandler(handler)
LOGGER.setLevel(logging.INFO)


# --------------------------------------------------------------------------- #
# Notion block helpers
# --------------------------------------------------------------------------- #
def _rich_text(content: str) -> List[Dict[str, Any]]:
    """Wrap plain text into Notion's rich_text structure."""
    return [{"type": "text", "text": {"content": content}}]


def paragraph_block(text: str) -> Dict[str, Any]:
    """Create a Notion paragraph block."""
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _rich_text(text)},
    }


def bulleted_list_block(text: str) -> Dict[str, Any]:
    """Create a Notion bulleted list item block."""
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": _rich_text(text)},
    }


# --------------------------------------------------------------------------- #
# Core conversion logic
# --------------------------------------------------------------------------- #
def load_conversations(path: Path) -> List[Dict[str, Any]]:
    """Load a JSON file containing a list of conversation entries.

    Expected schema (per entry):
        {
            "speaker": "Alice",
            "text": "Hello world",
            "action_items": ["Do X", "Do Y"]   # optional
        }
    """
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        LOGGER.error("Failed to parse JSON from %s: %s", path, exc)
        raise
    except OSError as exc:
        LOGGER.error("Unable to read %s: %s", path, exc)
        raise

    if not isinstance(data, list):
        raise ValueError(f"Root JSON element must be a list, got {type(data)}")
    return data


def convert_entry(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert a single conversation entry into Notion blocks."""
    if "text" not in entry:
        raise KeyError("Conversation entry missing required key 'text'")

    speaker = entry.get("speaker")
    text = entry["text"]
    # Prefix speaker name if present
    paragraph_text = f"{speaker}: {text}" if speaker else text
    blocks: List[Dict[str, Any]] = [paragraph_block(paragraph_text)]

    # Optional action items
    action_items = entry.get("action_items", [])
    if not isinstance(action_items, list):
        raise TypeError("'action_items' must be a list if present")
    for item in action_items:
        if not isinstance(item, str):
            raise TypeError("Each action item must be a string")
        blocks.append(bulleted_list_block(item))

    return blocks


def conversations_to_notion_blocks(conversations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Transform the whole conversation list into a flat list of Notion blocks."""
    notion_blocks: List[Dict[str, Any]] = []
    for idx, entry in enumerate(conversations, start=1):
        try:
            notion_blocks.extend(convert_entry(entry))
        except Exception as exc:
            LOGGER.error("Error processing entry #%d: %s", idx, exc)
            raise
    return notion_blocks


def write_atomic(data: Any, destination: Path) -> None:
    """Write JSON data to *destination* atomically."""
    temp_dir = destination.parent
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            dir=temp_dir,
            suffix=".tmp",
        ) as tmp_file:
            json.dump(data, tmp_file, ensure_ascii=False, indent=2)
            tmp_path = Path(tmp_file.name)
        # On POSIX, os.replace is atomic; on Windows it overwrites.
        os.replace(tmp_path, destination)
        LOGGER.info("Successfully wrote %d Notion blocks to %s", len(data), destination)
    except Exception as exc:
        LOGGER.error("Failed to write output file %s: %s", destination, exc)
        # Cleanup temp file if it still exists
        try:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink()
        finally:
            raise


# --------------------------------------------------------------------------- #
# CLI entry point
# --------------------------------------------------------------------------- #
def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert conversation JSON to Notion API block payloads."
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to the input JSON file containing conversation entries.",
    )
    parser.add_argument(
        "output",
        type=Path,
        help="Path where the Notion block JSON will be written.",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        conversations = load_conversations(args.input)
        notion_blocks = conversations_to_notion_blocks(conversations)
        write_atomic(notion_blocks, args.output)
    except Exception:
        LOGGER.exception("Conversion failed.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
