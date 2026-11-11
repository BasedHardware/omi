"""Public share-link base URL for self-hosting (#4339).

Default production host remains ``https://h.omi.me``. Override with
``OMI_SHARE_BASE_URL`` (scheme + host, optional path prefix, no trailing slash).
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit

DEFAULT_SHARE_BASE_URL = 'https://h.omi.me'
_ENV_KEY = 'OMI_SHARE_BASE_URL'


def share_base_url() -> str:
    """Return the configured share origin (no trailing slash)."""
    raw = (os.getenv(_ENV_KEY) or DEFAULT_SHARE_BASE_URL).strip()
    if not raw:
        raw = DEFAULT_SHARE_BASE_URL
    if '://' not in raw:
        raw = f'https://{raw}'
    return raw.rstrip('/')


def share_host() -> str:
    """Hostname used when minting share URLs (lowercase netloc without userinfo)."""
    parsed = urlsplit(share_base_url())
    return (parsed.hostname or 'h.omi.me').lower()


def accepted_share_hosts() -> frozenset[str]:
    """Hosts accepted when parsing inbound share URLs.

    Always includes the production default so existing ``h.omi.me`` links keep
    resolving even when ``OMI_SHARE_BASE_URL`` is customized.
    """
    hosts = {share_host(), 'h.omi.me'}
    return frozenset(hosts)


def build_share_url(path: str) -> str:
    """Join ``share_base_url()`` with a path that starts with ``/``."""
    if not path.startswith('/'):
        path = f'/{path}'
    return f'{share_base_url()}{path}'
