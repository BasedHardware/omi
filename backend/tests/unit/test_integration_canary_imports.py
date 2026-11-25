"""Workflow tooling must import in the minimal runner without cloud SDKs."""

from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('module', ['integration_canary_controller', 'runtime_env_canary_ops'])
def test_canary_consumer_imports_without_site_packages(module):
    backend = Path(__file__).resolve().parents[2]
    subprocess.run(
        [
            sys.executable,
            '-I',
            '-S',
            '-c',
            'import importlib, sys; sys.path.insert(0, sys.argv[1]); importlib.import_module(sys.argv[2])',
            str(backend),
            'scripts.' + module,
        ],
        check=True,
        timeout=10,
        capture_output=True,
        text=True,
    )
