"""Re-export of the shared persona_client.

This file exists so the plugin's main.py can `from persona_client import chat`
without managing sys.path. The actual implementation lives in
plugins/_shared/persona_client.py and is imported via the path inserted by
main.py on startup.
"""

# The shared module is added to sys.path by main.py before this file is
# imported. This re-export makes the import site in main.py obvious
# (`from persona_client import chat`) while keeping the source of truth
# in plugins/_shared/.
from persona_client import chat  # noqa: F401  (re-export)
