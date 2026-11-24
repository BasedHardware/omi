"""Verify bound finalizer custody before arming batch projection summary debt."""

import logging

from google.cloud import firestore
from database.conversation_finalization_schema import FINALIZATION_JOBS_COLLECTION
from utils.conversations import summary_delivery as delivery

logger = logging.getLogger(__name__)


def arm_projection_summary(uid, client, transaction, payload, current):
    """Read the bound job before assignment writes; content and proof commit together.

    A capture handoff retains finalization_job_id (and a stale queued status).
    Never infer that this generation finished from the conversation's lifecycle
    alone. Bind the proof to both job id and revision so a new finalizer restores
    the ordinary generation fence. This creates no task: projection and repair
    continue using the same conversation-keyed enrichment outbox.

    Unbound rows retain the existing projection-debt policy; no finalizer
    custody exception is minted. Canonical orphan completion supports that
    shape without creating a finalization job.
    """
    if (
        not delivery.projection_debt_enabled()
        or payload.get('record_lane_owner') != 'batch_live_v1'
        or payload.get('status') != 'completed'
        or not payload.get('transcript_segments')
        or (payload.get('record_projection_revision') or 0) <= ((current or {}).get('record_projection_revision') or 0)
        or payload.get('summary_completed_at')
        or payload.get('summary_output_present')
    ):
        return
    verified, proof = verify_projection_finalization(uid, client, transaction, payload)
    if not verified:
        return
    if proof is not None:
        payload['summary_projection_finalization'] = proof
    # Assignment has already staged this invalidation. DELETE_FIELD is truthy;
    # eligibility must describe the committed row, not mistake the sentinel
    # for an active local-processing projection.
    candidate = dict(payload)
    if candidate.get('client_processing') is firestore.DELETE_FIELD:
        candidate.pop('client_processing')
    delivery.stamp_projection_debt(candidate)
    # Literal sites keep these writes in the reviewed lifecycle inventory.
    if 'summary_title_provenance' in candidate:
        payload['summary_title_provenance'] = candidate['summary_title_provenance']
    if 'summary_first_pending_at' in candidate:
        payload['summary_first_pending_at'] = candidate['summary_first_pending_at']
    if 'summary_due_at' in candidate:
        payload['summary_due_at'] = candidate['summary_due_at']
    if 'summary_lane' in candidate:
        payload['summary_lane'] = candidate['summary_lane']


def verify_projection_finalization(uid, client, transaction, row):
    """Return whether this generation is unbound or proved terminal, and its proof."""
    job_id = row.get('finalization_job_id')
    if job_id is not None and (not isinstance(job_id, str) or '/' in job_id):
        logger.info('event=batch_summary_debt phase=precommit outcome=refused reason=finalizer_not_eligible')
        return False, None
    if not job_id:
        return True, None
    job = client.collection(FINALIZATION_JOBS_COLLECTION).document(job_id).get(transaction=transaction).to_dict() or {}
    revision = row.get('finalization_revision')
    if not (
        type(revision) is int
        and revision > 0
        and job.get('uid') == uid
        and job.get('conversation_id') == row['id']
        and job.get('finalization_revision') == revision
        and job.get('status') == 'completed'
        and job.get('terminal_outcome') == 'success'
        and job.get('fanout_status') == 'completed'
        and not job.get('requires_byok')
    ):
        reason = (
            'byok_required'
            if job.get('requires_byok')
            else 'missing_finalizer' if not job else 'finalizer_not_eligible'
        )
        # This is an eligibility observation, not a durable outcome: a
        # transaction retry can observe the same refusal more than once.
        logger.info('event=batch_summary_debt phase=precommit outcome=refused reason=%s', reason)
        return False, None
    return True, {'job_id': job_id, 'revision': revision}
