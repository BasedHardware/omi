"""Shared pytest hooks for the whole backend test tree."""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from testing.hermetic_network import block_outbound_network

_network_guard = None


def pytest_sessionstart(session):
    global _network_guard
    _network_guard = block_outbound_network()
    _network_guard.__enter__()


def pytest_sessionfinish(session, exitstatus):
    global _network_guard
    if _network_guard is not None:
        _network_guard.__exit__(None, None, None)
        _network_guard = None
