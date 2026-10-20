"""Deterministic local OIDC token format shared by the gauntlet.

The token embeds both the audience and the service-account identity so a token
minted for one route binding is rejected by every other binding, even when two
routes share the same service account.  Mint sites and the local verifier in
``app.py`` must both go through :func:`local_oidc_token`.
"""

from __future__ import annotations


def local_oidc_token(audience: str, identity: str) -> str:
    return f'local-sync-oidc:{audience}:{identity}'
