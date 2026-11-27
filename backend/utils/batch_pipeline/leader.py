"""Advisory single-owner lease for idempotent batch maintenance loops.

With several worker or serving replicas, timer loops such as lease recovery,
result-ready draining, artifact cleanup and quarantine discovery would otherwise
run once per replica per interval. Every one of those loops is already
idempotent and fenced by its own Firestore transactions, so this lease is a
cost and contention control only, never a correctness fence:

- One holder per role renews a TTL row in ``{namespace}_leases``. Another
  replica takes over only after the TTL lapses (crash, long GPU batch, drain).
- Each fresh acquisition mints a new token. Ownership is the row's holder
  identity: a live row naming this process is adopted with its stored token
  (so a lost commit acknowledgement heals next tick); a row naming another
  holder makes this process follow until that TTL lapses.
- Advisory lease-store errors fail open: the caller runs its loop exactly as it did
  before this lease existed. ``BATCH_PIPELINE_LEADER_LEASE_ENABLED=false`` does
  the same unconditionally.

The upload coalescing and projection outbox scan roles always elect, fail
closed on errors, and supply transactional token witnesses for scan progress.
Delivery and custody claims survive discovery takeover.
"""

import logging
import threading
import time
import uuid
from collections.abc import Callable

from prometheus_client import Counter

from config.batch_pipeline_leader import leader_lease_enabled, UPLOAD_COALESCING_SCAN
from config.batch_timeliness import MAX_INTERVAL_SECONDS
from database.batch_pipeline_leader import LeaseGuard, LeaseLost

logger = logging.getLogger(__name__)

TABLE = 'leases'
# Static, low-cardinality roles. Keep the worker pump and serving supervisor
# separate: each already ran its own recovery before replicas existed.
PUMP_RECOVERY = 'pump_recovery'
SERVING_MAINTENANCE = 'serving_maintenance'
SERVING_LEGACY_METRICS = 'serving_legacy_metrics'
QUEUE_METRICS = 'queue_metrics'
TIMELINESS_METRICS = 'timeliness_metrics'
PROJECTION_OUTBOX_SCAN = 'projection_outbox_scan'
STRICT_ROLES = frozenset({UPLOAD_COALESCING_SCAN, PROJECTION_OUTBOX_SCAN})
# Cover supervised tick jitter and sample RPCs between configured samples;
# the default sampling cadence remains 300s.
TIMELINESS_LEASE_GRACE_SECONDS = 60.0
ROLES = STRICT_ROLES | {
    PUMP_RECOVERY,
    SERVING_MAINTENANCE,
    SERVING_LEGACY_METRICS,
    QUEUE_METRICS,
    TIMELINESS_METRICS,
}
LEASE_EVENTS = Counter('omi_batch_leader_lease_total', 'Lease checks by static role and outcome', ['role', 'outcome'])


class LeaderLease:
    def __init__(
        self,
        store,
        role: str,
        *,
        ttl_seconds: float,
        holder: str | None = None,
        clock: Callable[[], float] = time.time,
    ):
        # Timeliness samples run at 60-600s. Hold through the interval plus
        # bounded refresh grace, so samples stay visible during normal RPCs.
        # Existing longer leases remain live until their stored expiry.
        max_ttl = MAX_INTERVAL_SECONDS + TIMELINESS_LEASE_GRACE_SECONDS if role == TIMELINESS_METRICS else 600
        if role not in ROLES or not 0 < ttl_seconds <= max_ttl:
            raise ValueError('static role and bounded lease TTL required')
        self.store = store
        self.role = role
        self.ttl_seconds = float(ttl_seconds)
        # Random per-process identity; carries no pod, host or user data.
        self.holder = holder or uuid.uuid4().hex
        self.clock = clock
        self.token: str | None = None
        self._lock = threading.Lock()

    def acquire(self) -> bool:
        """True when this replica should run the guarded loop this tick."""
        if self.role not in STRICT_ROLES and not leader_lease_enabled():
            return True
        # One process-local holder may be acquired from several executor
        # threads (serving supervisor and /metrics); serialize so a losing
        # overlap can never clear the winner's token.
        with self._lock:
            return self._acquire()

    def _acquire(self) -> bool:
        LEASE_EVENTS.labels(role=self.role, outcome='attempt').inc()
        current, candidate = self.token, uuid.uuid4().hex  # Minted outside the retryable body.

        def body(tx):
            LEASE_EVENTS.labels(role=self.role, outcome='transaction_attempt').inc()
            row = tx.get(TABLE, self.role)
            now = self.clock()  # A retried acquisition never extends an already stale clock.
            expires_at = float(row.get('expires_at') or 0)
            live = bool(row) and expires_at > now
            if live and row.get('holder') != self.holder:
                return None  # Another live replica leads this role.
            # A live row naming this holder is ours even when the in-memory
            # token was lost (ambiguous commit acknowledgement): adopt it.
            token = (row.get('token') or candidate) if live else candidate
            if live and token == row.get('token') and expires_at - now > self.ttl_seconds / 2:
                return token  # Still well inside our TTL: read-only renewal.
            tx.put(
                TABLE,
                self.role,
                {
                    'role': self.role,
                    'holder': self.holder,
                    'token': token,
                    'expires_at': now + self.ttl_seconds,
                    'renewed_at': now,
                },
            )
            return token

        try:
            token = self.store.run(body)
        except Exception as error:
            strict = self.role in STRICT_ROLES
            LEASE_EVENTS.labels(role=self.role, outcome='error').inc()
            logger.warning(
                'event=batch_leader_lease role=%s outcome=%s exception_type=%s',
                self.role,
                'fail_closed' if strict else 'fail_open',
                type(error).__name__,
            )
            if strict:
                self.token = None
            return not strict
        LEASE_EVENTS.labels(role=self.role, outcome='leader' if token is not None else 'follower').inc()
        if token != current:
            logger.info(
                'event=batch_leader_lease role=%s outcome=%s',
                self.role,
                'acquired' if token is not None else 'follower',
            )
        self.token = token
        return token is not None

    def guard(self) -> LeaseGuard:
        """Immutable token for a strict scan, never the mutable next acquisition."""
        if self.role not in STRICT_ROLES or self.token is None:
            raise LeaseLost('strict scan ownership required')
        return LeaseGuard(self.role, self.holder, self.token, self.clock)
