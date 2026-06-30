"""Shared bearer-token authentication for AI Clone plugin endpoints.

The desktop client (`AICloneClient`) sends `Authorization: Bearer <token>` on
every authenticated request to the plugin service, where `<token>` matches
the user's `AI_CLONE_PLUGIN_TOKEN` env var. This module exposes the
FastAPI dependency that enforces that contract on the plugin side.

## Why this exists

Identified by maintainer review on PR #8528 (security blocker): the desktop
UI tells users the bearer token protects plugin requests, but neither
`plugins/omi-telegram-app/main.py` nor `plugins/omi-whatsapp-app/main.py`
was actually verifying it on `/setup`. For a self-hosted plugin with a
public URL (ngrok / Cloudflare Tunnel), that left the setup surface
unauthenticated — anyone with the URL could:

  * cause the plugin to call Telegram's setWebhook / Meta's subscribed_apps
    (SSRF / phishing / spending the user's Meta quota)
  * persist arbitrary user-supplied credentials in plugin storage

The fix is a shared dependency that both plugins apply to sensitive
endpoints. `/health` and `/.well-known/omi-tools.json` stay public
(liveness probe + discovery).

## Auth policy

Behavior depends on two env vars:
- `AI_CLONE_PLUGIN_TOKEN` (required in production): the expected bearer.
- `OMI_DEV_MODE=1`: explicit opt-in to run without bearer verification
  (matches the existing WhatsApp-webhook `OMI_DEV_MODE` pattern).

Policy matrix:
  | AI_CLONE_PLUGIN_TOKEN | OMI_DEV_MODE | Outcome                              |
  |-----------------------|--------------|--------------------------------------|
  | set                   | (any)        | bearer must match (secrets.compare)  |
  | unset                 | 1            | allow all (dev only — explicit)      |
  | unset                 | unset        | 503 Service Unavailable (misconfig)  |

Returning 503 for the misconfig case (rather than silently allowing all)
ensures a deploy that forgot to set the token fails closed rather than
open.

## Constant-time comparison

`secrets.compare_digest` is used for the equality check. A naive `==`
comparison is timing-leaky: the time to compare grows with the longest
matching prefix, so an attacker can probe the token byte-by-byte. For a
local-network self-hosted plugin this is low-risk, but the right default
is free, so we use it.
"""

from __future__ import annotations

import os
import secrets
from typing import Optional

from fastapi import Header, HTTPException

# Env var name. Documented in plugins/_shared/auth.py's docstring above
# and referenced from the desktop side in
# desktop/macos/Desktop/Sources/AIClone/AICloneClient.swift (search for
# "AI_CLONE_PLUGIN_TOKEN").
_TOKEN_ENV_VAR = "AI_CLONE_PLUGIN_TOKEN"
_DEV_MODE_ENV_VAR = "OMI_DEV_MODE"


def get_plugin_token() -> str:
    """Return the configured plugin token, or "" if unset/blank.

    Whitespace-only tokens are treated as unset — a token of spaces
    would otherwise be "configured" but accept `Bearer    ` as valid.
    Identified by maintainer review on PR #8528.
    """
    raw = os.getenv(_TOKEN_ENV_VAR, "")
    return raw.strip()


def _is_dev_mode() -> bool:
    return os.getenv(_DEV_MODE_ENV_VAR) == "1"


async def require_bearer(
    authorization: Optional[str] = Header(default=None),
) -> None:
    """FastAPI dependency: reject the request unless the bearer matches.

    Apply via `dependencies=[Depends(require_bearer)]` on routes that
    must only be reachable from the configured desktop. See the policy
    matrix for the exact rules; in short:

    - production deploys (no OMI_DEV_MODE, token set) require a
      matching bearer,
    - dev installs (OMI_DEV_MODE=1, token unset) allow all,
    - misconfigured production (no OMI_DEV_MODE, token unset) returns
      503 so the failure is loud.

    Responses are deliberately identical for missing header, wrong
    scheme, and wrong token — all return 401 with the same body. An
    attacker probing the endpoint shouldn't be able to distinguish
    "no header sent" from "wrong token" via the response shape; both
    are equally "your request is unauthenticated".
    """
    expected = get_plugin_token()

    if not expected:
        # Token not configured. If we're in explicit dev mode, allow all.
        # Otherwise fail closed with 503 — a forgotten env var should be
        # loud, not silently permissive.
        if _is_dev_mode():
            return
        raise HTTPException(
            status_code=503,
            detail="Plugin bearer token not configured on the server",
        )

    # Same response (status + body) for missing header, wrong scheme,
    # and wrong token. An attacker probing the endpoint shouldn't be
    # able to tell these apart.
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Invalid bearer token",
        )

    presented = authorization[len("Bearer ") :]

    # Identified by cubic (P1): secrets.compare_digest raises TypeError on
    # non-ASCII input, which would surface as an unhandled 500 — leaking
    # that the comparison happened at all and breaking the
    # "uniform 401 for any unauthenticated caller" invariant.
    # FastAPI turns an unhandled exception into 500 (the framework's
    # default exception handler), so without this guard a non-ASCII
    # token / header pair is observably different from a missing or
    # wrong one — an attacker can probe ASCII handling vs. the 500 path.
    # We bail out with the same 401 before calling compare_digest.
    try:
        presented.encode("ascii")
        expected.encode("ascii")
    except UnicodeEncodeError:
        raise HTTPException(
            status_code=401,
            detail="Invalid bearer token",
        ) from None

    if not secrets.compare_digest(presented, expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid bearer token",
        )
