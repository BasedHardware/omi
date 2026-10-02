"""Content-free validation of a developer credential, with older-backend fallback."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from omi_cli.errors import NotFoundError, PermissionDeniedError

if TYPE_CHECKING:
    from omi_cli.client import OmiClient


def verify_key(client: OmiClient) -> tuple[Optional[list[str]], Optional[str]]:
    """Check credential metadata, probing content only on an older backend."""
    try:
        credential = client.get("/v1/dev/key")
        return credential["scopes"], None
    except NotFoundError:
        try:
            client.get("/v1/dev/user/memories", params={"limit": 1})
        except PermissionDeniedError:
            return None, (
                "Key is valid, but memory access is limited by scopes or account readiness. "
                "This backend cannot report the key's scopes."
            )
        return None, None
