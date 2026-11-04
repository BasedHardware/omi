#!/usr/bin/env python3
"""Pin the installed-loader geometry; optionally check a generated PM map.
The legacy source pm_static.yml app entry is inconsistent, as documented there;
never 'repair' it here. The fielded generated map is the compatibility authority.
"""
import argparse
import hashlib
from pathlib import Path
import re

FW = Path(__file__).resolve().parents[1]
PINNED = FW / "tools/cv1/pinned-partitions.yml"
# Baseline retained generated map, docs/ota-development.md.
PINNED_SHA = "345f6b77aa32407ed2aaf33c8d2d7809b37e37a68f920ad30fd5fb647a4d1f5a"
# Preserve the legacy source as well, including its documented discrepancy.
SOURCE_SHA = "404afad13e0bc4eab66ba137c31aa23afbe388dc26eca2bd6940918719f03b1f"


def regions(path):
    result = {}
    name = None
    for line in path.read_text().splitlines():
        if line and not line.startswith(" ") and ":" in line:
            name = line.split(":", 1)[0]
            result[name] = {}
        match = re.fullmatch(r"  (address|end_address|size): (0x[0-9a-fA-F]+)", line)
        if match:
            result[name][match[1]] = int(match[2], 16)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated", type=Path)
    args = parser.parse_args()
    assert hashlib.sha256(PINNED.read_bytes()).hexdigest() == PINNED_SHA, "fielded map changed"
    assert hashlib.sha256((FW / "boards/omi/pm_static.yml").read_bytes()).hexdigest() == SOURCE_SHA, "legacy PM source changed"
    pinned = regions(PINNED)
    for name, r in pinned.items():
        if all(k in r for k in ("address", "end_address", "size")):
            assert r["address"] + r["size"] == r["end_address"], name
    if args.generated:
        generated = regions(args.generated)
        for name in pinned:
            assert generated.get(name) == pinned[name], f"generated geometry differs: {name}"
    assert pinned["pcd_sram"]["end_address"] <= 0x2006FF00
    assert 0x2006FF40 <= pinned["rpmsg_nrf53_sram"]["address"]
    print("OTA geometry: fielded map and legacy PM source unchanged; retained slice outside PCD/IPC")


if __name__ == "__main__":
    main()
