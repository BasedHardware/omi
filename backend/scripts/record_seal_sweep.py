#!/usr/bin/env python3
"""CronJob entrypoint: content-free phase progress and one final run summary."""

import json
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from omi_logging import configure_logging

configure_logging('record-seal-sweeper', default_format='json')

# Imports stay at module scope; bootstrap diagnostics must not expose paths or
# identifiers before the content-free error summary can be emitted.
logging.disable(logging.CRITICAL)
try:
    from utils.batch_pipeline import record_seal_sweeper
except Exception:
    record_seal_sweeper = None


def emit(payload, level):
    # Send only our aggregate record through the configured JSON handler.
    # Never open a global logging window for concurrent SDK diagnostics.
    logger = logging.getLogger('record-seal-sweeper')
    record = logger.makeRecord(
        logger.name, level, '', 0, json.dumps(payload, sort_keys=True, allow_nan=False), (), None
    )
    logger.handle(record)


def emit_progress(payload):
    emit(payload, logging.INFO)


def main():
    # Suppress dependency diagnostics, including import-time errors containing IDs.
    logging.disable(logging.CRITICAL)
    report = {'event': 'record_seal_sweep', 'outcome': 'error'}
    try:
        if record_seal_sweeper is not None:
            report = record_seal_sweeper.run(progress=emit_progress)
    except Exception:
        pass
    failed = report['outcome'] not in {'ok', 'disabled'}
    emit(report, logging.ERROR if failed else logging.INFO)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
