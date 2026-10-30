#!/usr/bin/env python3
"""Counts-only entrypoint for the isolated repair CronJob and its row children."""

import json
from pathlib import Path
import signal
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.batch_pipeline import record_seal_cluster_repair as repair


def emit(payload):
    print(json.dumps(payload, sort_keys=True, allow_nan=False), flush=True)


def main():
    def terminate(*_):
        # Unwind the coordinator's finally block and reap all children.
        raise SystemExit(1)

    signal.signal(signal.SIGTERM, terminate)
    try:
        if sys.argv[1:] == ['--row']:
            payload = json.loads(sys.stdin.buffer.read(8193))
            emit(repair.row_main(payload))
        elif not sys.argv[1:]:
            emit(repair.run(progress=emit))
        else:
            raise ValueError('invalid arguments')
    except BaseException:
        emit({'event': 'record_seal_repair', 'outcome': 'error'})
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
