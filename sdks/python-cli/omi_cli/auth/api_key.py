"""Developer API key auth flow.

Usage:

* User generates a key in the Omi web app under Developer → API Keys, choosing
  the scopes the CLI should be allowed to exercise.
* User runs ``omi auth login`` and pastes the key. We validate the prefix
  client-side, then issue one round-trip to the API to confirm the key actually
  works (and to surface scope info in ``omi auth status``).

The actual *server-side* validation happens on the first authenticated call —
we don't need a special "check token" endpoint because the dev keys are stateless
bearer tokens.
"""

from __future__ import annotations

from omi_cli.auth.store import store_api_key
from omi_cli.config import Profile
from omi_cli.errors import UsageError

# Dev API keys are issued with this prefix by the backend (see
# ``backend/database/dev_api_key.py``). Validating the prefix client-side gives
# users a fast, helpful error when they paste the wrong kind of token (e.g. a
# Firebase ID token or an MCP key, ``omi_mcp_*``).
DEV_API_KEY_PREFIX = "omi_dev_"


def validate_api_key_format(api_key: str) -> str:
    """Return the trimmed key if the format looks plausible. Raise UsageError otherwise."""
    if api_key is None:
        raise UsageError(message="No API key provided")

    cleaned = api_key.strip()
    if not cleaned:
        raise UsageError(message="API key cannot be empty")

    if not cleaned.startswith(DEV_API_KEY_PREFIX):
        raise UsageError(
            message="That doesn't look like an Omi developer key",
            detail=(
                f"Expected a token starting with '{DEV_API_KEY_PREFIX}'. "
                "Generate one in the Omi web app under Developer → API Keys."
            ),
        )

    if len(cleaned) < len(DEV_API_KEY_PREFIX) + 16:
        raise UsageError(
            message="API key looks too short",
            detail="Real dev keys are at least ~24 characters. Check that you pasted the whole token.",
        )

    return cleaned


def login_with_api_key(profile_name: str, api_key: str, *, api_base: str | None = None) -> Profile:
    """Validate and persist a dev API key. Returns the updated profile."""
    cleaned = validate_api_key_format(api_key)
    return store_api_key(profile_name, cleaned, api_base=api_base)
