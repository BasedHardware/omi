#!/usr/bin/env python3
"""Static tripwire: sensitive Omi GATT attributes must use OMI_GATT_PERM_*.

Not a behavioural test -- the firmware has no host-runnable GATT harness. It
exists because the migration is silently reversible: when upstream moved the
button GATT service back from button_service.c into button.c, the merge
resolved cleanly and the button characteristic returned to plain
BT_GATT_PERM_READ with nothing failing.

BT_GATT_PERM_* stays legal only for the attributes listed in ALLOWED, which
carry no user content and are read before pairing.
"""

import re
import sys
from pathlib import Path

FIRMWARE_SRC = Path("omi/firmware/omi/src")

# Attributes that may keep plain permissions, with the reason they are exempt.
ALLOWED = {
    "features_characteristic_uuid": "features bitmap: no user content, read before pairing to pick a protocol",
}

PERM_RE = re.compile(r"\bBT_GATT_PERM_(?:READ|WRITE)\b")
UUID_RE = re.compile(r"&(\w+)\.uuid")


def violations(root: Path):
    found = []
    for path in sorted(root.rglob("*.c")):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for index, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            if not PERM_RE.search(line):
                continue
            context = "\n".join(lines[max(0, index - 8) : index + 1])
            names = UUID_RE.findall(context)
            if names and names[-1] in ALLOWED:
                continue
            found.append((path, index + 1, stripped))
    return found


def main() -> int:
    root = Path(__file__).resolve().parents[2] / FIRMWARE_SRC
    if not root.is_dir():
        print(f"firmware source tree not found: {root}", file=sys.stderr)
        return 1

    found = violations(root)
    if not found:
        print("firmware BLE permissions: all sensitive GATT attributes use OMI_GATT_PERM_*")
        return 0

    print("Sensitive GATT attributes must use OMI_GATT_PERM_* (see omi/firmware/omi/src/lib/core/ble_perm.h):")
    for path, line_no, text in found:
        print(f"  {path}:{line_no}: {text}")
    print("Replace BT_GATT_PERM_READ/WRITE with OMI_GATT_PERM_READ/WRITE (CCC: OMI_GATT_PERM_CCC),")
    print("or add the attribute to ALLOWED in this script with the reason it carries no user content.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
