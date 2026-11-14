"""Uncached, fail-closed hourly provider backlog budget; called inside merge's transaction."""

import logging
import math
import os
from dataclasses import dataclass

from google.api_core.exceptions import Aborted
from prometheus_client import Counter

from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
COMMITTED = Counter('omi_batch_pipeline_backlog_committed_total', 'Observed metered backlog commits')
REFUSED = Counter('omi_batch_pipeline_backlog_refused_total', 'Backlog gate refusals', ['reason'])


FIELDS = ('state', 'rate_per_hour', 'reach_seconds', 'window', 'tokens_used', 'updated_at')


def _number(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


@dataclass(frozen=True)
class Gate:
    state: str
    rate_per_hour: int
    reach_seconds: int  # 0 means no reach limit.
    window: int
    tokens_used: int
    updated_at: float

    @classmethod
    def parse(cls, row: dict) -> 'Gate | None':
        """Every field is required and nothing else is allowed: a partial document must not reset the budget."""
        if set(row) != set(FIELDS):
            return None
        gate = cls(**row)
        counts = (gate.rate_per_hour, gate.reach_seconds, gate.window, gate.tokens_used)
        if any(type(value) is not int or value < 0 for value in counts):
            return None
        if gate.state not in ('open', 'closed') or not _number(gate.updated_at):
            return None
        return gate

    def refusal(self, job: dict, now: float) -> str | None:
        if self.state != 'open':
            return 'closed'
        if not 0 <= now - self.updated_at < 180:
            return 'stale'
        capture, duration = job.get('capture_at'), job.get('duration_seconds')
        if not (_number(capture) and _number(duration) and duration >= 0):
            return 'job'
        if self.reach_seconds and now - capture - duration > self.reach_seconds:
            return 'reach'
        if self.used(now) >= self.rate_per_hour:
            return 'rate'
        return None

    def hour(self, now: float) -> int:
        """The budget hour never moves backward: a retried body or a slow clock spends from the stored hour."""
        return max(self.window, int(now // 3600))

    def used(self, now: float) -> int:
        return self.tokens_used if self.hour(now) == self.window else 0


def read(tx, job: dict, now: float, source: str) -> tuple[dict | None, str | None]:
    """Return the token write, or a bounded refusal. Never refresh the operator heartbeat."""
    if os.getenv('BATCH_PIPELINE_PROVIDER_BACKLOG_RELEASE_ENABLED', '').strip().lower() == 'false':
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
    reason = gate.refusal(job, now)
    if reason:
        return None, reason
    return {**row, 'window': gate.hour(now), 'tokens_used': gate.used(now) + 1}, None
