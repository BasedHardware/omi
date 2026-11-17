"""Bound only missing-source-marker refusals using the existing recoverable hold."""

import logging
import math

from google.cloud import firestore
from prometheus_client import Counter

from config.policy import ProjectionPolicy, kill_switch
from database.batch_pipeline_projection_protocol import ProjectionBlocked, ProjectionSourceMarkerMissing
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
PROTOCOL_REFUSAL_SECONDS = 15 * 60.0
PROTOCOL_HOLD_REASON = 'missing_source_marker'
PROTOCOL_BLOCK_TYPE = ProjectionSourceMarkerMissing.__name__
PROTOCOL_HOLDS = Counter(
    'omi_batch_projection_protocol_held_total',
    'Committed ordering-only quarantine holds after the missing-source-marker refusal bound',
    ['reason'],
)


def refusal_age(entry, now):
    since = entry.get('projection_blocked_since')
    if (
        entry.get('projection_block_type') != PROTOCOL_BLOCK_TYPE
        or type(since) not in (int, float)
        or not math.isfinite(since)
        or since < 0
    ):
        return None
    return now - since


def bound_protocol_head(store, segment_id, job, entry, binding, now) -> bool:
    """Return True only for a newly committed hold. Retry from durable first refusal.

    No refusal counter: multiple serving roles/processes must not race to spend
    the budget. Normal 20 s pump/serving ticks allow ~45 retries in 15 minutes.
    The transaction rechecks every ordinary fence and the age before advancing.
    """
    if not kill_switch('BATCH_PIPELINE_PROJECTION_PROTOCOL_HEAD_BOUND_ENABLED'):
        return False
    age = refusal_age(entry, now)
    if age is not None and age < PROTOCOL_REFUSAL_SECONDS:
        return False
    policy = ProjectionPolicy.from_dict(job['policy_parts']['projection'])

    @firestore.transactional
    def commit(transaction):
        session = store.session(segment_id, binding, now, policy=policy)
        session.prepare(transaction, protocol_hold=True)
        if session.job.get('shadow'):
            raise ProjectionBlocked('shadow publication forbidden')
        age = refusal_age(session.entry, now)
        if age is None:
            transaction.update(
                session.result_ref,
                {'projection_blocked_since': now, 'projection_block_type': PROTOCOL_BLOCK_TYPE},
            )
            return False
        if age < PROTOCOL_REFUSAL_SECONDS:
            return False
        session.persist(transaction, quarantined=True)
        transaction.update(session.result_ref, {'projection_protocol_hold_reason': PROTOCOL_HOLD_REASON})
        return age

    committed_age = store.run(commit, policy=policy)
    if committed_age is not False:
        try:
            store._mirror(binding)
        except Exception:
            logger.warning('event=jobstore_shadow op=refresh outcome=hook_error site=protocol_head_bound')
        PROTOCOL_HOLDS.labels(reason=PROTOCOL_HOLD_REASON).inc()
        logger.warning(
            'event=batch_projection action=protocol_head_bound outcome=quarantine_held reason=%s age_seconds=%.0f',
            PROTOCOL_HOLD_REASON,
            committed_age,
        )
        record_fallback(
            component='sync_dispatch',
            from_mode='none',
            to_mode='none',
            reason='capability_mismatch',
            outcome='degraded',
        )
    return committed_age is not False
