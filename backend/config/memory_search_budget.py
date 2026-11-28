"""Rollback switch for the bounded product-memory search read.

``GET /memory/search`` and ``GET /memory/archive/search`` read the
authoritative ``users/{uid}/memory_items`` collection. Without a request
budget that read can outlive the edge request timeout (``HTTP_GET_TIMEOUT``,
30s in prod) and surface as a bare middleware 504 with no body (SCA-3795,
four occurrences: SCA-3797, SCA-4277, SCA-4823, SCA-5469).

The budget ships on: the route derives a monotonic deadline from the request
start and every Firestore RPC in the read gets a timeout inside it. Setting
``OMI_MEMORY_SEARCH_READ_BUDGET_ENABLED`` to ``0``/``false``/``off``/``no``
restores the previous unbounded read path on the next revision, so a rollout
that misfires rolls back without reverting code. It is a whole-route switch:
there is no per-request toggle, and it cannot be used to serve a partial page
as a successful search.
"""

import os
from collections.abc import Mapping

MEMORY_SEARCH_READ_BUDGET_ENABLED_ENV = "OMI_MEMORY_SEARCH_READ_BUDGET_ENABLED"

_DISABLED_TOKENS = frozenset({"0", "false", "off", "no"})


def memory_search_read_budget_enabled(env: Mapping[str, str] | None = None) -> bool:
    """True unless the kill switch is explicitly set to a disabled token."""
    source = env if env is not None else os.environ
    raw = source.get(MEMORY_SEARCH_READ_BUDGET_ENABLED_ENV)
    if raw is None:
        return True
    return str(raw).strip().lower() not in _DISABLED_TOKENS


__all__ = [
    "MEMORY_SEARCH_READ_BUDGET_ENABLED_ENV",
    "memory_search_read_budget_enabled",
]
