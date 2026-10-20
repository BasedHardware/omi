"""Hermetic process defaults applied before any product module is imported.

Product modules validate these at import time. The values are synthetic test
constants (the same ones ``tests/conftest.py`` uses); they never reach a
provider because every provider call in the simulation is a fake.
"""

import os

# Synthetic test constants shared with tests/conftest.py, not credentials.
_TEST_ENCRYPTION_SECRET = (
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv'  # pragma: allowlist secret
)
os.environ.setdefault('ENCRYPTION_SECRET', _TEST_ENCRYPTION_SECRET)
os.environ.setdefault('OPENAI_API_KEY', 'fake-key-for-hermetic-simulation')  # pragma: allowlist secret
