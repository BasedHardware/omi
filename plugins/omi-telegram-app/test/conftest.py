"""Shared pytest fixtures for the Telegram plugin tests.

The bearer-auth gate (see plugins/_shared/auth.py) requires either
`Authorization: Bearer <AI_CLONE_PLUGIN_TOKEN>` or `OMI_DEV_MODE=1`.
The auth-gate tests live in `test_setup_auth.py` and
`test_toggle_schema_contract.py` — they override this default and
exercise the 401 / 403 / 503 paths.

For every OTHER test, defaulting to `OMI_DEV_MODE=1` keeps the
existing test code working without each test having to thread a
bearer header through every `TestClient.post(...)` call.
Production deploys are expected to set `AI_CLONE_PLUGIN_TOKEN`.
"""

import os

# Default to dev mode for the test suite. Auth tests explicitly
# delenv() this to exercise the auth gate.
os.environ.setdefault("OMI_DEV_MODE", "1")
