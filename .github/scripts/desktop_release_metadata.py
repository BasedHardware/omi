#!/usr/bin/env python3
"""Shared parsing helpers for desktop release KEY_VALUE metadata."""

from __future__ import annotations

from typing import NoReturn


def fail(message: str) -> NoReturn:
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


def update_metadata(body: str, values: dict[str, str]) -> str:
    """Replace or append keys inside the release metadata block."""
    if any("\n" in value or "\r" in value for value in values.values()):
        fail("release metadata values must be single-line strings")

    lines = body.splitlines()
    output: list[str] = []
    in_block = False
    saw_block = False
    seen: set[str] = set()
    for line in lines:
        stripped = normalize_metadata_line(line)
        if stripped == "KEY_VALUE_START":
            if in_block:
                fail("release body has nested KEY_VALUE_START blocks")
            in_block = True
            saw_block = True
            output.append(line)
            continue
        if stripped == "KEY_VALUE_END":
            if not in_block:
                fail("release body has KEY_VALUE_END without KEY_VALUE_START")
            for key, value in values.items():
                if key not in seen:
                    output.append(f"{key}: {value}")
            in_block = False
            output.append(line)
            continue
        if in_block and ":" in stripped:
            key = stripped.split(":", 1)[0].strip()
            if key in values:
                output.append(f"{key}: {values[key]}")
                seen.add(key)
                continue
        output.append(line)

    if in_block:
        fail("release body metadata block is missing KEY_VALUE_END")
    if not saw_block:
        fail("release body is missing KEY_VALUE_START/KEY_VALUE_END metadata block")
    return "\n".join(output) + ("\n" if body.endswith("\n") else "")
