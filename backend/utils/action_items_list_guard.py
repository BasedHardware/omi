"""Client classification, hot-loop ceiling, and stale-build refusal for GET /v1/action-items.

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

An env-gated **refusal** sits in front of both the extra ceiling and any
Firestore work. When ``ACTION_ITEMS_LIST_STALE_CLIENT_REFUSE`` is on, the same
narrow classification returns 426 with a machine-readable upgrade body instead
of serving the list. A page cap was examined and rejected (2026-09-21): that
build ignores ``has_more`` and would silently truncate user-visible tasks.
Default is off (unset / ``0`` / ``off``) so classification can be confirmed
from the counter before the flag is flipped, and flipped back with no code
deploy.

Classification is deliberately narrow. Only the exact stale product build string
is treated as hot; an unrecognised or absent user agent is *not*, because a
misclassification here takes a working client's task list away, and that is the
one harm that is not instantly reversible from the user's side.

Rollback: ``ACTION_ITEMS_LIST_HOT_CLIENT_MAX=0`` disables the extra ceiling,
and ``ACTION_ITEMS_LIST_STALE_CLIENT_REFUSE=0`` (or unset / ``off``) disables
the refusal, both without a code deploy.
"""

from __future__ import annotations

import os
import re
from typing import Optional

import redis as redis_pkg
from fastapi import HTTPException, Request

from database.redis_db import check_rate_limit
from utils.metrics import record_action_items_list_refused, record_action_items_list_throttled
from utils.rate_limit_config import ACTION_ITEMS_LIST_HOT_CLIENT_MAX, get_effective_limit

HOT_CLIENT_POLICY = "action_items:list_hot_client"

# Same shape as ACTION_ITEMS_LIST_HOT_CLIENT_MAX: unset / 0 / off keeps current
# behaviour. Read at call time so a config flip does not need a new image.
STALE_CLIENT_REFUSE_ENV = "ACTION_ITEMS_LIST_STALE_CLIENT_REFUSE"
STALE_WINDOWS_MINIMUM_SUPPORTED_BUILD = "omi-windows/1.0.35"
STALE_CLIENT_REFUSE_ERROR = "upgrade_required"
STALE_CLIENT_REFUSE_MESSAGE = (
    "This Omi for Windows build is no longer supported for the task list. "
    "Update to a current Omi for Windows release to continue seeing your tasks."
)
_REFUSE_TRUTHY = frozenset({"1", "true", "yes", "on"})

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


def stale_client_refuse_enabled() -> bool:
    """True only for an explicit on-value. A typo must not refuse a working client."""
    raw = os.getenv(STALE_CLIENT_REFUSE_ENV)
    if raw is None:
        return False
    return raw.strip().casefold() in _REFUSE_TRUTHY


def stale_client_refuse_detail() -> dict[str, str]:
    return {
        "error": STALE_CLIENT_REFUSE_ERROR,
        "minimum_supported_build": STALE_WINDOWS_MINIMUM_SUPPORTED_BUILD,
        "message": STALE_CLIENT_REFUSE_MESSAGE,
    }


def enforce_stale_client_list_refusal(request: Optional[Request]) -> None:
    """Refuse GET /v1/action-items for the exact stale build when the env flag is on.

    Runs before the extra ceiling and before any Firestore work. Classification
    uses the same closed set as the hot-loop ceiling: only ``stale_windows``.
    Unknown, absent, or differently-versioned user agents are never refused.
    The counter is emitted on every classified match so the match set can be
    confirmed while the flag is still off (``decision=allow``) and after it
    flips (``decision=refuse``).
    """
    if request is None:
        return
    client_class = classify_list_client(request.headers.get("user-agent"))
    if not is_hot_loop_client(client_class):
        return

    enabled = stale_client_refuse_enabled()
    record_action_items_list_refused(
        client=client_class,
        decision="refuse" if enabled else "allow",
    )
    if not enabled:
        return
    raise HTTPException(status_code=426, detail=stale_client_refuse_detail())


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
