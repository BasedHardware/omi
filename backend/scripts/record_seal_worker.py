#!/usr/bin/env python3
"""Private dependency output stays suppressed for the CPU seal worker lifetime."""

from pathlib import Path
import signal
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from omi_logging import configure_logging

configure_logging('record-seal-worker', default_format='json')

from utils.batch_pipeline.record_seal_cluster_repair import silent_dependencies
from utils.batch_pipeline.record_seal_worker import run


def main():
    def terminate(*_):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, terminate)
    with silent_dependencies():
        run()


if __name__ == '__main__':
    main()
