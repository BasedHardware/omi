#!/usr/bin/env python3
"""Keep OTA slots where the bootloader already installed on CV1 expects them.

MCUboot compiles its slot addresses in, and OTA does not replace it. mcumgr uses
the app's own map, so an app with moved or resized slots writes its image and
upgrade trailer where the installed bootloader never looks, and later OTAs stop
applying. Changing this geometry needs a bootloader migration plan first.

Settings are held to the same pins because moving them loses bonds and mute on
update.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PINNED = ROOT / "tools/cv1/pinned-partitions.yml"
STATIC = ROOT / "boards/omi/pm_static.yml"
OTA_SLOTS = ("mcuboot_primary", "mcuboot_primary_app", "mcuboot_secondary", "mcuboot_secondary_1")


def extents(path):
    """Return {partition: (address, end_address)} from a flat partition map."""
    found = {}
    for name, body in re.findall(r"(?m)^(\w+):\n((?:[ #].*\n)*)", path.read_text()):
        address = re.search(r"(?m)^  address: (0x[0-9a-fA-F]+)", body)
        end = re.search(r"(?m)^  end_address: (0x[0-9a-fA-F]+)", body)
        if address and end:
            found[name] = (int(address.group(1), 16), int(end.group(1), 16))
    return found


def violations(pinned, static):
    problems = []
    for slot in OTA_SLOTS:
        if static.get(slot) != pinned[slot]:
            problems.append(f"{slot}: {static.get(slot)} does not match the installed bootloader's {pinned[slot]}")
    if "settings_storage" in static and static["settings_storage"] != pinned["settings_storage"]:
        problems.append(f"settings_storage: {static['settings_storage']} moves it from {pinned['settings_storage']}")
    return problems


def main(argv):
    static_path = Path(argv[1]) if len(argv) > 1 else STATIC
    problems = violations(extents(PINNED), extents(static_path))
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print("CV1 OTA slot geometry matches the installed bootloader")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
