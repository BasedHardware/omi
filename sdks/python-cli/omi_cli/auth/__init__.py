"""Authentication primitives for omi-cli.

Two flows are wired through this package:

* :mod:`omi_cli.auth.api_key` — paste-in dev API key (``omi_dev_*``). Primary
  flow for agents, CI, and any headless context. Long-lived, scoped.
* :mod:`omi_cli.auth.oauth` — Firebase OAuth browser flow. Spins up a
  localhost callback server, opens the browser, exchanges the resulting code
  for a Firebase ID token + refresh token. Best for humans on a laptop.

Common token persistence lives in :mod:`omi_cli.auth.store`.
"""

from omi_cli.auth.api_key import login_with_api_key, validate_api_key_format
from omi_cli.auth.oauth import login_with_browser, needs_refresh, refresh_id_token
from omi_cli.auth.store import clear_credentials

__all__ = [
    "clear_credentials",
    "login_with_api_key",
    "login_with_browser",
    "needs_refresh",
    "refresh_id_token",
    "validate_api_key_format",
]
