# LIFECYCLE: permanent
"""Runtime cohort percents and the legacy_sync mode from `rollout_cohorts/_ramp` (contract (f)).

One process-wide cache entry with a 30s TTL. Reads run on the rollout executor, never on the
event loop, with a 1s timeout and SDK retries off. On a read error or a malformed document the
last-known-good value is served indefinitely (source="lkg"); a cold start with nothing loaded
serves each caller's env_default (source="env_default"). A value is never raised above LKG on
error. The bucket functions in config/ are untouched; only the percent source moves here.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import Future
import contextvars
from dataclasses import dataclass
import datetime as dt
import logging
import os
from threading import RLock
import time
from types import MappingProxyType
from typing import Any, Callable, Literal, Mapping

from prometheus_client import Gauge

from config import rollout_cohorts as policy
from config.rollout_cohorts import rollout_environment
from database import rollout_cohorts as store
from utils import executors

RAMP_NAMES = store.RAMP_NAMES
RAMP_DOC_ID = store.RAMP_DOC_ID
RAMP_ENVS = store.RAMP_ENVS
LEGACY_SYNC_MODES = store.LEGACY_SYNC_MODES
TTL_SECONDS = 30.0
COLD_READ_WAIT_SECONDS = 1.25
LKG_ALERT_SECONDS = 300.0
SOURCES = ('firestore', 'lkg', 'env_default')

LegacySyncMode = Literal['on', 'draining', 'dark']
logger = logging.getLogger(__name__)

RUNTIME_PERCENT_SOURCE = Gauge(
    'omi_runtime_percent_source',
    'Current source of runtime percents (1 for the active source): ramp, lkg, or env_default.',
    ['source'],
)
RUNTIME_PERCENT_ERROR_SECONDS = Gauge(
    'omi_runtime_percent_read_error_seconds',
    'Seconds since `_ramp` reads started failing; 0 while reads succeed. Alert above 300.',
)
RUNTIME_PERCENT_VALUE = Gauge(
    'omi_runtime_percent',
    'Percent served from the `_ramp` document (after nesting clamp); absent names are not exported.',
    ['name'],
)


@dataclass(frozen=True)
class RampSnapshot:
    """Frozen view of one environment's `_ramp` entry as this process currently serves it."""

    revision: int  # 0 when no document exists
    percents: Mapping[str, float]
    legacy_sync: LegacySyncMode
    locked_by: str | None
    source: Literal['firestore', 'lkg', 'env_default']
    env: str | None = None
    updated_at: str | None = None
    updated_by: str | None = None
    reason: str | None = None
    error_seconds: float = 0.0


class RampEnvironmentError(ValueError):
    """The process identity does not map to a `_ramp` environment."""


def deployment_env() -> str:
    """`OMI_DEPLOYMENT` when set (staging), else rollout_environment()."""
    deployment = os.getenv('OMI_DEPLOYMENT', '').strip().lower()
    env = deployment or rollout_environment()
    if env not in RAMP_ENVS:
        raise RampEnvironmentError('unsupported ramp environment')
    return env


def clamp_nesting(percents: Mapping[str, float]) -> dict[str, float]:
    """batch-live-stt-retire never exceeds batch-pipeline at read time (E decision 2)."""
    clamped = dict(percents)
    if 'batch-live-stt-retire' in clamped:
        clamped['batch-live-stt-retire'] = min(clamped['batch-live-stt-retire'], clamped.get('batch-pipeline', 0.0))
    return clamped


@dataclass
class _Loaded:
    env: str
    revision: int
    env_doc: dict[str, Any] | None  # None: no document or no entry for this env (nothing configured)


def _submit_read(fn: Callable[[], None]) -> Future:
    return executors.get_rollout_executor().submit(contextvars.Context().run, fn)  # never inherit request context


_background_submitter: Callable[[Callable[[], None]], Any] | None = _submit_read


class _RampCache:
    def __init__(self, reader: Callable[[], dict[str, Any] | None]):
        self.reader = reader
        self.lock = RLock()
        self.loaded: _Loaded | None = None
        self.expires = float('-inf')
        self.inflight: Future | None = None
        self.error_since: float | None = None

    def _refresh(self, done: Future) -> None:
        try:
            env = deployment_env()
            document = self.reader()
            entry = document['envs'].get(env) if document is not None else None
            loaded = _Loaded(env, document['revision'] if document is not None else 0, entry)
        except Exception:
            # SDK errors can carry paths and payloads; keep the line content-free.
            logger.warning('event=runtime_percent_read outcome=error served=lkg_or_env_default')
            with self.lock:
                now = time.monotonic()
                if self.error_since is None:
                    self.error_since = now
                self.expires = now + TTL_SECONDS
                self.inflight = None
            _export(self.snapshot_now())
            done.set_result(None)
            return
        with self.lock:
            self.loaded = loaded
            self.error_since = None
            self.expires = time.monotonic() + TTL_SECONDS
            self.inflight = None
        _export(self.snapshot_now())
        done.set_result(None)

    def start_refresh(self) -> Future | None:
        """Start at most one read; returns the in-flight future."""
        with self.lock:
            if self.inflight is not None:
                return self.inflight
            if time.monotonic() < self.expires:
                return None
            done: Future = Future()
            self.inflight = done
        try:
            if _background_submitter is None:
                raise RuntimeError('rollout executor not configured')
            _background_submitter(lambda: self._refresh(done))
        except Exception:
            logger.warning('event=runtime_percent_read outcome=not_scheduled served=lkg_or_env_default')
            with self.lock:
                now = time.monotonic()
                if self.error_since is None:
                    self.error_since = now
                self.expires = now + TTL_SECONDS
                self.inflight = None
            done.set_result(None)
        return done

    def snapshot(self) -> RampSnapshot:
        pending = self.start_refresh()
        if pending is not None and self.loaded is None and not _on_event_loop():
            # Cold start off the loop: give the first read a bounded chance so the first
            # requests do not run on env defaults. Never waits on the event loop.
            try:
                pending.result(timeout=COLD_READ_WAIT_SECONDS)
            except Exception:
                pass
        return self.snapshot_now()

    def snapshot_now(self) -> RampSnapshot:
        with self.lock:
            loaded, error_since = self.loaded, self.error_since
        error_seconds = 0.0 if error_since is None else max(0.0, time.monotonic() - error_since)
        if loaded is None:
            return RampSnapshot(
                revision=0,
                percents=MappingProxyType({}),
                legacy_sync='on',
                locked_by=None,
                source='env_default',
                error_seconds=error_seconds,
            )
        source: Literal['firestore', 'lkg', 'env_default']
        if error_since is not None:
            source = 'lkg'
        elif loaded.env_doc is None:
            source = 'env_default'
        else:
            source = 'firestore'
        doc = loaded.env_doc or store.empty_ramp_env()
        return RampSnapshot(
            revision=loaded.revision,
            percents=MappingProxyType(clamp_nesting(doc['percents'])),
            legacy_sync=doc['legacy_sync'],
            locked_by=doc['locked_by'],
            source=source,
            env=loaded.env,
            updated_at=doc['updated_at'],
            updated_by=doc['updated_by'],
            reason=doc['reason'],
            error_seconds=error_seconds,
        )

    def invalidate(self) -> None:
        with self.lock:
            self.expires = float('-inf')


def _on_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _export(snapshot: RampSnapshot) -> None:
    for source in SOURCES:
        RUNTIME_PERCENT_SOURCE.labels(source=source).set(1 if snapshot.source == source else 0)
    RUNTIME_PERCENT_ERROR_SECONDS.set(snapshot.error_seconds)
    for name in RAMP_NAMES:
        if name in snapshot.percents:
            RUNTIME_PERCENT_VALUE.labels(name=name).set(snapshot.percents[name])


def _read_ramp_document() -> dict[str, Any] | None:
    return store.read_ramp()


_cache = _RampCache(_read_ramp_document)


def ramp_snapshot() -> RampSnapshot:
    return _cache.snapshot()


def runtime_percent(name: str, *, env_default: float) -> float:
    """The `_ramp` percent for this environment, else env_default. Never raises on a serving path."""
    if name not in RAMP_NAMES:
        return env_default
    try:
        value = ramp_snapshot().percents.get(name)
    except Exception:
        logger.warning('event=runtime_percent_read outcome=snapshot_failed served=env_default')
        return env_default
    return env_default if value is None else value


def legacy_sync_mode() -> LegacySyncMode:
    """'on' | 'draining' | 'dark' for this environment; 'on' until a document says otherwise."""
    try:
        return ramp_snapshot().legacy_sync
    except Exception:
        logger.warning('event=runtime_percent_read outcome=snapshot_failed served=on')
        return 'on'


async def warm_ramp() -> None:
    """Await the first read from async code without blocking the loop (bounded)."""
    pending = _cache.start_refresh()
    if pending is None or pending.done():
        return
    try:
        await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(pending)), timeout=COLD_READ_WAIT_SECONDS)
    except asyncio.TimeoutError:
        pass


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _log_value(field_name: str, value: Any) -> str:
    if field_name == 'locked_by':
        return 'set' if value else 'none'
    return str(value)


def write_ramp(
    env: str,
    change: Mapping[str, Any],
    *,
    expected_revision: int,
    actor: str,
    reason: str,
    gate_verdict: Mapping[str, Any] | None = None,
    firestore_client: Any | None = None,
) -> int:
    """CAS write of one environment's entry plus its history row; used only by the controller and ramp_set.

    Raises store.RampRevisionConflict when the revision moved and store.RampDocumentError on a change
    that violates the schema (range, unknown names, nesting).
    """
    revision, before, after = store.write_ramp(
        env,
        change,
        expected_revision=expected_revision,
        actor=actor,
        reason=reason,
        gate_verdict=gate_verdict,
        at=_utc_now_iso(),
        firestore_client=firestore_client,
    )
    fields: list[tuple[str, Any, Any]] = [
        (name, before['percents'].get(name), after['percents'].get(name))
        for name in RAMP_NAMES
        if before['percents'].get(name) != after['percents'].get(name)
    ]
    for field_name in ('legacy_sync', 'locked_by'):
        if field_name in change:
            fields.append((field_name, before[field_name], after[field_name]))
    for name, old, new in fields or [('none', None, None)]:
        logger.info(
            'event=ramp_write env=%s name=%s before=%s after=%s revision=%d actor=%s reason=%s',
            env,
            name,
            _log_value(name, old),
            _log_value(name, new),
            revision,
            actor,
            reason,
        )
    _cache.invalidate()
    return revision


def configure_runtime_percent() -> None:
    """Bind the config-layer percent and legacy_sync seams to this runtime reader."""
    policy.configure_runtime_percent(
        lambda name, env_default: runtime_percent(name, env_default=env_default), legacy_sync_mode
    )
