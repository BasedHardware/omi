"""Shared pytest fixtures for the Telegram plugin tests.

The bearer-auth gate added in commit 5f1f710f9 / 08d00b9cb (security
fix for PR #8528) requires either an `Authorization: Bearer` header
matching `AI_CLONE_PLUGIN_TOKEN`, OR `OMI_DEV_MODE=1`. The auth-bypass
tests live in `test_setup_auth.py` and `test_toggle_auth.py` — they
override this default and exercise the 401 / 503 paths.

For every OTHER test, defaulting to `OMI_DEV_MODE=1` keeps the existing
test code working without each test having to thread a bearer header
through every `TestClient.post(...)` call. Production deploys are
expected to set `AI_CLONE_PLUGIN_TOKEN` (see `plugins/_shared/auth.py`);
test mode is a deliberate opt-out.

Tests that need real verification set `AI_CLONE_PLUGIN_TOKEN` explicitly
via monkeypatch and pass an `Authorization: Bearer ...` header.
"""

import os

# Default to dev mode for the test suite. test_setup_auth.py / future
# test_toggle_auth.py explicitly delenv() this to exercise the auth gate.
os.environ.setdefault("OMI_DEV_MODE", "1")
