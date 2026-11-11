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


def inspect_hex(path, policy=None):
    memory = read_hex(path)
    if not any(address < BOOT_END for address in memory):
        return {'kind': 'bootloader-free', 'boot_sha256': None}
    digest = hashlib.sha256(boot_bytes(memory)).hexdigest()
    approved = json.loads(Path(policy or POLICY).read_text())['approved_boot_sha256']
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


def validate_build_bootloader(memory):
    """A build must reproduce the jig-qualified loader, not merely any allowed state."""
    if not memory or min(memory) != 0 or max(memory) >= BOOT_END:
        raise ValueError('MCUboot initialized bytes must fit inside [0, 0x10000) and start at zero')
    policy = json.loads(POLICY.read_text())
    expected = policy['build_boot_sha256']
    if expected not in policy['approved_boot_sha256']:
        raise ValueError('Pinned build bootloader must also be approved')
    image = boot_bytes(memory)
    if hashlib.sha256(image).hexdigest() != expected:
        raise ValueError('MCUboot must match the pinned build bootloader SHA-256')
    return image


def app_memory(image):
    if not image or len(image) > 0xf6000 - BOOT_END:
        raise ValueError('Signed application must fit entirely below storage at 0xf6000')
    return dict(enumerate(image, BOOT_END))


def wire_memory(image, boot_image):
    """Canonical release image: approved boot reservation plus the exact OTA app."""
    if len(boot_image) != BOOT_END:
        raise ValueError('Wire bootloader must cover the full 64 KiB reservation')
    memory = dict(enumerate(boot_image))
    validate_build_bootloader(memory)
    memory.update(app_memory(image))
    return memory


def validate_release_hex(path, signed_image):
    """Reparse a release HEX and bind its entire memory map to the shipping pin/app."""
    memory = read_hex(path)
    boot_image = validate_build_bootloader({address: byte for address, byte in memory.items() if address < BOOT_END})
    if memory != wire_memory(signed_image, boot_image):
        raise ValueError('Release app HEX must contain exactly the pinned bootloader and tested OTA signed bytes')
    return {'kind': 'approved-bootloader', 'boot_sha256': hashlib.sha256(boot_image).hexdigest()}


def app_hex(image, target):
    """Optional app-only recovery preserves the installed approved bootloader."""
    write_hex(target, app_memory(image))
    inspect_hex(target)


def inspect_role(path, role):
    result = inspect_hex(path)
    if role is None:
        return result
    memory = read_hex(path)
    minimum = BOOT_END if role == 'app' else 0
    if min(memory) < minimum or max(memory) >= 0xf6000:
        raise ValueError('Wire image includes bytes outside the allowed app-core window (storage/UICR/network excluded)')
    if bytes(memory.get(BOOT_END + i, 0xff) for i in range(4)) != bytes.fromhex('3db8f396'):
        raise ValueError('Wire image is missing the signed app header at 0x10000')
    if role == 'manufacturing' and result['kind'] != 'approved-bootloader':
        raise ValueError('Manufacturing image must contain an approved bootloader, not just an app')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('hex', type=Path, nargs='+')
    role = parser.add_mutually_exclusive_group()
    role.add_argument('--app-only', action='store_const', dest='role', const='app')
    role.add_argument('--require-bootloader', action='store_const', dest='role', const='manufacturing')
    parser.add_argument('--signed-app', type=Path, help='Exact omi.signed.bin extracted from the intended OTA ZIP')
    args = parser.parse_args()
    if (args.role == 'manufacturing') != (args.signed_app is not None):
        parser.error('--require-bootloader and --signed-app must be used together')
    for path in args.hex:
        result = (validate_release_hex(path, args.signed_app.read_bytes())
                  if args.role == 'manufacturing' else inspect_role(path, args.role))
        print(json.dumps({'file': path.name, **result}, sort_keys=True))


if __name__ == '__main__':
    main()
