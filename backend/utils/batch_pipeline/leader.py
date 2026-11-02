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
- Any lease-store error fails open: the caller runs its loop exactly as it did
  before this lease existed. ``BATCH_PIPELINE_LEADER_LEASE_ENABLED=false`` does
  the same unconditionally.
"""

import logging
import threading
import time
import uuid
from collections.abc import Callable

from config.batch_pipeline_leader import leader_lease_enabled

logger = logging.getLogger(__name__)

TABLE = 'leases'
# Static, low-cardinality roles. Keep the worker pump and serving supervisor
# separate: each already ran its own recovery before replicas existed.
PUMP_RECOVERY = 'pump_recovery'
SERVING_MAINTENANCE = 'serving_maintenance'
ROLES = frozenset({PUMP_RECOVERY, SERVING_MAINTENANCE})


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
        if role not in ROLES or not 0 < ttl_seconds <= 600:
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
        if not leader_lease_enabled():
            return True
        # One process-local holder may be acquired from several executor
        # threads (serving supervisor and /metrics); serialize so a losing
        # overlap can never clear the winner's token.
        with self._lock:
            return self._acquire()

    def _acquire(self) -> bool:
        now = self.clock()
        current, candidate = self.token, uuid.uuid4().hex  # Minted outside the retryable body.

        def body(tx):
            row = tx.get(TABLE, self.role)
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
            logger.warning(
                'event=batch_leader_lease role=%s outcome=fail_open exception_type=%s',
                self.role,
                type(error).__name__,
            )
            return True
        if token != current:
            logger.info(
                'event=batch_leader_lease role=%s outcome=%s',
                self.role,
                'acquired' if token is not None else 'follower',
            )
        self.token = token
        return token is not None
