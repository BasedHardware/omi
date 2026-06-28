"""Shared pytest fixtures for the WhatsApp plugin tests.

Centralizes the sys.path setup so each test file can `import main` and
`import simple_storage` regardless of where pytest is invoked from.

We do NOT add backend/ to sys.path — the shared persona_client is self-contained
(plugins/_shared/persona_client.py) and adding backend would cause `main` to
resolve to backend/main.py (which imports firebase_admin at module load).

P1.1 fix: WHATSAPP_APP_SECRET must be set or OMI_DEV_MODE=1 to allow the module
to load. Default to dev mode here so the standard test command works without
extra env vars. Tests that specifically exercise signature verification set
WHATSAPP_APP_SECRET explicitly via monkeypatch.
"""

import os
import sys

# Default to dev mode for the test suite. Tests that need real verification
# set WHATSAPP_APP_SECRET themselves.
os.environ.setdefault("OMI_DEV_MODE", "1")

# Put the plugin root on sys.path so `import main` and `import simple_storage`
# resolve correctly regardless of where pytest is invoked from. _SHARED must
# come BEFORE _PLUGIN_ROOT in sys.path so `import persona_client` resolves to
# the shared one (not this plugin's re-export, which would self-import).
_HERE = os.path.dirname(os.path.abspath(__file__))
_SHARED = os.path.abspath(os.path.join(_HERE, "..", "..", "_shared"))
_PLUGIN_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
for p in (_SHARED, _PLUGIN_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)
