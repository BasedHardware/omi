#!/usr/bin/env python3
"""Private dependency output stays suppressed for the CPU seal worker lifetime."""

from pathlib import Path
import json
import logging
import os
import signal
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from omi_logging import configure_logging

configure_logging('record-seal-worker', default_format='json')

from utils.batch_pipeline.record_seal_cluster_repair import silent_dependencies
from utils.batch_pipeline.record_seal_worker import run


def emit(payload):
    logger = logging.getLogger('record-seal-worker')
    record = logger.makeRecord(logger.name, logging.ERROR, '', 0, json.dumps(payload), (), None)
    logger.handle(record)


def main():
    def terminate(*_):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, terminate)
    # Keep one explicit aggregate output fd while silencing private SDK output.
    with os.fdopen(os.dup(1), 'w') as output:
        configure_logging('record-seal-worker', default_format='json', stdout=output, stderr=output)
        with silent_dependencies():
            run(os.environ['BATCH_PIPELINE_WORKER_RELEASE'], os.environ['POD_NAMESPACE'], emit=emit)


if __name__ == '__main__':
    main()
