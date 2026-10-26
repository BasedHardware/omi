#!/usr/bin/env python3
"""Attest an explicit virtual target and pinned runtime before any installation."""
import argparse
import json
from pathlib import Path
import re
import subprocess


def read(command):
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=20).stdout.strip()


def attest(platform, device, runtime_build):
    if not runtime_build:
        raise ValueError('an exact --runtime-build is required for virtual qualification')
    if platform == 'android':
        if not re.fullmatch(r'emulator-[0-9]+', device):
            raise ValueError('virtual Android target must be an explicit emulator serial')
        if read(['adb', '-s', device, 'shell', 'getprop', 'ro.kernel.qemu']) != '1':
            raise ValueError('target is not an Android emulator')
        actual = read(['adb', '-s', device, 'shell', 'getprop', 'ro.build.fingerprint'])
        details = {'kind': 'android-emulator', 'runtime_build': actual,
                   'size': read(['adb', '-s', device, 'shell', 'wm', 'size']),
                   'density': read(['adb', '-s', device, 'shell', 'wm', 'density']),
                   'model': read(['adb', '-s', device, 'shell', 'getprop', 'ro.product.model'])}
    else:
        inventory = json.loads(read(['xcrun', 'simctl', 'list', 'devices', 'booted', '-j']))
        matches = [(runtime, entry) for runtime, entries in inventory['devices'].items()
                   for entry in entries if entry['udid'] == device and entry['state'] == 'Booted']
        if len(matches) != 1:
            raise ValueError('target must match exactly one booted iOS simulator')
        runtime, entry = matches[0]
        runtimes = json.loads(read(['xcrun', 'simctl', 'list', 'runtimes', '-j']))['runtimes']
        actual = next(item['buildversion'] for item in runtimes if item['identifier'] == runtime)
        details = {'kind': 'ios-simulator', 'runtime_build': actual, 'runtime': runtime,
                   'model': entry['deviceTypeIdentifier']}
    if actual != runtime_build:
        raise ValueError(f'runtime build differs from pin: expected {runtime_build}, got {actual}')
    return details


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', choices=('ios', 'android'), required=True)
    parser.add_argument('--device', required=True)
    parser.add_argument('--runtime-build', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        args.out.write_text(json.dumps(attest(args.platform, args.device, args.runtime_build), indent=2) + '\n')
    except (ValueError, KeyError, StopIteration, subprocess.SubprocessError) as error:
        parser.exit(65, f'virtual admission refused: {error}\n')


if __name__ == '__main__':
    main()
