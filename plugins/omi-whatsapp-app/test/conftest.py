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


def load_main_module():
    """Load WhatsApp's main.py and return the loaded module.

    Used by test_whatsapp_setup_auth.py and any other test that needs
    to mount the WhatsApp FastAPI app without colliding with Telegram's
    bare-name `main` module. The loaded module is cached so the second
    call is a dict lookup.

    For the desktop branch (this branch), the test suite doesn't run
    alongside Telegram's in a single pytest invocation, so the sys.modules
    swap dance that chat-tools uses isn't needed. A plain importlib load
    of the local main.py works.
    """
    import importlib.util

    if "whatsapp_main" in sys.modules:
        return sys.modules["whatsapp_main"]
    spec = importlib.util.spec_from_file_location(
        "whatsapp_main", os.path.join(_PLUGIN_ROOT, "main.py")
    )
    if spec is None or spec.loader is None:
        raise ImportError("Could not load WhatsApp main.py spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules["whatsapp_main"] = module
    spec.loader.exec_module(module)
    return module
