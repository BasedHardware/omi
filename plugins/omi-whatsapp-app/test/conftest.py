"""Shared pytest fixtures for the WhatsApp plugin tests.

Centralizes the sys.path setup so each test file can `import main` and
`import simple_storage` regardless of where pytest is invoked from.

P1.1 fix: WHATSAPP_APP_SECRET must be set or OMI_DEV_MODE=1 to allow the module
to load. Default to dev mode here so the standard test command works without
extra env vars. Tests that specifically exercise signature verification set
WHATSAPP_APP_SECRET explicitly via monkeypatch.

Note: we do NOT add backend/ to sys.path — that would cause `main` to resolve
to backend/main.py (which imports firebase_admin at module load).
"""

import os
import sys

# Default to dev mode for the test suite.
os.environ.setdefault("OMI_DEV_MODE", "1")

# Put _SHARED FIRST so `import persona_client` resolves to the shared module
# (not this plugin's re-export, which would self-import). _PLUGIN_ROOT second
# so `import simple_storage` resolves to our local copy when main.py does it.
_HERE = os.path.dirname(os.path.abspath(__file__))
_SHARED = os.path.abspath(os.path.join(_HERE, "..", "..", "_shared"))
_PLUGIN_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
for p in (_SHARED, _PLUGIN_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)
