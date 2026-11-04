"""Network guard surrounds collection as well as every fixture and test."""

import os
from pathlib import Path
import sys

import pytest

from testing.lifecycle_sim.preflight import preflight
from testing.hermetic_network import block_outbound_network


def main():
    preflight(Path(os.environ['LIFECYCLE_SIM_STATE_DIR']))
    with block_outbound_network():
        return pytest.main(
            [
                '-p',
                'asyncio',
                '-v',
                '--tb=short',
                str(Path(__file__).with_name('test_scenarios.py')),
                *sys.argv[1:],
            ]
        )


if __name__ == '__main__':
    raise SystemExit(main())
