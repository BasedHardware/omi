"""Best-effort request-owner attribution; never an entitlement authority.

Only subscriptions already read by business code warm this local projection.
There is no cache loader and no I/O on either the request or probe path.
"""

import math
import threading
import time
from collections import OrderedDict
from contextvars import ContextVar
from dataclasses import dataclass
from enum import Enum
from typing import Any

from config.plan_catalog import PLAN_TYPE_VALUES, WIRE_PLAN_ALIASES

TIER_VALUES = PLAN_TYPE_VALUES | frozenset(WIRE_PLAN_ALIASES) | {'unattributed', 'other'}
_TTL_SECONDS = 60
_MAX_ENTRIES = 4096
_cache: OrderedDict[str, tuple[str, float]] = OrderedDict()
_cache_lock = threading.Lock()


def bounded_tier(value: Any) -> str:
    if isinstance(value, Enum):
        value = value.value
    if value is None:
        return 'unattributed'
    return value if type(value) is str and value in TIER_VALUES else 'other'


@dataclass
class _RequestOwner:
    uid: str | None = None  # Internal ownership guard only; never exported or logged.
    tier: str = 'unattributed'
    expires_at: float = 0
    closed: bool = False


# A fresh holder per ASGI invocation lets sync auth deps publish into the async
# handler's copied context. Never use a mutable ContextVar default.
_request_owner: ContextVar[_RequestOwner | None] = ContextVar('firestore_request_owner', default=None)


def bind_request_owner(uid: str) -> None:
    """Called only after authentication. A cold/contended cache adds no read."""
    try:
        owner = _request_owner.get()
        if owner is None or owner.closed:
            return
        if owner.uid is not None:
            if owner.uid != uid:
                owner.closed = True  # Ambiguous ownership must never look like basic.
            return
        owner.uid = uid
        if not _cache_lock.acquire(blocking=False):
            return
        try:
            entry = _cache.get(uid)
            if entry is not None and entry[1] > time.monotonic():
                owner.tier, owner.expires_at = entry
                _cache.move_to_end(uid)
        finally:
            _cache_lock.release()
    except Exception:
        # An instrumentation fault cannot change authentication or run a loader.
        return


def observe_subscription(uid: str, subscription: Any) -> None:
    """Project an already-read stored subscription, never a synthesized default.

    Mirror the existing validity boundary conservatively: active stored basic,
    or paid through period end (including pending cancellation). Missing/expired
    paid state stays unattributed instead of manufacturing a basic observation.
    """
    try:
        tier = 'unattributed'
        lifetime = _TTL_SECONDS
        if subscription is not None:
            candidate = bounded_tier(subscription.plan)
            if candidate == 'other':
                tier = candidate
            elif candidate == 'basic':
                if subscription.status == 'active':
                    tier = candidate
            elif subscription.current_period_end:
                remaining = float(subscription.current_period_end) - time.time()
                if math.isfinite(remaining) and remaining > 0:
                    tier = candidate
                    lifetime = min(lifetime, remaining)
        entry = (tier, time.monotonic() + lifetime)
        owner = _request_owner.get()
        if owner is not None and not owner.closed and owner.uid == uid:
            owner.tier, owner.expires_at = entry
        if not _cache_lock.acquire(blocking=False):
            return
        try:
            _cache[uid] = entry
            _cache.move_to_end(uid)
            if len(_cache) > _MAX_ENTRIES:
                _cache.popitem(last=False)
        finally:
            _cache_lock.release()
    except Exception:
        invalidate_subscription(uid)


def invalidate_subscription(uid: str) -> None:
    """Best-effort invalidation around existing subscription writes."""
    try:
        owner = _request_owner.get()
        if owner is not None and owner.uid == uid:
            owner.tier, owner.expires_at = 'unattributed', 0
        if not _cache_lock.acquire(blocking=False):
            return
        try:
            _cache.pop(uid, None)
        finally:
            _cache_lock.release()
    except Exception:
        return


def current_tier() -> str:
    """The hot probe path: no lock, cache lookup, uid label, logging, or I/O."""
    try:
        owner = _request_owner.get()
        if owner is not None and not owner.closed and owner.expires_at > time.monotonic():
            return bounded_tier(owner.tier)
    except Exception:
        pass
    return 'unattributed'


class FirestoreTierMiddleware:
    """Pure ASGI lifetime boundary, including HTTP streams and WebSockets."""

    def __init__(self, app: Any):
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope['type'] not in ('http', 'websocket'):
            await self.app(scope, receive, send)
            return
        owner = _RequestOwner()
        token = _request_owner.set(owner)

        async def send_with_lifetime(message: Any) -> None:
            # Starlette BackgroundTasks run after the final response body; they
            # must not inherit a completed request's owner, even before ASGI returns.
            if (message['type'] == 'http.response.body' and not message.get('more_body', False)) or message[
                'type'
            ] == 'websocket.close':
                owner.closed = True
            await send(message)

        try:
            await self.app(scope, receive, send_with_lifetime)
        finally:
            owner.closed = True  # Also revokes copies held by detached tasks/workers.
            _request_owner.reset(token)
