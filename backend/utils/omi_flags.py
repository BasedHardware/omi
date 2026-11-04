"""In-process evaluation of Omi-owned feature flags (the PostHog flag replacement).

Every process holds one snapshot of ``database.omi_flags`` and re-checks its
version at most every ``REDIS_CHECK_SECONDS`` (Redis fast path) and
``STORE_POLL_SECONDS`` (Firestore ``meta`` doc, always, so a writer without Redis
access still propagates). A failed refresh keeps the last good snapshot.

A key absent from the store is ``None`` to callers: they keep their previous
source (PostHog) or the registry fail value. That makes migration per flag:
writing a rule moves that key, deleting it moves it back.

Rollout bucketing is PostHog's (``sha1("{key}.{uid}")`` over 15 hex digits), so a
flag imported at the same percentage keeps the same users.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Mapping

from database import omi_flags as store
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

REDIS_CHECK_SECONDS = 15.0
STORE_POLL_SECONDS = 60.0
_LONG_SCALE = float(0xFFFFFFFFFFFFFFF)
CLIENT_SURFACES = ('macos', 'mobile', 'web-app', 'windows')


@dataclass(frozen=True)
class FlagRule:
    key: str
    active: bool = False
    rollout_percentage: float = 0.0
    variant: str | None = None
    payload: str | None = None
    allow_uids: frozenset[str] = frozenset()
    deny_uids: frozenset[str] = frozenset()
    surfaces: tuple[str, ...] = ()

    @classmethod
    def from_doc(cls, key: str, doc: Mapping[str, Any]) -> 'FlagRule':
        pct = float(doc.get('rollout_percentage') or 0)
        variant = doc.get('variant')
        payload = doc.get('payload')
        return cls(
            key=key,
            active=doc.get('active') is True,
            rollout_percentage=min(100.0, max(0.0, pct)),
            variant=variant if isinstance(variant, str) and variant else None,
            payload=payload if isinstance(payload, str) and payload else None,
            allow_uids=frozenset(str(u) for u in doc.get('allow_uids') or ()),
            deny_uids=frozenset(str(u) for u in doc.get('deny_uids') or ()),
            surfaces=tuple(str(s) for s in doc.get('surfaces') or ()),
        )


@dataclass(frozen=True)
class Resolved:
    enabled: bool
    variant: str | None = None
    payload: str | None = None


@dataclass(frozen=True)
class Snapshot:
    version: int | None = None
    rules: Mapping[str, FlagRule] = field(default_factory=dict)

    @property
    def loaded(self) -> bool:
        return self.version is not None


EMPTY = Snapshot()


def rollout_hash(key: str, uid: str) -> float:
    # Bucketing, not security: must match PostHog's SHA-1 bit for bit so imported cohorts do not move.
    digest = hashlib.sha1(f'{key}.{uid}'.encode('utf-8'), usedforsecurity=False).hexdigest()[:15]
    return int(digest, 16) / _LONG_SCALE


def evaluate(rule: FlagRule, uid: str) -> Resolved:
    if not rule.active or uid in rule.deny_uids:
        return Resolved(False)
    if uid not in rule.allow_uids and rollout_hash(rule.key, uid) > rule.rollout_percentage / 100:
        return Resolved(False)
    return Resolved(True, rule.variant, rule.payload)


class _SnapshotCache:
    def __init__(self) -> None:
        self._lock = Lock()
        self._snapshot = EMPTY
        self._redis_checked_at = float('-inf')
        self._store_checked_at = float('-inf')

    def reset(self) -> None:
        with self._lock:
            self._snapshot = EMPTY
            self._redis_checked_at = self._store_checked_at = float('-inf')

    def get(self) -> Snapshot:
        now = time.monotonic()
        if now - self._redis_checked_at < REDIS_CHECK_SECONDS and now - self._store_checked_at < STORE_POLL_SECONDS:
            return self._snapshot
        # Once loaded, a refresh in another thread never blocks readers; they serve the current snapshot.
        if not self._lock.acquire(blocking=not self._snapshot.loaded):
            return self._snapshot
        try:
            self._refresh(now)
            return self._snapshot
        finally:
            self._lock.release()

    def _refresh(self, now: float) -> None:
        if store.store_target() is None:
            self._snapshot = EMPTY
            self._redis_checked_at = self._store_checked_at = now
            return
        current = self._snapshot.version
        remote: int | None = None
        if now - self._redis_checked_at >= REDIS_CHECK_SECONDS:
            self._redis_checked_at = now
            remote = store.read_redis_version()
        try:
            # Inside the try: client construction (ADC, database id) fails like a read and keeps the snapshot.
            client = store.flags_client()
            if now - self._store_checked_at >= STORE_POLL_SECONDS or (remote is not None and remote != current):
                self._store_checked_at = now
                version, docs = store.read_all(client) if current is None else (store.read_version(client), None)
                if docs is None and version != current:
                    version, docs = store.read_all(client)
                if docs is not None:
                    self._snapshot = Snapshot(version, {k: FlagRule.from_doc(k, d) for k, d in docs.items()})
        except Exception as exc:
            record_fallback(
                component='feature_flags',
                from_mode='store',
                to_mode='last_known_good' if self._snapshot.loaded else 'none',
                reason='other',
                outcome='degraded',
                log=logger,
                failure_subtype=type(exc).__name__[:64],
            )


_cache = _SnapshotCache()


def snapshot() -> Snapshot:
    return _cache.get()


def resolve(key: str, uid: str) -> Resolved | None:
    """The flag for ``uid``, or None when the store is unconfigured, unreadable, or has no rule for ``key``."""
    rule = snapshot().rules.get(key)
    return evaluate(rule, uid) if rule is not None else None


def resolve_surface(uid: str, surface: str) -> tuple[int | None, dict[str, Resolved]]:
    snap = snapshot()
    return snap.version, {
        key: evaluate(rule, uid) for key, rule in sorted(snap.rules.items()) if surface in rule.surfaces
    }
