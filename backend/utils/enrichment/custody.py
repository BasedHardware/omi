"""Atomic, content-free custody transfer for absorbed sync conversations."""

from typing import Any
import uuid

from google.cloud import firestore

from database.batch_pipeline_privacy import BatchPrivacyBlocked, BatchPrivacyReason, assert_batch_write_allowed


def discard_blocked(document_id: str) -> bool:
    """A deletion/protection fence retires derived work without recreating it."""
    from utils.enrichment import outbox

    client = outbox.get_firestore_client()
    ref = client.collection(outbox.COLLECTION).document(document_id)

    @firestore.transactional
    def discard(transaction):
        row = ref.get(transaction=transaction).to_dict() or {}
        if not row or row.get('dormant'):
            return False
        try:
            assert_batch_write_allowed(client, transaction, row['uid'], conversation_ids=[row['conversation_id']])
        except BatchPrivacyBlocked as error:
            if error.reason in {
                BatchPrivacyReason.CONVERSATION_REDIRECT_CYCLE,
                BatchPrivacyReason.CONVERSATION_REDIRECT_MISSING,
                BatchPrivacyReason.CONVERSATION_FENCE_BUDGET,
            }:
                # Invalid topology is not evidence of user deletion. The real
                # callback defers unresolved redirects without forgetting debt.
                return False
            transaction.delete(ref)
            return True
        return False

    return discard(client.transaction())


def transfer_redirect(document_id: str, token: str, owner: str, canonical: str, *, now: float) -> dict | None:
    """Coalesce into one canonical outbox before retiring the donor.

    Revalidate the same-owner redirect/privacy chain in the transaction. The
    canonical callback still takes its normal snapshot and publication fences;
    transferring metadata is never a summary/provider completion receipt.
    """
    from utils.enrichment import outbox as reprocess

    client = reprocess.get_firestore_client()
    source = client.collection(reprocess.COLLECTION).document(document_id)

    @firestore.transactional
    def transfer(transaction: Any):
        donor = source.get(transaction=transaction).to_dict() or {}
        if donor.get('owner') != owner or donor.get('task_token') != token or donor.get('dormant'):
            return None
        snapshots: dict = {}
        try:
            assert_batch_write_allowed(
                client, transaction, donor['uid'], conversation_ids=[donor['conversation_id']], snapshots=snapshots
            )
        except BatchPrivacyBlocked as error:
            if error.reason in {
                BatchPrivacyReason.CONVERSATION_REDIRECT_CYCLE,
                BatchPrivacyReason.CONVERSATION_REDIRECT_MISSING,
                BatchPrivacyReason.CONVERSATION_FENCE_BUDGET,
            }:
                raise reprocess.FirstSummaryCallbackPending('redirect topology changed') from None
            transaction.delete(source)
            return None
        # The callback's resolution may have raced another merge. Never retire
        # its debt onto a target no longer named by the transactional chain.
        current = donor['conversation_id']
        seen: set[str] = set()
        data: dict = {}
        while isinstance(current, str) and current not in seen:
            seen.add(current)
            data = snapshots.get('conversations', {}).get(current, {})
            if data.get('owner_uid', donor['uid']) != donor['uid'] or data.get('id', current) != current:
                raise reprocess.FirstSummaryCallbackPending('redirect ownership changed')
            if not data.get('deleted'):
                break
            current = data.get('sync_merged_into')
        if current != canonical or current == donor['conversation_id'] or not data:
            raise reprocess.FirstSummaryCallbackPending('redirect target changed')
        target_id = reprocess.key(donor['uid'], canonical)
        target = client.collection(reprocess.COLLECTION).document(target_id)
        previous = target.get(transaction=transaction).to_dict() or {}
        if (
            previous
            and not previous.get('dormant')
            and (previous.get('uid') != donor['uid'] or previous.get('conversation_id') != canonical)
        ):
            raise reprocess.FirstSummaryCallbackPending('canonical custody binding changed')
        pending = dict(previous)
        prior_due = previous.get('due_at')
        pending.update(
            document_id=target_id,
            uid=donor['uid'],
            conversation_id=canonical,
            language=previous.get('language') or donor['language'],
            version=previous.get('version', 0) + 1,
            first_pending_at=min(previous.get('first_pending_at', float('inf')), donor['first_pending_at']),
            due_at=min(float('inf') if prior_due is None else prior_due, donor['due_at']),
            summary_lane=previous.get('summary_lane') or donor.get('summary_lane'),
            effects_only=False,
            summary_repair=False,
            summary_expected_revision=None,
        )
        if donor.get('summary_deadline_at') is not None:
            prior_deadline = previous.get('summary_deadline_at')
            pending['summary_deadline_at'] = min(
                float('inf') if prior_deadline is None else prior_deadline, donor['summary_deadline_at']
            )
            pending['due_at'] = min(pending['due_at'], pending['summary_deadline_at'])
        # A canonical empty-output budget remains terminal. Redirects cannot
        # reset it, nor can they grant another paid processing epoch.
        if previous.get('summary_blocked_reason') == reprocess.EMPTY_BLOCKED_REASON:
            pending.update(dormant=True, due_at=None)
        else:
            pending.update(dormant=False, summary_seen=bool(previous.get('summary_seen')))
        if not reprocess.valid_dispatch_binding(pending.get('dispatch')):
            pending['dispatch'] = donor.get('dispatch')
        if (
            not previous
            or previous.get('dormant')
            or (previous.get('lease_until', 0) <= now and previous.get('task_due_at', float('inf')) > pending['due_at'])
        ):
            pending.update(task_token=uuid.uuid4().hex, task_due_at=pending['due_at'], lease_until=0, owner=None)
            pending.pop('wake_generation', None)
        pending.pop('wake_check_after', None)
        transaction.set(target, pending)
        transaction.delete(source)
        return None if pending.get('dormant') else pending

    return transfer(client.transaction())
