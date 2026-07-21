#!/usr/bin/env python3
"""Fail closed unless a Stable pointer mutation has explicit operator intent."""

from __future__ import annotations

import argparse


CONFIRMATION = "promote-stable"
OPERATIONS = {"promote", "repoint"}


def validate(*, operation: str, confirm: str) -> None:
    if operation not in OPERATIONS:
        raise ValueError(f"unsupported Stable operation: {operation}")
    if confirm != CONFIRMATION:
        raise ValueError(f"confirm must be exactly: {CONFIRMATION}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--operation", required=True)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    try:
        validate(operation=args.operation, confirm=args.confirm)
    except ValueError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
