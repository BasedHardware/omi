"""Process-wide stale-while-refresh held-content cohort. Serving checks never wait on IO.

HELD_CONTENT_ENABLED is the kill switch and is read before the cache. A missing
snapshot denies. A confirmed-absent document falls back to HELD_CONTENT_COHORT.
Malformed documents and refresh failures never widen the last decision.
"""

import asyncio
from dataclasses import dataclass
import logging
import os
from threading import RLock
import time
from typing import Callable

from config.rollout_cohorts import parse_cohort, rollout_environment
from database.rollout_cohorts import read_held_content_cohort
from utils import executors
from utils.held_content_flags import enabled
from utils.observability.fallback import record_fallback
from utils.observability.held_content import COHORT_PERCENT, COHORT_REFRESH_FAILURES, COHORT_SOURCE

TTL_SECONDS = 60
COHORT_ENV = 'HELD_CONTENT_COHORT'
logger = logging.getLogger(__name__)


@dataclass
class _Snapshot:
    # None after a confirmed miss is the env fallback. '' is a document denial.
    tokens: str | None = None
    seen: bool = False
    expires: float = 0
    pending: bool = False
    malformed_logged: bool = False


class RuntimeCohort:
    def __init__(self, reader: Callable = read_held_content_cohort, *, clock: Callable = time.monotonic, submit=None):
        self.reader = reader
        self.clock = clock
        self.submit = submit
        self.lock = RLock()
        self.snapshots: dict[str, _Snapshot] = {}
        self.observed: tuple[str, int] | None = None

    def _publish(self, raw: str, source: str) -> str:
        parsed = parse_cohort(raw)
        active = source if parsed is not None and source in {'doc', 'env'} else 'none'
        pct = parsed[1] if parsed is not None and active != 'none' else 0
        observation = (active, pct)
        if self.observed != observation:
            for label in ('doc', 'env', 'none'):
                COHORT_SOURCE.labels(source=label).set(int(label == active))
            COHORT_PERCENT.set(pct)
            self.observed = observation
            logger.info('event=held_content_cohort_changed source=%s pct=%d', active, pct)
        return raw if active != 'none' else ''

    def _failure(self, reason: str) -> None:
        COHORT_REFRESH_FAILURES.labels(reason=reason).inc()
        record_fallback(
            component='firestore_read',
            from_mode='cohort_doc',
            to_mode='cohort_cache',
            reason='unavailable',
            outcome='degraded',
            log=logger,
        )

    def _refresh(self, environment: str, snapshot: _Snapshot) -> None:
        try:
            doc = self.reader()
        except Exception:
            with self.lock:
                self._failure('read')
                snapshot.expires = self.clock() + TTL_SECONDS
                snapshot.pending = False
            return
        with self.lock:
            tokens = doc.get('tokens') if isinstance(doc, dict) else None
            malformed = doc is not None and (
                not isinstance(doc, dict)
                or doc.get('environment') != environment
                or not isinstance(tokens, str)
                or (bool(tokens.strip()) and parse_cohort(tokens) is None)
            )
            if malformed:
                snapshot.tokens = ''
                if not snapshot.malformed_logged:
                    logger.warning('event=held_content_cohort_invalid outcome=denied')
                snapshot.malformed_logged = True
            else:
                snapshot.tokens = None if doc is None else doc['tokens']
                snapshot.malformed_logged = False
            snapshot.seen = True
            snapshot.expires = self.clock() + TTL_SECONDS
            snapshot.pending = False
            if not enabled():
                self._publish('', 'none')
            elif snapshot.tokens is None:
                self._publish(os.getenv(COHORT_ENV, ''), 'env')
            else:
                self._publish(snapshot.tokens, 'doc')

    def _schedule(self, environment: str, snapshot: _Snapshot) -> None:
        if snapshot.pending or self.clock() < snapshot.expires:
            return
        snapshot.pending = True
        try:
            submit = self.submit or executors.get_rollout_executor().submit
            submit(self._refresh, environment, snapshot)
        except Exception:
            snapshot.pending = False
            snapshot.expires = self.clock() + TTL_SECONDS
            self._failure('schedule')

    def tokens(self) -> str:
        with self.lock:
            if not enabled():
                return self._publish('', 'none')
            try:
                environment = rollout_environment()
            except ValueError:
                return self._publish('', 'none')
            snapshot = self.snapshots.setdefault(environment, _Snapshot())
            self._schedule(environment, snapshot)
            if not snapshot.seen:
                return self._publish('', 'none')
            if snapshot.tokens is None:
                return self._publish(os.getenv(COHORT_ENV, ''), 'env')
            return self._publish(snapshot.tokens, 'doc')


runtime_cohort = RuntimeCohort()


def admitted(uid: str) -> bool:
    """Kill switch first. Cohort membership never admits a request the switch denies."""
    from config.rollout_cohorts import cohort_admits

    if not enabled():
        return False
    return cohort_admits(uid, runtime_cohort.tokens())


async def refresh_held_content_cohort_forever() -> None:
    """Startup poller. Request checks share the TTL and the single in-flight read."""
    while True:
        runtime_cohort.tokens()
        await asyncio.sleep(5)
