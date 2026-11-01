#!/usr/bin/env python3
"""Counts-only entrypoint for the isolated repair CronJob and its row children."""

import json
import logging
import os
from pathlib import Path
import signal
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from omi_logging import configure_logging

configure_logging('record-seal-repair', default_format='json')

from utils.batch_pipeline import record_seal_cluster_repair as repair


def emit(payload):
    logger = logging.getLogger('record-seal-repair')
    level = logging.ERROR if payload.get('outcome') == 'error' else logging.INFO
    record = logger.makeRecord(
        logger.name, level, '', 0, json.dumps(payload, sort_keys=True, allow_nan=False), (), None
    )
    logger.handle(record)


def main():
    def terminate(*_):
        # Unwind the coordinator's finally block and reap all children.
        raise SystemExit(1)

    signal.signal(signal.SIGTERM, terminate)
    # Keep only our aggregate handler/IPC on an explicit output fd. Suppress
    # native diagnostics for the whole lifetime, including SDK background threads.
    with os.fdopen(os.dup(1), 'w') as output:
        configure_logging('record-seal-repair', default_format='json', stdout=output, stderr=output)
        with repair.silent_dependencies():
            try:
                if sys.argv[1:] == ['--row']:
                    payload = json.loads(sys.stdin.buffer.read(8193))
                    output.write(json.dumps(repair.row_main(payload)) + '\n')  # Private child IPC, closed outcome only.
                    output.flush()
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
