"""Process-wide stale-while-refresh token cohort; serving checks never wait for IO."""

import asyncio
from dataclasses import dataclass
import logging
import os
from threading import RLock
import time
from typing import Callable

from config.rollout_cohorts import parse_cohort, rollout_environment
from config.stt_cap_dispatch import execution_admission_configured
from database.rollout_cohorts import read_stt_cap_cohort
from utils import executors
from utils.observability.fallback import record_fallback
from utils.observability.stt_cap_dispatch import COHORT_SOURCE, COHORT_PERCENT, COHORT_REFRESH_FAILURES

TTL_SECONDS = 60
logger = logging.getLogger(__name__)


@dataclass
class _Snapshot:
    # None is a confirmed missing document, '' is a document-layer denial.
    tokens: str | None = None
    expires: float = 0
    pending: bool = False
    malformed_logged: bool = False


class RuntimeCohort:
    def __init__(self, reader: Callable = read_stt_cap_cohort, *, clock: Callable = time.monotonic, submit=None):
        self.reader = reader
        self.clock = clock
        self.submit = submit
        self.lock = RLock()
        # rollout_environment accepts exactly four identities; never keyed by UID.
        self.snapshots: dict[str, _Snapshot] = {}
        self.observed: tuple[str, str] | None = None

    def _observe(self, tokens: str | None) -> str:
        raw = os.getenv('STT_CAP_DISPATCH_COHORT', '') if tokens is None else tokens
        parsed = parse_cohort(raw)
        source = ('env' if tokens is None else 'doc') if parsed is not None else ('none' if tokens is None else 'doc')
        active_source = source if execution_admission_configured() else 'none'
        pct = parsed[1] if parsed is not None and active_source != 'none' else 0
        observation = (active_source, raw)
        if self.observed == observation:
            return raw
        for label in ('doc', 'env', 'none'):
            COHORT_SOURCE.labels(source=label).set(int(label == active_source))
        COHORT_PERCENT.set(pct)
        self.observed = observation
        # Detect exact membership changes without emitting tokens, hashes or UIDs.
        logger.info('event=stt_cap_cohort_changed source=%s pct=%d', active_source, pct)
        return raw

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
            # SDK errors may contain private paths or payloads. Retain even a
            # previous empty/malformed denial; errors never restore env over it.
            with self.lock:
                self._failure('read')
                snapshot.expires = self.clock() + TTL_SECONDS
                snapshot.pending = False
            return
        with self.lock:
            malformed = doc is not None and (
                not isinstance(doc, dict)
                or doc.get('environment') != environment
                or not isinstance(doc.get('tokens'), str)
                or bool(doc['tokens'].strip())
                and parse_cohort(doc['tokens']) is None
            )
            if malformed:
                snapshot.tokens = ''
                if not snapshot.malformed_logged:
                    logger.warning('event=stt_cap_cohort_invalid outcome=denied')
                snapshot.malformed_logged = True
            else:
                snapshot.tokens = None if doc is None else doc['tokens']
                snapshot.malformed_logged = False
            snapshot.expires = self.clock() + TTL_SECONDS
            snapshot.pending = False
            self._observe(snapshot.tokens)

    def tokens(self) -> str:
        with self.lock:
            try:
                environment = rollout_environment()
            except ValueError:
                return self._observe('')
            snapshot = self.snapshots.setdefault(environment, _Snapshot())
            if execution_admission_configured() and not snapshot.pending and self.clock() >= snapshot.expires:
                snapshot.pending = True
                try:
                    submit = self.submit or executors.get_rollout_executor().submit
                    submit(self._refresh, environment, snapshot)
                except Exception:
                    snapshot.pending = False
                    snapshot.expires = self.clock() + TTL_SECONDS
                    self._failure('schedule')
            return self._observe(snapshot.tokens)


runtime_cohort = RuntimeCohort()


async def refresh_stt_cap_cohort_forever() -> None:
    """Startup-owned poller; demand checks share the same TTL and in-flight slot."""
    while True:
        runtime_cohort.tokens()
        # Poll more often than the TTL: the one-second read deadline must not
        # make an idle host skip an entire minute at the expiry boundary.
        await asyncio.sleep(5)
