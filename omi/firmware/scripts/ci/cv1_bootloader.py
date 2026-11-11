#!/usr/bin/env python3
"""Strict Intel HEX boot-region policy; no third-party parser or signing key access."""

import argparse
import hashlib
import json
from pathlib import Path

BOOT_END = 0x10000
POLICY = Path(__file__).resolve().parents[2] / 'bootloader' / 'cv1-bootloader-policy.json'


def read_hex(path):
    memory = {}
    base = 0
    eof = False
    for number, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line or eof or not line.startswith(':'):
            raise ValueError(f'{path}:{number}: invalid HEX record or data after EOF')
        try:
            record = bytes.fromhex(line[1:])
        except ValueError as error:
            raise ValueError(f'{path}:{number}: invalid HEX encoding') from error
        if len(record) < 5 or record[0] + 5 != len(record) or sum(record) & 255:
            raise ValueError(f'{path}:{number}: HEX length/checksum mismatch')
        size, address, kind = record[0], int.from_bytes(record[1:3], 'big'), record[3]
        data = record[4:-1]
        if kind == 0:
            if not size or address + size > 0x10000:
                raise ValueError('Empty or wrapping HEX data record')
            for offset, byte in enumerate(data):
                absolute = base + address + offset
                if absolute in memory:
                    raise ValueError(f'Overlapping HEX address {absolute:#x}')
                memory[absolute] = byte
        elif kind == 1 and size == 0 and address == 0:
            eof = True
        elif kind in (2, 4) and size == 2 and address == 0:
            base = int.from_bytes(data, 'big') << (4 if kind == 2 else 16)
        elif kind in (3, 5) and size == 4 and address == 0:
            pass  # execution start metadata, not flash data
        else:
            raise ValueError(f'Unsupported/malformed HEX record type {kind}')
    if not eof or not memory:
        raise ValueError('HEX requires data and a terminal EOF')
    return memory


def boot_bytes(memory):
    return bytes(memory.get(address, 0xff) for address in range(BOOT_END))


def inspect_hex(path, policy=POLICY):
    memory = read_hex(path)
    if not any(address < BOOT_END for address in memory):
        return {'kind': 'bootloader-free', 'boot_sha256': None}
    digest = hashlib.sha256(boot_bytes(memory)).hexdigest()
    approved = json.loads(Path(policy).read_text())['approved_boot_sha256']
    if digest not in approved:
        raise ValueError(f'{path}: unapproved CV1 boot region sha256={digest}; never flash stock MCUboot')
    return {'kind': 'approved-bootloader', 'boot_sha256': digest}


def record(address, kind, data):
    raw = bytes([len(data)]) + address.to_bytes(2, 'big') + bytes([kind]) + bytes(data)
    return ':' + (raw + bytes([-sum(raw) & 255])).hex().upper()


def write_hex(path, memory):
    lines = []
    upper = None
    addresses = sorted(memory)
    index = 0
    while index < len(addresses):
        start = addresses[index]
        if start >> 16 != upper:
            upper = start >> 16
            lines.append(record(0, 4, upper.to_bytes(2, 'big')))
        data = [memory[start]]
        index += 1
        while index < len(addresses) and len(data) < 16 and addresses[index] == start + len(data) and addresses[index] >> 16 == upper:
            data.append(memory[addresses[index]])
            index += 1
        lines.append(record(start & 0xffff, 0, data))
    lines.append(record(0, 1, b''))
    Path(path).write_text('\n'.join(lines) + '\n')


def app_hex(image, target):
    """Wire recovery uses the exact OTA signed bytes and preserves factory state."""
    if not image or len(image) > 0xf6000 - BOOT_END:
        raise ValueError('Signed application must fit entirely below storage at 0xf6000')
    write_hex(target, dict(enumerate(image, BOOT_END)))
    inspect_hex(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('hex', type=Path, nargs='+')
    args = parser.parse_args()
    for path in args.hex:
        print(json.dumps({'file': path.name, **inspect_hex(path)}, sort_keys=True))


if __name__ == '__main__':
    main()
