#!/usr/bin/env python3
"""CronJob entrypoint: emit exactly one content-free structured run summary."""

import json
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from omi_logging import configure_logging

configure_logging('record-seal-sweeper', default_format='json')


def main():
    # Suppress dependency diagnostics, including import-time errors containing IDs.
    logging.disable(logging.CRITICAL)
    report = {'event': 'record_seal_sweep', 'outcome': 'error'}
    try:
        from utils.batch_pipeline.record_seal_sweeper import run

        report = run()
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
