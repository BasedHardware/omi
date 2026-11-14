"""Uncached, fail-closed hourly provider backlog budget; called inside merge's transaction."""

import logging
import os
from dataclasses import dataclass

from google.api_core.exceptions import Aborted
from prometheus_client import Counter

from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
COMMITTED = Counter('omi_batch_pipeline_backlog_committed_total', 'Observed metered backlog commits')
REFUSED = Counter('omi_batch_pipeline_backlog_refused_total', 'Backlog gate refusals', ['reason'])


@dataclass(frozen=True)
class Gate:
    state: str = 'closed'
    rate_per_hour: int = 0
    reach_seconds: int = 0
    window: int = 0
    tokens_used: int = 0
    updated_at: float = 0.0

    def refusal(self, job: dict, now: float) -> str | None:
        if self.state != 'open':
            return 'closed'
        if not 0 <= now - self.updated_at < 180:
            return 'stale'
        if self.reach_seconds and now - job['capture_at'] - job['duration_seconds'] > self.reach_seconds:
            return 'reach'
        if self.used(now) >= self.rate_per_hour:
            return 'rate'
        return None

    def used(self, now: float) -> int:
        return self.tokens_used if self.window == int(now // 3600) else 0


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
    try:
        gate = Gate(**{name: row[name] for name in Gate.__dataclass_fields__ if name in row})
        if any(
            type(getattr(gate, name)) is not int for name in ('rate_per_hour', 'reach_seconds', 'window', 'tokens_used')
        ):
            return None, 'closed'
        reason = gate.refusal(job, now)
        if gate.reach_seconds < 0 or gate.tokens_used < 0:
            reason = 'closed'
    except (TypeError, ValueError):
        return None, 'closed'
    if reason:
        return None, reason
    return {**row, 'window': int(now // 3600), 'tokens_used': gate.used(now) + 1}, None
