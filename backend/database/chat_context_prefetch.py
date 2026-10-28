"""Bounded request-only snapshots and fresh, projected fences for shaped context."""

import json
import time

from functools import lru_cache

from database.account_deletion_marker import account_deletion_document
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status
from utils import encryption

RPC_SECONDS = 1.0
FENCE_FIELDS = [
    'id',
    'channel_link_id',
    'link_generation',
    'shaped_context_revision',
    'chat_context_generation',
    'active',
    'uid',
    'generation',
    'wipe_status',
]


@lru_cache(maxsize=1)
def no_retry():
    # Cache the policy only when optional context is actually read. Importing
    # shared chat readers must not eagerly initialize the retry/auth SDK stack.
    from google.api_core.retry import Retry

    return Retry(predicate=lambda error: False)


def _refs(messaging, uid, session_id, link_id):
    refs = [
        messaging.user(uid).collection('chat_sessions').document(session_id),
        messaging.user(uid),
        account_deletion_document(uid, firestore_client=messaging.db),
    ]
    if link_id:
        refs.append(messaging.db.collection('channel_identities').document(link_id))
    return refs


def _batch(messaging, refs, timeout, *, fields=None):
    # BatchGet is unordered. Never zip request references to response order.
    documents = {
        doc.reference.path: doc
        for doc in messaging.db.get_all(refs, field_paths=fields, timeout=timeout, retry=no_retry())
    }
    return [documents[ref.path] for ref in refs]


def _guard(documents, uid, link_id):
    session, user, deletion, *links = documents
    row, account = session.to_dict() or {}, user.to_dict() or {}
    deleting = account_deletion_blocks_access(
        normalize_account_deletion_status(
            marker_exists=deletion.exists, raw_status=(deletion.to_dict() or {}).get('wipe_status')
        )
    )
    if not session.exists or not user.exists or deleting:
        raise PermissionError('Context session or account unavailable')
    if row.get('channel_link_id') != link_id:
        raise PermissionError('Context link changed')
    if link_id:
        link = links[0].to_dict() or {}
        if not link.get('active') or link.get('uid') != uid or link.get('generation') != row['link_generation']:
            raise PermissionError('Context link revoked')
    return row, account


def _fence(row, account, documents):
    return {
        'generation': account.get('chat_context_generation', 0),
        'revision': row.get('shaped_context_revision', 0),
        'incarnations': [doc.create_time for doc in (documents[:2] + documents[3:])],
        'link_id': row.get('channel_link_id'),
        'link_generation': row.get('link_generation'),
    }


def load(messaging, uid, session_id):
    deadline = time.monotonic() + RPC_SECONDS
    ref = messaging.user(uid).collection('chat_sessions').document(session_id)
    row = ref.get(field_paths=['channel_link_id'], timeout=RPC_SECONDS, retry=no_retry()).to_dict() or {}
    link_id = row.get('channel_link_id')
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError()
    documents = _batch(messaging, _refs(messaging, uid, session_id, link_id), remaining)
    row, account = _guard(documents, uid, link_id)
    # Preserve the transactional loader's rejection of malformed empty records.
    # At use, a valid legacy account may project to {} without a generation field.
    if not row or not account:
        raise PermissionError('Context session or account unavailable')
    fence = _fence(row, account, documents)
    state = json.loads(encryption.decrypt(row['shaped_context'], uid)) if row.get('shaped_context') else {}
    if state.get('generation', 0) != fence['generation']:
        state = {}
    return dict(state, generation=fence['generation'], revision=fence['revision'], prefetch_fence=fence)


def validate(messaging, uid, session_id, state, timeout):
    fence = state['prefetch_fence']
    documents = _batch(
        messaging, _refs(messaging, uid, session_id, fence['link_id']), min(timeout, RPC_SECONDS), fields=FENCE_FIELDS
    )
    row, account = _guard(documents, uid, fence['link_id'])
    if _fence(row, account, documents) != fence:
        raise PermissionError('Context generation or revision changed')
