"""Repair a missing Home summary obligation through existing delivery policy."""

import math
import time

from google.cloud import firestore

from database import rpc_deadline
from database.batch_pipeline_privacy import BatchPrivacyBlocked, assert_batch_write_allowed
from database.batch_summary_debt import verify_projection_finalization
from services.home_health_review import (
    CARD_FIELDS,
    METADATA_FIELDS,
    hidden_for_review,
    protected_for_review,
    positive_revision,
)
from utils.conversations import summary_delivery
from utils.conversations.fragment_visibility import held_for_notes
from utils.enrichment import age_gate, outbox
from utils.summary_quality import safe_body

GENERATION_FIELDS = (
    'record_projection_revision',
    'sync_content_revision',
    'finalization_job_id',
    'finalization_revision',
)
DISCOVERY_FIELDS = tuple(dict.fromkeys((*METADATA_FIELDS, 'content_word_units', *GENERATION_FIELDS)))
APPLY_METADATA_FIELDS = (*DISCOVERY_FIELDS, 'summary_lane')
APPLY_CARD_FIELDS = (*CARD_FIELDS, 'structured.sections')


def generation(row):
    return tuple(row.get(key) for key in GENERATION_FIELDS)


def candidate(row, *, now):
    """Cheap scan fence. The masked survey can admit a candidate for rechecking only."""
    return _eligible_metadata(row, now=now) and _missing_summary(row)


def _eligible_metadata(row, *, now):
    created = age_gate.timestamp(row.get('created_at'))
    finished = age_gate.timestamp(row.get('finished_at'))
    units = row.get('content_word_units')
    return bool(
        summary_delivery.projection_debt_enabled()
        and row.get('record_lane_owner') == 'batch_live_v1'
        and row.get('status') == 'completed'
        and not protected_for_review(row)
        and not held_for_notes(row, now=now)
        and not row.get('deleted')
        and not row.get('record_upload_failed')
        and not row.get('summary_retryable')
        and row.get('finalization_status') not in {'blocked_byok', 'dead_letter'}
        and (row.get('finalization_job_id') or row.get('finalization_status') not in {'queued', 'leased'})
        and row.get('has_content') is True
        and not row.get('record_transcription_empty')
        and type(units) in (int, float)
        and math.isfinite(units)
        and 0 < units
        and positive_revision(row.get('record_projection_revision'))
        and positive_revision(row.get('sync_content_revision'))
        and row.get('summary_output_present') is False
        and not row.get('summary_completed_at')
        and not row.get('notes_written_at')
        and row.get('summary_due_at') is None
        and row.get('summary_blocked_reason') is None
        and created is not None
        and created <= now
        and finished is not None
        and finished <= now - summary_delivery.deadline_seconds()
        and not age_gate.expired({'first_pending_at': _pending(row, now)}, row.get('created_at'), now=now)
    )


def _missing_summary(row):
    structured = row.get('structured')
    return bool(
        (structured is None or isinstance(structured, dict))
        and not hidden_for_review(row)
        and row.get('user_title') is None
        and row.get('user_overview') is None
        and not safe_body(summary_delivery.field(structured, 'gist')).strip()
        and not summary_delivery.present(structured)
        and not summary_delivery.intentional_short_clip_minimum(row)
    )


def _pending(row, now):
    accepted = age_gate.timestamp(row.get('summary_first_pending_at'))
    if accepted is not None and accepted <= now:
        return accepted
    return age_gate.timestamp(row.get('finished_at'))


def commit(client, transaction, ref, uid, expected, *, now):
    """Recheck all fences in the conflict set before updating scheduling metadata."""
    current = ref.get(transaction=transaction, field_paths=APPLY_METADATA_FIELDS)
    row = current.to_dict() or {}
    if not current.exists or generation(row) != expected or not _eligible_metadata(row, now=now):
        return 'superseded'
    row['id'] = ref.id
    try:
        assert_batch_write_allowed(client, transaction, uid, conversation_ids=(ref.id,), allow_token_mint=False)
    except BatchPrivacyBlocked:
        return 'privacy_refused'

    user = ref.parent.parent.get(transaction=transaction, field_paths=('byok.active',))
    byok = (user.to_dict() or {}).get('byok')
    if not user.exists or (byok is not None and (not isinstance(byok, dict) or byok.get('active'))):
        return 'provider_refused'
    card = ref.get(transaction=transaction, field_paths=APPLY_CARD_FIELDS)
    row.update(card.to_dict() or {})
    if not card.exists or not _missing_summary(row):
        return 'superseded'
    verified, proof = verify_projection_finalization(uid, client, transaction, row)
    if not verified:
        return 'finalization_refused'
    existing = client.collection(outbox.COLLECTION).document(outbox.key(uid, ref.id))
    if existing.get(transaction=transaction, field_paths=()).exists:
        return 'outbox_owned'
    if proof is not None:
        row['summary_projection_finalization'] = proof
    row['summary_first_pending_at'] = _pending(row, now)
    if row.get('summary_lane') not in {'live', 'batch', 'fresh', 'backfill', 'integration'}:
        row['summary_lane'] = 'batch'
    if not summary_delivery.stamp_projection_debt(row, now=now, allow_existing_title=True):
        return 'policy_refused'
    patch = {
        'summary_title_provenance': row['summary_title_provenance'],
        'summary_first_pending_at': row['summary_first_pending_at'],
        'summary_due_at': row['summary_due_at'],
        'summary_lane': row['summary_lane'],
    }
    if proof is not None:
        patch['summary_projection_finalization'] = proof
    transaction.update(ref, patch)
    return 'armed'


def arm(client, ref, uid, expected, *, deadline, execute_before):
    @firestore.transactional
    def transaction_work(transaction):
        now = time.time()
        if now >= execute_before:
            return 'deadline_reached'
        return commit(client, transaction, ref, uid, expected, now=now)

    rpc_deadline.bind_firestore_client(client)
    cutoff = min(deadline, rpc_deadline.now() + max(0, execute_before - time.time()))
    if cutoff <= rpc_deadline.now():
        return 'deadline_reached'
    try:
        with rpc_deadline.rpc_deadline(cutoff):
            return transaction_work(client.transaction(max_attempts=3))
    except rpc_deadline.RpcDeadlineExceeded:
        return 'deadline_reached'
