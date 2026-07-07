#!/usr/bin/env python3
"""Shared KEY_VALUE_START/KEY_VALUE_END release-metadata parsing.

Used by check-desktop-release-promotion.py and mark-desktop-release-stable.py
so the two scripts can't silently drift on how the block is parsed.
"""

from __future__ import annotations


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def normalize_metadata_line(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("<!--"):
        stripped = stripped[4:].strip()
    if stripped.endswith("-->"):
        stripped = stripped[:-3].strip()
    return stripped


def parse_metadata(body: str) -> dict[str, str]:
    in_block = False
    metadata: dict[str, str] = {}

    for line in body.splitlines():
        stripped = normalize_metadata_line(line)
        if stripped == "KEY_VALUE_START":
            in_block = True
            continue
        if stripped == "KEY_VALUE_END":
            return metadata
        if not in_block or not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            fail(f"invalid release metadata line: {stripped}")
        key, value = stripped.split(":", 1)
        metadata[key.strip()] = value.strip()

    fail("release body is missing KEY_VALUE_START/KEY_VALUE_END metadata block")
