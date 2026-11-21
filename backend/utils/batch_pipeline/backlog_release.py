"""Uncached, fail-closed hourly provider backlog budget; called inside merge's transaction."""

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeGuard, cast

from google.api_core.exceptions import Aborted
from prometheus_client import Counter, Gauge

from config.batch_pipeline import provider_backlog_release_closed
from config.batch_pipeline_backlog_release import MIN_REACH_SECONDS, valid_owner_keys
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
COMMITTED = Counter('omi_batch_pipeline_backlog_committed_total', 'Observed metered backlog commits')
REFUSED = Counter('omi_batch_pipeline_backlog_refused_total', 'Backlog gate refusals', ['reason'])


FIELDS = ('state', 'rate_per_hour', 'reach_seconds', 'window', 'tokens_used', 'updated_at')
POLICY_FIELDS = ('schema_version', 'mode', 'owner_keys')
HEARTBEAT_AGE = Gauge('omi_batch_pipeline_backlog_heartbeat_age_seconds', 'Age at last gate observation')
TOKENS_GRANTED = Counter('omi_batch_pipeline_backlog_tokens_granted_total', 'Observed durable token grants')
ALLOWLIST_HITS = Counter('omi_batch_pipeline_backlog_allowlist_hits_total', 'Observed commits for allowlisted owners')
TOKENS_USED = Gauge('omi_batch_pipeline_backlog_window_tokens_used', 'Durable usage at last heartbeat or commit')
WINDOW = Gauge('omi_batch_pipeline_backlog_token_window', 'Epoch hour of observed durable usage')


def _number(value: object) -> TypeGuard[float]:
    return type(value) in (int, float) and math.isfinite(cast(float, value))


@dataclass(frozen=True)
class Gate:
    state: str
    rate_per_hour: int
    reach_seconds: int  # 0 means no reach limit.
    window: int
    tokens_used: int
    updated_at: float
    schema_version: int = 1
    mode: str = 'all'
    owner_keys: tuple[str, ...] = ()

    @classmethod
    def parse(cls, row: dict) -> 'Gate | None':
        """Every field is required and nothing else is allowed: a partial document must not reset the budget."""
        versioned = set(row) == set(FIELDS + POLICY_FIELDS)
        if set(row) != set(FIELDS) and not versioned:
            return None
        if versioned and (
            type(row['schema_version']) is not int
            or row['schema_version'] != 2
            or row['mode'] not in ('all', 'allowlist_only')
            or not valid_owner_keys(row['owner_keys'])
        ):
            return None
        gate = cls(
            state=row['state'],
            rate_per_hour=row['rate_per_hour'],
            reach_seconds=row['reach_seconds'],
            window=row['window'],
            tokens_used=row['tokens_used'],
            updated_at=row['updated_at'],
            schema_version=2 if versioned else 1,
            mode=row['mode'] if versioned else 'all',
            owner_keys=tuple(row['owner_keys']) if versioned else (),
        )
        counts = (gate.rate_per_hour, gate.reach_seconds, gate.window, gate.tokens_used)
        if any(type(value) is not int or value < 0 for value in counts):
            return None
        if gate.state not in ('open', 'closed') or not _number(gate.updated_at) or gate.updated_at < 0:
            return None
        if gate.window > gate.hour():  # Tokens counted against an hour the heartbeat has not reached.
            return None
        if versioned and gate.reach_seconds and gate.reach_seconds < MIN_REACH_SECONDS:
            return None
        return gate

    def refusal(self, job: dict, now: float) -> str | None:
        if self.state != 'open':
            return 'closed'
        if not 0 <= now - self.updated_at < 180:
            return 'stale'
        if self.mode == 'allowlist_only' and job.get('owner_key') not in self.owner_keys:
            return 'allowlist'
        capture, duration = job.get('capture_at'), job.get('duration_seconds')
        if not (_number(capture) and _number(duration) and duration >= 0):
            return 'job'
        if self.reach_seconds and now - capture - duration > self.reach_seconds:
            return 'reach'
        if self.used() >= self.rate_per_hour:
            return 'rate'
        return None

    def hour(self) -> int:
        """The heartbeat is the one clock for the budget hour, so a committer's fast or slow clock cannot roll it."""
        return int(self.updated_at // 3600)

    def used(self) -> int:
        return self.tokens_used if self.window == self.hour() else 0


def read(tx, job: dict, now: Callable[[], float], source: str) -> tuple[dict | None, str | None]:
    """Return the token write, or a bounded refusal. Never refresh the operator heartbeat."""
    if provider_backlog_release_closed():
        return None, 'closed'
    try:
        row = tx.get('backlog_release', 'gate')
    except Aborted:
        raise
    except Exception as error:
        logger.warning(
            'event=batch_merge outcome=backlog_gate_unavailable source=%s exception_type=%s count=1',
            source,
            type(error).__name__,
        )
        record_fallback(
            component='firestore_read',
            from_mode='backlog_gate',
            to_mode='backlog_hold',
            reason='unavailable',
            outcome='degraded',
            log=logger,
        )
        return None, 'error'
    if not row:
        return None, 'missing'
    gate = Gate.parse(row)
    if gate is None:
        return None, 'closed'
    observed_at = now()
    HEARTBEAT_AGE.set(max(0, observed_at - gate.updated_at))
    reason = gate.refusal(job, observed_at)
    if reason:
        return None, reason
    return {**row, 'window': gate.hour(), 'tokens_used': gate.used() + 1}, None


def projection_refusal(tx, owner: dict, depth: int, *, owner_key: str, owner_id: str) -> str | None:
    """Reuse the owner log/projection watermark, but uncertainty cannot grant backlog headroom."""
    from config.batch_pipeline import MERGE_CATCH_UP_DEPTH_DEFAULT

    sequence = owner.get('log_sequence', 0)
    if type(sequence) is not int or sequence < 0:
        return 'projection'
    projected = owner.get('projection_watermark')
    done = 0
    if projected is not None:
        if not isinstance(projected, str) or not projected:
            return 'projection'
        result = tx.get('results', projected)
        done = result.get('log_sequence')
        if (
            result.get('owner_key') != owner_key
            or result.get('owner_id') != owner_id
            or result.get('segment_id') != projected
            or type(done) is not int
            or not 1 <= done <= sequence
            or not isinstance(owner.get('log_tail'), str)
            or not owner['log_tail']
            or ((done == sequence) != (owner['log_tail'] == projected))
        ):
            return 'projection'
    # Turning off fresh-first depth must never turn off the backlog flood guard.
    return 'projection' if sequence - done >= (depth or MERGE_CATCH_UP_DEPTH_DEFAULT) else None
