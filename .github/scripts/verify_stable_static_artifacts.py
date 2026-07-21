#!/usr/bin/env python3
"""Verify exact Stable static publication against the retained manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from desktop_repair_installer import build_repair_bundle


def verify(latest: object, index: str, manifest: dict, bucket: str) -> None:
    """Fail closed unless both public stable artifacts equal the manifest render.

    The retained manifest is the authority. Re-rendering its static repair
    bundle makes the release ID, immutable DMG URL, SHA-256, and HTML download
    target one comparison rather than trusting mutable release metadata.
    """
    if not isinstance(latest, dict):
        raise ValueError("published stable latest.json must be a JSON object")
    expected = build_repair_bundle(manifest, bucket)
    if latest != expected["latest"]:
        raise ValueError("published stable latest.json differs from the retained manifest identity")
    if index != expected["landing_page"]:
        raise ValueError("published stable index.html differs from the retained manifest installer identity")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--latest", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--bucket", required=True)
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    latest = json.loads(args.latest.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("retained manifest must be a JSON object")
    verify(latest, args.index.read_text(encoding="utf-8"), manifest, args.bucket)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
