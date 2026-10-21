#!/usr/bin/env python3
"""Resolve a prod Android build number against the live Google Play floor.

Google Play version codes are global and immutable: once a code is used by
any upload it can never be reused.  The internal-auto lane keeps allocating
``floor + 1`` on every build, so a release tag pinned before those builds can
carry a build number the Play store has already burned.  The tag number stays
authoritative while it is above the floor; otherwise ``floor + 1`` is
allocated so a prod publish can never collide with an already-used code.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mobile_release_identity import MAX_BUILD_NUMBER
from mobile_store_version import StoreLookupError, parse_play_output

BUILD_NUMBER_SOURCE_TAG = "tag"
BUILD_NUMBER_SOURCE_PLAY_FLOOR = "play_floor"


def resolve_build_number(tag_number: int, play_output: str) -> tuple[int, str]:
    """Return ``(build_number, source)`` for a tag number and a Play read.

    ``play_output`` is the raw ``google-play get-latest-build-number``
    stdout; blank output is an explicit empty-history result and keeps the
    tag number.
    """
    snapshot = parse_play_output(play_output)
    if snapshot.status == "empty":
        return tag_number, BUILD_NUMBER_SOURCE_TAG
    floor = snapshot.build_number
    assert floor is not None, "available snapshots always carry a build number"
    if floor < tag_number:
        return tag_number, BUILD_NUMBER_SOURCE_TAG
    if floor >= MAX_BUILD_NUMBER:
        raise StoreLookupError("play floor leaves no allocatable build number")
    return floor + 1, BUILD_NUMBER_SOURCE_PLAY_FLOOR


def _require_tag_number(value: str) -> int:
    if not value.isdigit() or not value.isascii():
        raise ValueError("tag number must be a positive integer")
    number = int(value)
    if number <= 0:
        raise ValueError("tag number must be a positive integer")
    if number > MAX_BUILD_NUMBER:
        raise ValueError(f"tag number must be <= {MAX_BUILD_NUMBER}")
    return number


def _read_play_output(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag-number", required=True)
    parser.add_argument(
        "--play-output",
        required=True,
        help="file containing raw google-play get-latest-build-number stdout, or - for stdin",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        tag_number = _require_tag_number(args.tag_number)
        build_number, source = resolve_build_number(tag_number, _read_play_output(args.play_output))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps({"build_number": build_number, "source": source}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
