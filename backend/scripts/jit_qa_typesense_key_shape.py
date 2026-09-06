#!/usr/bin/env python3
"""Validate and normalize the isolated QA Typesense API-key byte shape.

Secret Manager preserves the bytes written by the workflow.  This helper keeps
the deployment boundary explicit: a key is exactly 64 lowercase hex bytes, or
the one legacy shape produced by piping ``openssl rand -hex 32`` to a secret
upload (64 lowercase hex bytes followed by one LF).  No key bytes are printed
by the file-oriented command.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Literal

KEY_BYTES = 32
KEY_HEX_LENGTH = KEY_BYTES * 2
LEGACY_TRAILING_LF_LENGTH = KEY_HEX_LENGTH + 1
KeyShape = Literal["valid", "legacy_trailing_lf", "invalid"]
_HEX_KEY_RE = re.compile(rb"[0-9a-f]+\Z")


def classify_typesense_api_key(value: bytes) -> KeyShape:
    """Classify without decoding or logging the secret bytes."""

    if len(value) == KEY_HEX_LENGTH and _HEX_KEY_RE.fullmatch(value):
        return "valid"
    if len(value) == LEGACY_TRAILING_LF_LENGTH and value[-1:] == b"\n" and _HEX_KEY_RE.fullmatch(value[:-1]):
        return "legacy_trailing_lf"
    return "invalid"


def normalize_typesense_api_key(value: bytes) -> bytes:
    """Return the exact server key, repairing only the known legacy shape."""

    shape = classify_typesense_api_key(value)
    if shape == "valid":
        return value
    if shape == "legacy_trailing_lf":
        return value[:-1]
    raise ValueError("Typesense API key has an unexpected byte shape")


def _write_private_file(path: Path, value: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(value)
    except BaseException:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--normalize-stdin", action="store_true")
    modes.add_argument("--normalize-file", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        if args.normalize_stdin:
            if args.output is not None:
                raise ValueError("--output is only valid with --normalize-file")
            normalized = normalize_typesense_api_key(sys.stdin.buffer.read())
            sys.stdout.buffer.write(normalized)
            return 0

        if args.output is None:
            raise ValueError("--output is required with --normalize-file")
        raw = args.normalize_file.read_bytes()
        shape = classify_typesense_api_key(raw)
        if shape == "invalid":
            raise ValueError("Typesense API key has an unexpected byte shape")
        _write_private_file(args.output, normalize_typesense_api_key(raw))
        print(shape)
        # Exit 2 identifies the one repairable legacy shape without exposing
        # any secret material to the workflow log.
        return 2 if shape == "legacy_trailing_lf" else 0
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
