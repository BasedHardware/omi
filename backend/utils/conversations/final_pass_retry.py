"""Speaker-only durable retries, delivered on the existing authenticated task edge."""

import hashlib
import logging
import math
import time

from config.batch_conversation_speakers import batch_unit_scope
from database.batch_final_pass_retry import FinalPassRetries
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


def _now():
    return time.time()


def scope_key(conversation):
    # Immutable unit/segment membership identifies one obligation. Summary writes
    # or duplicate enrichment calls cannot reset its attempt cap.
    membership = sorted((s.id, batch_unit_scope(s)) for s in conversation.transcript_segments if batch_unit_scope(s))
    return hashlib.sha256(repr(membership).encode()).hexdigest()


def _store():
    return FinalPassRetries()


def _binding():
    from utils.enrichment.outbox import _dispatch_binding

    return _dispatch_binding()


def _wake(key, row):
    from utils.cloud_tasks import enqueue_named_task

    dispatch = row.get('dispatch') or _binding()
    if not dispatch:
        raise RuntimeError('retry_dispatch_unavailable')
    enqueue_named_task(
        dispatch['queue'],
        dispatch['handler'],
        f"bfp-{key}-{row['token']}",
        {'kind': 'batch_final_pass', 'key': key, 'task_token': row['token']},
        audience=dispatch['audience'],
        invoker_sa=dispatch['invoker_sa'],
        schedule_at=math.ceil(row['due_at']),
    )


def _exists(key, row):
    from utils.cloud_tasks import named_task_exists

    dispatch = row.get('dispatch') or _binding()
    return bool(dispatch and named_task_exists(dispatch['queue'], f"bfp-{key}-{row['token']}"))


def _try_wake(key, row):
    try:
        _wake(key, row)
    except Exception as error:
        # The dedicated row is already durable; the existing maintenance route
        # repairs a lost wake without replaying enrichment.
        logger.warning('event=batch_final_pass_retry outcome=wake_failed exception_type=%s', type(error).__name__)
        record_fallback(
            component='stt_selection',
            from_mode='speaker_final_pass_retry',
            to_mode='speaker_retry_sweep',
            reason='enqueue_failed',
            outcome='degraded',
        )


def enqueue(uid, conversation):
    key, row, created = _store().enqueue(uid, conversation.id, scope_key(conversation), _binding(), now=_now())
    if created:
        _try_wake(key, row)
    return {'outcome': row['outcome'] or 'deferred_slot_busy'}


def run_only(uid, conversation_id, expected_scope):
    """Reload current authority and CAS only identity fields; never process notes/effects."""
    from database import conversations as db
    from database.speaker_resolution_updates import persist_speaker_resolution_if_current
    from models.conversation import Conversation
    from utils.conversations import final_pass_batch as batch, speaker_resolution as stage

    raw = db.get_conversation(uid, conversation_id, include_transcript_decode_status=True)
    if not raw or not raw.get('_recovery_transcript_decoded', False):
        return {'outcome': 'failed_revoked'}
    if any(raw.get(field) for field in ('deleted', 'discarded', 'is_locked')):
        return {'outcome': 'failed_revoked'}
    if raw.get('status') != 'completed':
        return {'outcome': 'deferred_not_completed'}
    conversation = Conversation(**raw)
    if scope_key(conversation) != expected_scope:
        return {'outcome': 'failed_revoked'}
    receipt = db.get_manual_speaker_receipt(uid, conversation_id)
    before = conversation.model_dump()
    with batch.identity_only_attempt():
        result = batch.run_batch_final_pass(
            uid,
            conversation,
            receipt,
            load_prints=stage.load_voiceprints_for_resolution,
            apply=stage.apply_speaker_resolution,
            requeue=lambda *args: None,
        )
    if conversation.model_dump() != before:
        if not persist_speaker_resolution_if_current(
            uid, conversation.model_dump(), expected_updated_at=raw.get('updated_at')
        ):
            return {'outcome': 'deferred_revision_changed'}
    return result


def _terminal(result):
    from utils.conversations import final_pass_batch as batch

    if result['outcome'] == 'skipped_ineligible':
        return
    if result['outcome'] == 'success':
        batch.count_terminal('success')
        logger.info('event=batch_final_pass outcome=success reason=speaker_retry')
    else:
        batch._fallback(**result)


def consume(key, token, *, now=None):
    """Claim/settle one wake. Duplicate tokens and live leases do no model work."""
    from utils.conversations.final_pass_errors import error_details

    now = _now() if now is None else now
    store = _store()
    state, claim = store.claim(key, token, now=now)
    if state == 'early':
        _try_wake(key, claim)
        return {'outcome': 'deferred_not_due'}
    if state == 'exhausted':
        _terminal({'outcome': claim['outcome']})
        return {'outcome': claim['outcome']}
    if state != 'claimed':
        return {'outcome': 'stale'}
    try:
        result = run_only(claim['uid'], claim['conversation_id'], claim['scope_key'])
    except Exception as error:
        result = {'outcome': 'deferred_dependency', **error_details(error)}
        logger.warning(
            'event=batch_final_pass_retry outcome=dependency_failed exception_type=%s reason=%s',
            result['exception_type'],
            result['reason'],
        )
    settled = store.settle(key, claim, result['outcome'], now=max(now, _now()))
    if settled is None:
        return {'outcome': 'stale'}
    if not settled['outcome']:
        _try_wake(key, settled)
    else:
        result = {**result, 'outcome': settled['outcome']}
        _terminal(result)
    return result


def sweep(*, now):
    store = _store()
    count = 0
    for snapshot in store.due(now=now):
        observed = snapshot.to_dict()
        row = store.repair(snapshot.id, observed['token'], now=now, wake_exists=_exists(snapshot.id, observed))
        if row:
            _try_wake(snapshot.id, row)
            count += 1
    return count
