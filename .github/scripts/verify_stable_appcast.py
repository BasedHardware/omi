#!/usr/bin/env python3
"""Verify the default Stable appcast item for one retained manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from xml.etree import ElementTree as ET

SPARKLE = "http://www.andymatuschak.org/xml-namespaces/sparkle"


def verify(manifest: dict, feed: Path) -> None:
    root = ET.parse(feed).getroot()
    matches = []
    for item in root.findall(".//item"):
        enclosure = item.find("enclosure")
        if enclosure is None or item.findtext(f"{{{SPARKLE}}}channel") == "beta":
            continue
        if (
            item.findtext(f"{{{SPARKLE}}}version") == str(manifest["build_number"])
            and item.findtext(f"{{{SPARKLE}}}shortVersionString") == manifest["version"]
            and enclosure.get("url") == manifest["zip_url"]
            and enclosure.get(f"{{{SPARKLE}}}edSignature") == manifest["ed_signature"]
        ):
            matches.append(item)
    if len(matches) != 1:
        raise ValueError("stable appcast must contain exactly one default/non-beta immutable requested item")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--feed", type=Path, required=True)
    args = parser.parse_args()
    verify(json.loads(args.manifest.read_text(encoding="utf-8")), args.feed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
