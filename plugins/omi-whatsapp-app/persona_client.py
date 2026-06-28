"""Re-export of the shared persona client.

Mechanical copy of plugins/omi-telegram-app/persona_client.py — both plugins
share the same persona API and the same auth model.
"""

from persona_client import chat  # noqa: F401  re-export

__all__ = ["chat"]
