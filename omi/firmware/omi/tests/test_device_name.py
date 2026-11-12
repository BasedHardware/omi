#!/usr/bin/env python3
"""Compile production NVS and advertising code; --source supports negative controls."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=HERE.parent / "src")
    parser.add_argument("--case", choices=["settings", "advertising"])
    args = parser.parse_args()
    source = args.source.resolve()
    with tempfile.TemporaryDirectory(prefix="device-name-") as output:
        out = Path(output)
        for case in ([args.case] if args.case else ["settings", "advertising"]):
            if case == "settings":
                fragment = (source / "settings.c").read_text()
            else:
                transport = (source / "lib/core/transport.c").read_text()
                start = transport.index("static char adv_device_name")
                end = transport.index("//\n// State and Characteristics", start)
                fragment = transport[start:end]
                disconnected = transport.split("static void _transport_disconnected(", 1)[1].split("\n}", 1)[0]
                # Execute the production disconnect scheduling hook, if present.
                # The pre-fix source has no hook and must fail the resume test.
                hook = "advertising_name_disconnected();"
                (out / "disconnected.inc").write_text(hook if hook in disconnected else "")
            (out / f"{case}.inc").write_text(fragment)
            subprocess.run([
                os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-Wno-unused-function", "-Wno-unused-variable", "-fsanitize=undefined",
                "-fno-sanitize-recover=all", "-I", str(HERE / "settings_stubs"),
                "-I", str(source), "-I", str(out), str(HERE / f"test_device_name_{case}.c"),
                "-o", str(out / case),
            ], check=True)
            subprocess.run([str(out / case)], check=True)
        if not args.case:
            transport = (source / "lib/core/transport.c").read_text()
            assert "BT_UUID_128_ENCODE(0x19B10014," in transport
            assert "features |= OMI_FEATURE_DEVICE_NAME;" in transport
            assert "OMI_FEATURE_DEVICE_NAME = (1 << 9)" in (source / "lib/core/features.h").read_text()
            attrs = transport.split("static struct bt_gatt_attr settings_service_attr[]", 1)[1].split("\n};", 1)[0]
            assert attrs.index("BT_GATT_CCC(charging_status") < attrs.index("&settings_device_name_characteristic_uuid.uuid")


if __name__ == "__main__":
    main()
