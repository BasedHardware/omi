#!/usr/bin/env python3
"""Retain launch load samples; a load1/CPU ratio above 1 invalidates the batch."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time

POLICY = 'load1-per-logical-cpu<=1/v1'


def sample(phase):
    loads = os.getloadavg()
    cpus = os.cpu_count()
    return {'phase': phase, 'monotonic_ns': time.monotonic_ns(),
            'load_1_5_15m': list(loads), 'logical_cpus': cpus,
            'admitted': cpus is not None and cpus > 0 and loads[0] <= cpus}


def run(command, out):
    samples = [sample('before')]
    code = None
    if samples[0]['admitted']:
        child = subprocess.Popen(command)
        previous = signal.getsignal(signal.SIGTERM)
        def interrupted(signum, frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, interrupted)
        try:
            while True:
                try:
                    code = child.wait(timeout=1)
                    break
                except subprocess.TimeoutExpired:
                    samples.append(sample('during'))
        except BaseException:
            # perf_drive owns its Flutter process group and collects it on TERM.
            child.terminate()
            child.wait()
            raise
        finally:
            signal.signal(signal.SIGTERM, previous)
            samples.append(sample('after'))
    passed = all(item['admitted'] for item in samples)
    out.write_text(json.dumps({'policy': POLICY, 'passed': passed,
                               'command_exit_code': code, 'samples': samples}, indent=2) + '\n')
    if not passed:
        print('Host overload: entire batch invalid; launch evidence retained, no retry.', flush=True)
        return 65
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('a launch command is required')
    return run(command, args.out)


if __name__ == '__main__':
    raise SystemExit(main())
