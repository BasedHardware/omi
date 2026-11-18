"""Conversation summary persistence and content-scoped retry fences."""

from database import conversations_v3_leases as leases
from utils.conversations.v3 import metrics

import hashlib
import json
from datetime import datetime, timedelta, timezone
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter
from database import conversations, conversations_v3 as store
from database.account_deletion_marker import account_deletion_document
from database.account_deletion_policy import account_deletion_marker_blocks_access
from utils.conversations.v3 import Conflict, policy


def store_summary(uid, cid, token, revision, structured, covers, *, firestore_client=None):
    client = firestore_client or store.get_firestore_client()
    ref, held = store.user_conversations(client, uid).document(cid), leases.lease_ref(client, uid, 'summary-' + cid)
    patch = conversations._prepare_conversation_for_write(  # pyright: ignore[reportPrivateUsage] -- reuse the authoritative encryption codec
        {'structured': structured}, uid, 'enhanced', allow_offload=False
    )

    @firestore.transactional
    def persist(tx):
        snapshot = ref.get(transaction=tx)
        deletion = account_deletion_document(uid, firestore_client=client).get(transaction=tx)
        if account_deletion_marker_blocks_access(
            marker_exists=deletion.exists, raw_status=(deletion.to_dict() or {}).get('status')
        ):
            raise Conflict('account_deletion')
        lease = held.get(transaction=tx).to_dict() or {}
        current = snapshot.to_dict() or {}
        if (
            not snapshot.exists
            or current.get('deleted')
            or current.get('is_locked')
            or snapshot.update_time != revision
            or lease.get('token') != token
            or not lease.get('until')
            or lease['until'] <= datetime.now(timezone.utc)
        ):
            raise Conflict('summary_source_changed')
        if current.get('title_locked'):
            patch['structured']['title'] = (current.get('structured') or {}).get('title', '')
            patch['structured']['emoji'] = (current.get('structured') or {}).get('emoji', '')
        settled = current.get('v3_derived') and current.get('status') != 'in_progress'
        # On-open notes are a notes write too: a row whose background notes failed and the user then
        # opened owes the same single created delivery once it is visible and completed.
        armed = bool(
            settled
            and policy.created_eligible(
                {**current, 'v3_notes_written': True, 'v3_process_failed': False, 'tile_state': 'done'}
            )
        )
        tx.update(
            ref,
            {
                **patch,
                'summary_covers_through': covers,
                **(
                    {'tile_state': 'done', 'v3_process_failed': False, 'summary_retryable': False}
                    if current.get('v3_derived') and current.get('status') != 'in_progress'
                    else {}
                ),
                **(
                    {'title_locked': True}
                    if current.get('v3_derived') and not current.get('home_hidden') and patch['structured'].get('title')
                    else {}
                ),
                **({'v3_notes_written': True} if settled else {}),
                **({'v3_created_pending': True} if armed else {}),
            },
        )
        return armed

    return persist(client.transaction())


def settle_processing(
    uid, cid, token, revision, covers, *, skipped=False, notes=False, content_hash=None, firestore_client=None
):
    """Settle one processing attempt; `notes` marks a completed notes write (arms the created delivery).

    Returns True when this settle armed the conversation-created delivery obligation.
    """
    client = firestore_client or store.get_firestore_client()
    ref = store.user_conversations(client, uid).document(cid)
    held = leases.lease_ref(client, uid, 'summary-' + cid)

    @firestore.transactional
    def settle(tx):
        snapshot = ref.get(transaction=tx)
        row = snapshot.to_dict() or {}
        lease = held.get(transaction=tx).to_dict() or {}
        if lease.get('token') != token or not lease.get('until') or lease['until'] <= datetime.now(timezone.utc):
            raise Conflict('processing_source_changed')
        if not row:
            return False
        if not skipped and not row.get('deleted') and row.get('sync_content_revision') != revision:
            decoded = store.decode_row(uid, snapshot)
            if not content_hash or processing_hash(decoded) != content_hash:
                raise Conflict('processing_source_changed')
        written = bool(notes and not skipped and not row.get('deleted'))
        armed = written and policy.created_eligible(
            {**row, 'v3_notes_written': True, 'v3_process_failed': False, 'v3_process_pending': False}
        )
        tx.update(
            ref,
            {
                'v3_process_pending': False,
                'tile_state': 'done',
                'v3_process_failed': False,
                'v3_process_failure_reason': None,
                'summary_retryable': False,
                **({'summary_covers_through': covers} if not skipped and not row.get('deleted') else {}),
                **(
                    {'title_locked': True}
                    if not skipped and not row.get('home_hidden') and (row.get('structured') or {}).get('title')
                    else {}
                ),
                **({'v3_notes_written': True} if written else {}),
                **({'v3_created_pending': True} if armed else {}),
            },
        )
        return armed

    return settle(client.transaction())


CREATED_CLAIM = timedelta(minutes=5)
CREATED_MAX_ATTEMPTS = 5
CREATED_PAGE = 8


def pending_created(uid, *, firestore_client=None):
    """Owed conversation-created deliveries for one owner (collection-scoped, bounded)."""
    client = firestore_client or store.get_firestore_client()
    return [
        snapshot.id
        for snapshot in store.user_conversations(client, uid)
        .where(filter=FieldFilter('v3_created_pending', '==', True))
        .limit(CREATED_PAGE)
        .stream()
    ]


def claim_created(uid, cid, *, firestore_client=None):
    """Claim one owed delivery for a bounded lease; returns the attempt number or None.

    A row that stopped qualifying (deleted, hidden, locked, discarded, already delivered) drops the
    obligation instead of delivering. A live claim held by another worker is left alone.
    """
    client = firestore_client or store.get_firestore_client()
    ref = store.user_conversations(client, uid).document(cid)

    @firestore.transactional
    def claim(tx):
        snapshot = ref.get(transaction=tx)
        row = snapshot.to_dict() or {}
        if not snapshot.exists or not row.get('v3_created_pending'):
            return None
        now = datetime.now(timezone.utc)
        if not policy.created_eligible(row):
            tx.update(ref, {'v3_created_pending': False, 'v3_created_claim_until': None})
            return None
        if row.get('v3_created_claim_until') and row['v3_created_claim_until'] > now:
            return None
        attempt = int(row.get('v3_created_attempts') or 0) + 1
        if attempt > CREATED_MAX_ATTEMPTS + 1:
            # The final delivery attempt drops failures itself; this bounds a row whose read or
            # claim keeps failing outside the delivery so it never cycles the owner's wakes forever.
            tx.update(ref, {'v3_created_pending': False, 'v3_created_claim_until': None})
            return None
        tx.update(ref, {'v3_created_attempts': attempt, 'v3_created_claim_until': now + CREATED_CLAIM})
        return attempt

    return claim(client.transaction())


def finish_created(uid, cid, attempt, *, delivered, dropped=False, firestore_client=None):
    """Record the delivery, drop an obligation the row no longer qualifies for, or release the claim.

    Fenced by the attempt number so a superseded claimant cannot settle a successor's attempt.
    """
    client = firestore_client or store.get_firestore_client()
    ref = store.user_conversations(client, uid).document(cid)

    @firestore.transactional
    def finish(tx):
        snapshot = ref.get(transaction=tx)
        row = snapshot.to_dict() or {}
        if not snapshot.exists or int(row.get('v3_created_attempts') or 0) != attempt:
            return False
        if delivered:
            tx.update(
                ref,
                {
                    'v3_created_pending': False,
                    'v3_created_claim_until': None,
                    'v3_created_delivered_at': datetime.now(timezone.utc),
                },
            )
        elif dropped:
            tx.update(ref, {'v3_created_pending': False, 'v3_created_claim_until': None})
        else:
            tx.update(ref, {'v3_created_claim_until': None})
        return True

    return finish(client.transaction())


def processing_hash(row):
    return hashlib.sha256(
        json.dumps(
            {
                'segments': (row or {}).get('transcript_segments') or [],
                'manual_end': bool((row or {}).get('manual_end')),
                'kind': (row or {}).get('kind') or 'conversation',
            },
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()


def begin_processing(uid, row, token, *, force=False, firestore_client=None):
    client = firestore_client or store.get_firestore_client()
    ref = store.user_conversations(client, uid).document(row['id'])
    held = leases.lease_ref(client, uid, 'summary-' + row['id'])
    fingerprint = processing_hash(row)

    @firestore.transactional
    def begin(tx):
        current = ref.get(transaction=tx).to_dict() or {}
        lease = held.get(transaction=tx).to_dict() or {}
        if lease.get('token') != token or lease.get('until', datetime.min.replace(tzinfo=timezone.utc)) <= datetime.now(
            timezone.utc
        ):
            raise Conflict('lease_lost')
        if not current or current.get('deleted') or current.get('is_locked'):
            return False
        attempts = (
            current.get('v3_process_attempts', 0)
            if not force and current.get('v3_process_fingerprint') == fingerprint
            else 0
        )
        if attempts >= 2:
            tx.update(ref, failure_patch(retryable=bool(row.get('transcript_segments')), reason='attempts_exhausted'))
            return 'failed' if not current.get('v3_process_failed') else False
        tx.update(
            ref,
            {
                'v3_process_fingerprint': fingerprint,
                'v3_process_attempts': attempts + 1,
                'v3_process_failed': False,
                'v3_process_failure_reason': None,
                'summary_retryable': False,
                'tile_state': 'writing',
                'status': 'processing',
                'v3_process_pending': True,
            },
        )
        return True

    result = begin(client.transaction())
    if result == 'failed':
        metrics.terminal_failure('attempts_exhausted')
    return result is True


def failure_patch(*, retryable=True, reason='processing'):
    return {
        'status': 'completed',
        'tile_state': 'failed',
        'summary_retryable': retryable,
        'v3_process_pending': False,
        'v3_process_failed': True,
        'v3_process_failure_reason': reason,
    }


def fail_processing(uid, cid, token, revision, *, content_hash=None, retryable=True, firestore_client=None):
    client = firestore_client or store.get_firestore_client()
    ref = store.user_conversations(client, uid).document(cid)
    held = leases.lease_ref(client, uid, 'summary-' + cid)

    @firestore.transactional
    def fail(tx):
        snapshot = ref.get(transaction=tx)
        row = snapshot.to_dict() or {}
        lease = held.get(transaction=tx).to_dict() or {}
        if lease.get('token') != token or not lease.get('until') or lease['until'] <= datetime.now(timezone.utc):
            raise Conflict('lease_lost')
        if not row or row.get('deleted'):
            return False
        if row.get('is_locked'):
            tx.update(ref, {'v3_process_pending': False, 'tile_state': 'done', 'v3_process_failed': False})
            return False
        if row.get('sync_content_revision') != revision:
            if not content_hash or processing_hash(store.decode_row(uid, snapshot)) != content_hash:
                raise Conflict('processing_source_changed')
        tx.update(ref, failure_patch(retryable=retryable))
        return not row.get('v3_process_failed')

    changed = fail(client.transaction())
    if changed:
        metrics.terminal_failure('processing')
    return changed
