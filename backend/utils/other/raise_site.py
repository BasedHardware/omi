"""Name the raise site of an HTTP 503 without changing its response.

A 503 that reaches the client with no app log line is unattributable: the
response body is not in Cloud Logging and several sites share the status. Each
site tags its exception here; the route-level hook reads the tag and emits one
WARNING line. The tag is an attribute on the exception object, so it survives
the threadpool hop a synchronous dependency makes.

Nothing here reads or writes request state, and nothing here logs: the tag is
metadata only, and the caller's response is byte-identical to before.
"""

from __future__ import annotations

import json
from typing import Any

RAISE_SITE_ATTRIBUTE = 'omi_raise_site'
UNATTRIBUTED_RAISE_SITE = 'unattributed'


def tag_raise_site(exc: Any, site: str) -> Any:
    """Return *exc* carrying *site*; callers raise the returned object."""
    try:
        setattr(exc, RAISE_SITE_ATTRIBUTE, site)
    except AttributeError:  # pragma: no cover - every HTTPException accepts attributes
        pass
    return exc


def raise_site_of(exc: Any) -> str:
    """The tagged site, or ``unattributed`` when the raise site is not enumerated."""
    site = getattr(exc, RAISE_SITE_ATTRIBUTE, None)
    return site if isinstance(site, str) and site else UNATTRIBUTED_RAISE_SITE


def serialized_detail_bytes(detail: Any) -> int:
    """Byte length of the JSON body FastAPI's default handler would send.

    Mirrors ``JSONResponse.render`` (``ensure_ascii=False``, no indent, ``(',',
    ':')`` separators) so the logged length is the one Cloud Logging reports as
    ``responseSize``. Returns ``-1`` when the detail cannot be serialized, which
    is itself the signal that the body is not a plain ``{"detail": ...}``.
    """
    try:
        return len(
            json.dumps({'detail': detail}, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
        )
    except (TypeError, ValueError):
        return -1
