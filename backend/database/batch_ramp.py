"""Bounded, metadata-only owner-load reads at new admission boundaries."""

from dataclasses import replace
import logging
import time

from prometheus_client import Counter

from config.policy.ramp import OPEN_WINDOW_SECONDS, READ_LIMIT, exclusion_enabled, exclusion_reason, owner_load
from database._client import get_data_plane_firestore_client
from utils.sync.stage import current_stage

logger = logging.getLogger(__name__)
EXCLUDED = Counter(
    'omi_batch_ramp_heavy_owner_excluded_total',
    'New partial-ramp admission decisions routed to legacy by owner load',
    ('reason',),
)


def read_owner_load(uid, *, firestore_client=None, now=None, incoming_audio_seconds=0, stage=None):
    stage = current_stage() if stage is None else stage
    if stage not in {'prod', 'dev'}:
        raise ValueError('ramp owner-load reads require an explicit prod/dev data-plane namespace')
    client = firestore_client if firestore_client is not None else get_data_plane_firestore_client()
    now = time.time() if now is None else now
    jobs = list(
        client.collection(f'batch_pipeline_{stage}_jobs')
        .where('owner_id', '==', uid)
        .where('enqueued_at', '>=', now - OPEN_WINDOW_SECONDS)
        .select(('client_status', 'state', 'enqueued_at', 'duration_seconds'))
        .limit(READ_LIMIT)
        .stream()
    )
    pending = list(
        client.collection('sync_backfill_pending' if stage == 'prod' else 'sync_backfill_pending_dev')
        .where('uid', '==', uid)
        .select(('job_id', 'payload.audio_start_seconds', 'payload.audio_end_seconds'))
        .limit(READ_LIMIT)
        .stream()
    )
    pending_rows = [row.to_dict() or {} for row in pending]
    # claim_next atomically removes the waiting row and installs active_payload.
    # These separate read RPCs can straddle that transition: deduplicate the
    # active job if it was also present in the waiting snapshot.
    active = (
        client.collection('sync_backfill_sequencer' if stage == 'prod' else 'sync_backfill_sequencer_dev')
        .document(uid)
        .get(field_paths=['active_job_id', 'active_payload.audio_start_seconds', 'active_payload.audio_end_seconds'])
        .to_dict()
        or {}
    )
    active_job = active.get('active_job_id')
    if active_job and not any(row.get('job_id') == active_job for row in pending_rows):
        pending_rows.append({'job_id': active_job, 'payload': active.get('active_payload')})
    return owner_load(
        [row.to_dict() or {} for row in jobs],
        pending_rows,
        now,
        incoming_audio_seconds=incoming_audio_seconds,
    )


def ramp_admission_policy(
    uid, policy, *, incoming_audio_seconds=0, firestore_client=None, content_id=None, conversation_id=None
):
    """Filter only a new admission. Callers must honour prior durable owners first.

    Outside a partial ramp or with the kill switch off this does no reads.
    Read failures keep new work on the existing legacy path. They cannot cancel
    or reroute previously accepted batch work.
    """
    if not policy.batch_enabled or not exclusion_enabled(policy.batch_percent):
        return policy
    legacy_policy = replace(
        policy, batch_enabled=False, batch_allowlisted=False, live_record_enabled=False, live_stt_retired=False
    )
    try:
        client = firestore_client
        if content_id or conversation_id:
            stage = current_stage()
            if stage not in {'prod', 'dev'}:
                raise ValueError('ramp ownership reads require an explicit prod/dev namespace')
            client = client if client is not None else get_data_plane_firestore_client()
            user = client.collection('users').document(uid)
            ledger = 'sync_content_ledger' if stage == 'prod' else f'sync_content_ledger_{stage}'
            if content_id:
                receipt = user.collection(ledger).document(content_id).get(field_paths=['dispatch_protocol'])
                if receipt.exists:
                    return policy if (receipt.to_dict() or {}).get('dispatch_protocol') == 'batch_v1' else legacy_policy
            if conversation_id:
                row = user.collection('conversations').document(conversation_id).get(field_paths=['record_lane_owner'])
                owner = (row.to_dict() or {}).get('record_lane_owner')
                if owner:
                    return policy if owner in {'batch_sync_v1', 'batch_live_v1'} else legacy_policy
        load = read_owner_load(uid, firestore_client=client, incoming_audio_seconds=incoming_audio_seconds)
    except Exception:  # bounded admission narrowing; never log account data/errors
        load = None
    reason = exclusion_reason(load)
    if reason is None:
        return policy
    EXCLUDED.labels(
        reason=(
            'open_backlog'
            if reason == 'open_backlog'
            else 'recording_hours' if reason == 'recording_hours' else 'load_unavailable'
        )
    ).inc()
    logger.info('event=batch_ramp_heavy_owner_excluded reason=%s count=1', reason)
    return legacy_policy
