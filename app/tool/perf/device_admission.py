#!/usr/bin/env python3
"""Refuse to install/launch over a running DEV app; never stop an unknown PID."""
import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess
from urllib.parse import unquote, urlparse

DEV = 'com.friend-app-with-wearable.ios12.development'


def file_path(value):
    if not isinstance(value, str):
        raise ValueError('missing executable/install URL; cannot prove DEV is idle')
    parsed = urlparse(value)
    if parsed.scheme != 'file' or parsed.netloc:
        raise ValueError('unexpected executable/install URL')
    path = PurePosixPath('/' + unquote(parsed.path).lstrip('/'))
    if '..' in path.parts:
        raise ValueError('unexpected executable/install path')
    return path


def idle_state(apps, processes):
    if not isinstance(apps, list) or len(apps) > 1:
        raise ValueError('ambiguous DEV installation metadata')
    if not apps:
        return {'bundle_id': DEV, 'installed': False, 'running_pids': [], 'extension_pids': []}
    app = apps[0]
    if not isinstance(app, dict) or app.get('bundleIdentifier') != DEV:
        raise ValueError('installation metadata is not the exact DEV bundle')
    root = file_path(app.get('url'))
    if root.suffix != '.app' or not isinstance(processes, list):
        raise ValueError('incomplete DEV process admission metadata')
    pids = []
    extensions = []
    for process in processes:
        if not isinstance(process, dict):
            raise ValueError('unclassified process metadata; cannot prove DEV is idle')
        executable = file_path(process.get('executable'))
        if executable == root or root in executable.parents:
            pid = process.get('processIdentifier')
            if type(pid) is not int or pid <= 0:
                raise ValueError('missing DEV PID; cannot prove DEV is idle')
            relative = executable.relative_to(root)
            if relative.parts == ('Runner',):
                pids.append(pid)
            elif (len(relative.parts) == 3 and relative.parts[0] == 'PlugIns'
                  and relative.parts[1].endswith('.appex')
                  and relative.parts[2] == relative.parts[1][:-len('.appex')]):
                # iOS may launch a widget after an in-place install. It is not
                # the main app: record it without blocking or terminating it.
                extensions.append(pid)
            else:
                raise ValueError('unclassified DEV executable; cannot prove main app is idle')
    return {'bundle_id': DEV, 'installed': True, 'running_pids': sorted(pids),
            'extension_pids': sorted(extensions)}


def query(device, kind, *options):
    command = ['xcrun', 'devicectl', 'device', 'info', kind, '--device', device,
               *options, '--timeout', '20', '--json-output', '-']
    result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=25)
    return json.loads(result.stdout)['result']


def android_state(device):
    result = subprocess.run(['adb', '-s', device, 'shell', 'pidof', 'com.friend.ios.dev'],
                            capture_output=True, text=True, timeout=20)
    words = result.stdout.split()
    if result.returncode == 1 and not words and not result.stderr.strip():
        return {'bundle_id': 'com.friend.ios.dev', 'running_pids': []}
    if result.returncode == 0 and words and all(word.isdigit() and int(word) > 0 for word in words):
        return {'bundle_id': 'com.friend.ios.dev', 'running_pids': sorted(map(int, words))}
    raise ValueError('unknown Android process state')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', required=True)
    parser.add_argument('--platform', choices=('ios', 'android'), default='ios')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        # Same CoreDevice JSON fields used by Flutter3.44.5 core_devices.dart.
        # Inspect app/process metadata only, never app-container contents.
        if args.platform == 'ios':
            apps = query(args.device, 'apps', '--bundle-id', DEV)['apps']
            processes = query(args.device, 'processes')['runningProcesses'] if apps else []
            state = idle_state(apps, processes)
        else:
            state = android_state(args.device)
        args.out.write_text(json.dumps(state, indent=2) + '\n')
        if state['running_pids']:
            parser.exit(65, 'DEV app is running. Stop: ask its owner to quiesce it; never force-stop capture.\n')
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        parser.exit(65, 'Cannot prove the DEV app is idle; no install/launch is permitted.\n')


if __name__ == '__main__':
    main()
