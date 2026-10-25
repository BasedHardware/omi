#!/usr/bin/env python3
"""Bound one Flutter driver launch to 14 minutes, including startup/transport."""
import os
from pathlib import Path
import signal
import subprocess
import sys


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
    log = Path(sys.argv[1])
    with log.open('w') as stream:
        process = subprocess.Popen(sys.argv[2:], stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
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
