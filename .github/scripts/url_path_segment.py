#!/usr/bin/env python3
"""Encode one untrusted value for use as a URL path segment."""

from __future__ import annotations

import argparse
from urllib.parse import quote


def encode(value: str) -> str:
    return quote(value, safe="")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("value")
    args = parser.parse_args()
    print(encode(args.value))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
