#!/usr/bin/env python3
"""Rewrite the desktop release metadata block to channel: stable."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from desktop_release_metadata import fail, normalize_metadata_line  # noqa: E402


def mark_stable(body: str) -> str:
    lines = body.splitlines()
    output: list[str] = []
    in_block = False
    saw_block = False
    saw_channel = False

    for line in lines:
        stripped = normalize_metadata_line(line)
        if stripped == "KEY_VALUE_START":
            in_block = True
            saw_block = True
            output.append(line)
            continue
        if stripped == "KEY_VALUE_END":
            if not in_block:
                fail("release body has KEY_VALUE_END without KEY_VALUE_START")
            if not saw_channel:
                output.append("channel: stable")
            in_block = False
            output.append(line)
            continue
        if in_block and stripped.startswith("channel:"):
            output.append("channel: stable")
            saw_channel = True
            continue
        output.append(line)

    if in_block:
        fail("release body metadata block is missing KEY_VALUE_END")
    if not saw_block:
        fail("release body is missing KEY_VALUE_START/KEY_VALUE_END metadata block")

    trailing_newline = "\n" if body.endswith("\n") else ""
    return "\n".join(output) + trailing_newline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    body = Path(args.input).read_text()
    Path(args.output).write_text(mark_stable(body))
    print("desktop release metadata channel set to stable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
