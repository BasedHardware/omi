#!/usr/bin/env python3
"""Check generated app AND fielded MCUboot maps before jig qualification.
Do not substitute an unrelated/new bootloader map for the installed baseline.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

START, END = 0x2006FF00, 0x2006FF40


def check(path, app=False):
    text = path.read_text()
    # GNU ld output/input section allocations; input sections repeat extents.
    spans = []
    for name, address, size in re.findall(
        r"^\s*(\.[\w.]+|noinit)\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)", text, re.M
    ):
        address, size = int(address, 16), int(size, 16)
        if not size or not (0x20000000 <= address < 0x20080000):
            continue
        if app and name == ".omi_retained":
            assert address == START and address + size <= END
        else:
            assert address + size <= START or address >= END, f"{path}: {name} overlaps retained RAM"
            spans.append((address, address + size))
    assert spans, f"{path}: no SRAM allocations found; wrong/unsupported map"
    if app:
        assert re.search(r"^\.omi_retained\s+0x0*2006ff00\b", text, re.M), "retained section missing"
    return {"map": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "max_other_sram_end": hex(max(end for _, end in spans))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mcuboot-map", type=Path, required=True)
    parser.add_argument("--app-map", type=Path, required=True)
    parser.add_argument("--baseline-app-map", type=Path, required=True)
    args = parser.parse_args()
    # Decoder address 0x20002010 is the up-buffer pointer, not control block.
    def rtt_symbols(path):
        text = path.read_text()
        symbols = {name: int(address, 16) for address, name in re.findall(
            r"(0x[0-9a-fA-F]+)\s+(_SEGGER_RTT|_acUpBuffer)\b", text)}
        # Local RTT buffers may appear only as input section names in a map.
        match = re.search(r"\.(?:bss|data|noinit)\._acUpBuffer\s+(0x[0-9a-fA-F]+)", text)
        if match:
            symbols["_acUpBuffer"] = int(match[1], 16)
        return symbols
    baseline_rtt = rtt_symbols(args.baseline_app_map)
    assert rtt_symbols(args.app_map) == baseline_rtt, "baseline RTT symbol addresses changed"
    print(json.dumps({"baseline_rtt_symbols": baseline_rtt, "reserved": [hex(START), hex(END)],
                      "mcuboot": check(args.mcuboot_map), "app": check(args.app_map, True)}, indent=2))


if __name__ == "__main__":
    main()
