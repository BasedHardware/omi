"""Client classification and the extra hot-loop ceiling for GET /v1/action-items.

Context
-------
``GET /v1/action-items`` was 65.6% of all backend requests and 48.8% of every
billable Firestore document read (~$328/day) because ~82 stale ``omi-windows``
Electron binaries issued a ``completed=false`` + ``completed=true`` pair every
~1.2 seconds. #12258 made the ``action_items:list`` policy immune to
``RATE_LIMIT_BOOST`` and restored its 12/min per-uid cap, which removed ~90% of
that volume. A fixed-window prod capture on 2026-09-02 shows the route at
3.0 req/s with 11.7% 429s and **90% of the surviving traffic still coming from
``omi-windows/1.0.0`` asking for ``limit=500``** — the pre-fix build, two weeks
after its fix merged. That fleet is not updating on any schedule we can observe.

What this adds
--------------
A **second** ceiling that composes with the first rather than replacing it.
Every caller keeps the 12/min ``action_items:list`` bucket, checked in the auth
dependency before this runs. A caller additionally classified as the hot-loop
build is charged a second, independent Redis bucket
(``action_items:list_hot_client``, default 4/min) and is refused with 429 +
``Retry-After`` above it. Two buckets, two keys, no shared state: the tighter one
binds for a stale poller and nothing changes for anyone else.

Classification is deliberately narrow. Only the exact stale product build string
is treated as hot; an unrecognised or absent user agent is *not*, because a
misclassification here degrades a real client, and the 12/min policy already
covers the general case.

Rollback: ``ACTION_ITEMS_LIST_HOT_CLIENT_MAX=0`` disables the extra ceiling
without a code deploy.
"""

from __future__ import annotations

import re
from typing import Optional

import redis as redis_pkg
from fastapi import HTTPException, Request

from database.redis_db import check_rate_limit
from utils.metrics import record_action_items_list_throttled
from utils.rate_limit_config import ACTION_ITEMS_LIST_HOT_CLIENT_MAX, get_effective_limit

HOT_CLIENT_POLICY = "action_items:list_hot_client"

# The known hot-loop build. `omi-windows/1.0.0` is what the pre-fix Electron main
# process reports (repo package.json is already at 1.0.35, so the shipped
# binaries producing this string are the ones whose sync engine predates
# 65249902cb). Anchored on the product token so an unrelated UA containing the
# word "windows" is never classified.
_STALE_WINDOWS_UA = re.compile(r"\bomi-windows/1\.0\.0\b")


def classify_list_client(user_agent: Optional[str]) -> str:
    """Return a low-cardinality client class for metrics and the hot ceiling.

    Values: ``stale_windows`` (the known hot-loop build), ``windows`` (any other
    omi-windows build), ``other``. Kept to a closed set — this label goes on a
    Prometheus counter.
    """
    ua = user_agent or ""
    if _STALE_WINDOWS_UA.search(ua):
        return "stale_windows"
    if "omi-windows/" in ua:
        return "windows"
    return "other"


def is_hot_loop_client(client_class: str) -> bool:
    return client_class == "stale_windows"


def enforce_hot_client_list_ceiling(uid: str, request: Optional[Request]) -> None:
    """Charge the second ceiling for a hot-loop client; raise 429 when exceeded.

    Runs *before* any Firestore work, so a refused poll costs zero document
    reads. Fail-open on Redis errors, matching the first-party rate-limit
    contract in ``utils.other.endpoints._enforce_rate_limit``: a Redis outage
    must not take the list endpoint down.
    """
    if ACTION_ITEMS_LIST_HOT_CLIENT_MAX <= 0 or request is None:
        return
    client_class = classify_list_client(request.headers.get("user-agent"))
    if not is_hot_loop_client(client_class):
        return

    max_requests, window = get_effective_limit(HOT_CLIENT_POLICY)
    if max_requests <= 0:
        return
    try:
        allowed, _remaining, retry_after = check_rate_limit(
            f"{uid}:{client_class}", HOT_CLIENT_POLICY, max_requests, window
        )
    except redis_pkg.exceptions.RedisError:  # type: ignore[attr-defined]
        # Fail-open, exactly like the parent policy: the 12/min bucket already
        # bounds this route, and a Redis outage must not 503 a read path.
        return
    if allowed:
        return

    record_action_items_list_throttled(client=client_class, policy=HOT_CLIENT_POLICY)
    raise HTTPException(
        status_code=429,
        detail=f"Rate limit exceeded. Try again in {retry_after}s.",
        headers={
            "X-RateLimit-Limit": str(max_requests),
            "X-RateLimit-Remaining": "0",
            "Retry-After": str(max(1, retry_after)),
        },
    )
