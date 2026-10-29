"""Ordering-only privacy holds; no conversation, ledger, usage or audio writes."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

from google.cloud import firestore

from database.batch_pipeline_privacy import BatchPrivacyReason
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.sync_ledger import LEDGER_RETENTION_DAYS

HOLD_REASONS = frozenset(
    {
        BatchPrivacyReason.ACCOUNT_DELETED,
        BatchPrivacyReason.ACCOUNT_MISSING,
        BatchPrivacyReason.DATA_PROTECTION_CHANGED,
        BatchPrivacyReason.PRIVACY_GENERATION_CHANGED,
        BatchPrivacyReason.RECORDING_PRIVACY_CHANGED,
        BatchPrivacyReason.CONVERSATION_REDIRECT_CYCLE,
        BatchPrivacyReason.CONVERSATION_REDIRECT_MISSING,
        BatchPrivacyReason.CONVERSATION_FENCE_BUDGET,
    }
)


def checkpoint(entry):
    saved = entry.get('projection_privacy_checkpoint') or {}
    return (
        entry.get('protocol_version') == 2
        and entry.get('privacy_quarantine_version') == 1
        and saved.get('version') == 1
        and saved.get('ordering_settled') is True
        and saved.get('protocol_before') in {1, 2}
        and saved.get('state_before') in {'pending', 'persisted', 'ready', 'quarantine_held'}
    )


def _hold_receipt(receipt):
    if receipt and 'privacy_previous_state' not in receipt:
        receipt['privacy_previous_state'] = receipt['state']
        receipt['state'] = 'quarantined'


def hold(store, segment_id, binding, now, reason, *, policy):
    if not isinstance(reason, BatchPrivacyReason) or reason not in HOLD_REASONS:
        raise ProjectionBlocked('unrecognized privacy hold reason')

    @firestore.transactional
    def commit(transaction):
        session = store.session(segment_id, binding, now, policy=policy)
        session.prepare(transaction, replay=False, privacy_refusal=reason)
        if session.job.get('shadow'):
            raise ProjectionBlocked('shadow publication forbidden')
        if session.ledger.get('status') == 'completed' and session.receipt().get('state') == 'ready':
            return False  # Historical completion cannot become a new hold.
        entry = deepcopy(session.entry)
        prior = entry.get('projection_privacy_refusal') or {}
        if checkpoint(entry) and prior.get('reason') == reason.value:
            return False
        existing = bool(session.receipt())
        settled = checkpoint(entry)
        if not settled:
            entry['projection_privacy_checkpoint'] = {
                'version': 1,
                'ordering_settled': True,
                'protocol_before': entry['protocol_version'],
                'state_before': entry['projection_state'],
            }
        _hold_receipt(entry.get('projection'))
        for receipt in (entry.get('projection_parts') or {}).values():
            _hold_receipt(receipt)
        if not entry.get('projection'):
            entry['projection'] = {
                'state': 'quarantined',
                'privacy_control_only': True,
                'conversation_id': None,
                'created': False,
                'speech_seconds': 0.0,
                'held_speech_seconds': None,
                'audio_required': False,
                'enrichment_required': False,
            }
        entry.update(
            protocol_version=2,
            privacy_quarantine_version=1,
            projection_state='quarantine_held',
            projection_privacy_refusal={
                'version': 1,
                'reason': reason.value,
                'held_at': now,
                'obligation_due_at': entry['committed_at'] + 900,
            },
        )
        transaction.set(session.result_ref, entry)
        if not settled and not existing:
            transaction.update(session.owner_ref, {'projection_watermark': segment_id})
            for reference in session.erased_predecessors:
                transaction.update(
                    reference,
                    {'expires_at': datetime.fromtimestamp(now, timezone.utc) + timedelta(days=LEDGER_RETENTION_DAYS)},
                )
        return True

    changed = store.run(commit, policy=policy)
    if changed:
        store._mirror(binding)
    return changed


def resume(store, segment_id, binding, now, *, policy):
    """An explicit replay restores progress only after all ordinary fences pass."""

    @firestore.transactional
    def commit(transaction):
        session = store.session(segment_id, binding, now, policy=policy)
        session.prepare(transaction, replay=False, privacy_replay=True)
        entry = deepcopy(session.entry)
        if not entry.get('projection_privacy_refusal'):
            return entry
        if not checkpoint(entry):
            raise ProjectionBlocked('privacy ordering checkpoint required')
        saved = entry['projection_privacy_checkpoint']
        for receipt in [entry.get('projection') or {}, *(entry.get('projection_parts') or {}).values()]:
            if 'privacy_previous_state' in receipt:
                receipt['state'] = receipt.pop('privacy_previous_state')
        if (entry.get('projection') or {}).get('privacy_control_only'):
            entry.pop('projection')
        entry.pop('projection_privacy_refusal')
        if entry.get('projection'):
            entry.update(protocol_version=saved['protocol_before'], projection_state=saved['state_before'])
            entry.pop('projection_privacy_checkpoint')
            entry.pop('privacy_quarantine_version')
        else:
            # Older binaries must not replay this ordered-but-unassigned unit.
            # The last ordinary assignment clears this checkpoint, without
            # ever moving the owner's watermark back to an older result.
            entry['projection_state'] = 'pending'
        transaction.set(session.result_ref, entry)
        return entry

    entry = store.run(commit, policy=policy)
    store._mirror(binding)
    return entry


def completed_checkpoint_fields(entry, *, quarantined=False):
    if not checkpoint(entry):
        return {}
    return {
        'protocol_version': 2 if quarantined else entry['projection_privacy_checkpoint']['protocol_before'],
        'projection_privacy_checkpoint': None,
        'projection_privacy_refusal': None,
        'privacy_quarantine_version': None,
    }
