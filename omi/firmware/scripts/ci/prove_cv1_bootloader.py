#!/usr/bin/env python3
"""Emit public-only MCUboot equivalence evidence. No PEM files are opened."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from cv1_bootloader import BOOT_END, POLICY, boot_bytes, read_hex

KEY_SHA256 = 'fc5701dc6135e1323847bdc40f04d2e5bee5833b23c29f93593d00018cfa9994'


def require(value, message):
    if not value:
        raise ValueError(message)


def public_key(image):
    # imgtool embeds a 270-byte PKCS#1 RSA-2048 public DER sequence. Identify
    # by public digest, never by reading or printing a private signing key.
    prefix = bytes.fromhex('3082010a0282010100')
    matches = [image[i:i + 270] for i in range(len(image)) if image.startswith(prefix, i)]
    matches = [key for key in matches if hashlib.sha256(key).hexdigest() == KEY_SHA256]
    require(len(matches) == 1, 'Expected exactly one factory release public key in MCUboot')
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--objdump', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    fw = POLICY.parents[1]
    factory = boot_bytes(read_hex(fw / 'FLASH_3.0.8/MAC/merged.hex'))
    memory = read_hex(args.build / 'mcuboot/zephyr/zephyr.hex')
    require(min(memory) == 0 and max(memory) < 0xce00, 'MCUboot must fit below 0xCE00')
    candidate = boot_bytes(memory)
    require(public_key(candidate) == public_key(factory), 'Public key differs from factory')
    partitions = (args.build / 'partitions.yml').read_text()
    for name, address, size in [('mcuboot', 0, BOOT_END), ('mcuboot_pad', BOOT_END, 0x200), ('app', 0x10200, 0xe5e00)]:
        section = re.search(rf'^{name}:\n((?:[ \t].*\n)+)', partitions, re.M)
        require(section, f'Missing partition {name}')
        for key, expected in [('address', address), ('size', size)]:
            match = re.search(rf'^  {key}: (0x[0-9a-f]+|[0-9]+)$', section[1], re.M)
            require(match and int(match[1], 0) == expected, f'Unexpected {name}.{key}')
    config = (args.build / 'mcuboot/zephyr/.config').read_text()
    for setting in ['CONFIG_BOOT_UPGRADE_ONLY=y', 'CONFIG_MCUBOOT_DOWNGRADE_PREVENTION=y', 'CONFIG_DISK_ACCESS=y', 'CONFIG_DISK_DRIVER_SDMMC=y']:
        require(setting in config.splitlines(), f'Missing production setting: {setting}')
    elf = args.build / 'mcuboot/zephyr/zephyr.elf'
    disassembly = subprocess.check_output([args.objdump, '-d', '--disassemble=main', str(elf)], text=True)
    require(disassembly.count('<disk_access_ioctl>') == 2, 'main must call disk ioctl INIT and DEINIT')
    require(disassembly.count('<pm_device_action_run>') == 2, 'main must resume and suspend SD')
    require('<boot_go>' in disassembly, 'Missing boot_go in main')
    require(disassembly.rfind('<disk_access_ioctl>') < disassembly.index('<boot_go>'), 'SD initialization must precede boot_go')
    # Source identity catches an omitted overlay even if unused drivers exist.
    ninja = (args.build / 'mcuboot/build.ninja').read_text()
    require('mcuboot_boot_zephyr.c.obj:' in ninja, 'Custom MCUboot main was not compiled')
    require(not re.search(r'build [^\n]*[/\\]main\.c\.obj:', ninja), 'Stock MCUboot main was compiled')
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'cv1-mcuboot.bin').write_bytes(candidate)
    (args.out / 'main.disassembly.txt').write_text(disassembly)
    for name in ['zephyr.elf', 'zephyr.map', '.config']:
        shutil.copyfile(elf.parent / name, args.out / ('mcuboot.config' if name == '.config' else name))
    shutil.copyfile(args.build / 'partitions.yml', args.out / 'partitions.yml')
    digest = hashlib.sha256(candidate).hexdigest()
    report = {
        'schema_version': 1,
        'source_sha': os.environ.get('GITHUB_SHA', 'local-unrecorded'),
        'run_id': os.environ.get('GITHUB_RUN_ID'),
        'run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
        'factory_boot_sha256': hashlib.sha256(factory).hexdigest(),
        'candidate_boot_sha256': digest,
        'public_key_sha256': KEY_SHA256,
        'boot_region_end': BOOT_END,
        'candidate_data_end': max(memory) + 1,
        'factory_data_end': max(i for i, b in enumerate(factory) if b != 255) + 1,
        'differing_bytes': sum(a != b for a, b in zip(factory, candidate)),
        'primary_slot': BOOT_END,
        'app_vector': 0x10200,
        'mode': 'overwrite-only; no trial rollback',
        'release_approved': digest in json.loads(POLICY.read_text())['approved_boot_sha256'],
        'bench_qualified': False,
    }
    (args.out / 'bootloader-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
