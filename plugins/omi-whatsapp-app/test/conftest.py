"""Shared pytest fixtures for the WhatsApp plugin tests.

Centralizes the sys.path setup so each test file can `import main` and
`import simple_storage` regardless of where pytest is invoked from.

We do NOT add backend/ to sys.path — the shared persona_client is self-contained
(plugins/_shared/persona_client.py) and adding backend would cause `main` to
resolve to backend/main.py (which imports firebase_admin at module load).
"""

import os
import sys

# Put the plugin root on sys.path so `import main` and `import simple_storage`
# resolve correctly regardless of where pytest is invoked from.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)
