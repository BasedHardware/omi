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


def emit_progress(payload):
    # Keep all dependency logging suppressed. Only our allowlisted aggregate
    # payload bypasses the global disable switch; restore it even on log errors.
    logging.disable(logging.NOTSET)
    try:
        logging.getLogger('record-seal-sweeper').info(json.dumps(payload, sort_keys=True, allow_nan=False))
    finally:
        logging.disable(logging.CRITICAL)


def main():
    # Suppress dependency diagnostics, including import-time errors containing IDs.
    logging.disable(logging.CRITICAL)
    report = {'event': 'record_seal_sweep', 'outcome': 'error'}
    try:
        if record_seal_sweeper is not None:
            report = record_seal_sweeper.run(progress=emit_progress)
    except Exception:
        pass
    logging.disable(logging.NOTSET)
    failed = report['outcome'] not in {'ok', 'disabled'}
    logging.getLogger('record-seal-sweeper').log(
        logging.ERROR if failed else logging.INFO, json.dumps(report, sort_keys=True, allow_nan=False)
    )
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
