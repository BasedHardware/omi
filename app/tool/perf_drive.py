#!/usr/bin/env python3
"""Bound one Flutter driver launch to 14 minutes, including startup/transport."""
import os
from pathlib import Path
import signal
import subprocess
import sys


def validate_command(command):
    if len(command) < 2 or Path(command[0]).name != 'flutter' or command[1] != 'drive':
        raise ValueError('this runner only permits a Flutter drive command')
    if ('--keep-app-running' not in command
            or any(arg.startswith('--no-keep-app-running') or arg.startswith('--keep-app-running=')
                   or arg.startswith('--uninstall') for arg in command)):
        raise ValueError('refusing Flutter drive cleanup: explicit --keep-app-running is mandatory; uninstall is forbidden')
    if any(arg.startswith('--disable-service-auth-codes') for arg in command):
        raise ValueError('VM service authentication must remain enabled')
    flavors = []
    for index, arg in enumerate(command):
        if arg == '--flavor':
            flavors.append(command[index + 1] if index + 1 < len(command) else '')
        elif arg.startswith('--flavor='):
            flavors.append(arg.split('=', 1)[1])
    if flavors != ['dev']:
        raise ValueError('exactly one DEV flavor is required')
    return command


def stop(process):
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def main():
    try:
        command = validate_command(sys.argv[2:])
    except ValueError as error:
        print(f'UNSAFE_DRIVER_COMMAND: {error}', file=sys.stderr)
        return 64
    log = Path(sys.argv[1])
    with log.open('w') as stream:
        process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        def interrupted(signum, frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, interrupted)
        try:
            return process.wait(timeout=14 * 60)
        except subprocess.TimeoutExpired:
            stop(process)
            print(f'profile driver exceeded 14-minute limit; see {log}', file=sys.stderr)
            return 124
        except BaseException:
            stop(process)
            raise


if __name__ == '__main__':
    raise SystemExit(main())
