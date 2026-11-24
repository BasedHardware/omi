"""Network guard surrounds collection as well as every fixture and test."""

import argparse
import os
from pathlib import Path
import sys

import pytest

from testing.lifecycle_sim.preflight import preflight
from testing.hermetic_network import block_outbound_network


def extra_test_module_path(value):
    backend = Path(__file__).resolve().parents[2]
    path = (backend / value).resolve()
    if not path.is_relative_to(backend / 'testing') or path.suffix != '.py' or not path.is_file():
        raise argparse.ArgumentTypeError('extra test module must be an existing Python file under backend/testing')
    return str(path)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--extra-test-module', action='append', type=extra_test_module_path, default=[])
    args, pytest_args = parser.parse_known_args(sys.argv[1:] if argv is None else argv)
    preflight(Path(os.environ['LIFECYCLE_SIM_STATE_DIR']))
    with block_outbound_network():
        return pytest.main(
            [
                '-p',
                'asyncio',
                '-v',
                '--tb=short',
                '--junitxml',
                str(Path(os.environ['LIFECYCLE_SIM_STATE_DIR']) / 'results.xml'),
                str(Path(__file__).with_name('test_scenarios.py')),
                *args.extra_test_module,
                *pytest_args,
            ]
        )


if __name__ == '__main__':
    raise SystemExit(main())
