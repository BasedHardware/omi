"""Owner-scoped field snapshots for exact chat undo, with concurrency fences."""

import base64
from database.action_item_fence import fenced_action_item_commit
from contextlib import nullcontext
from datetime import datetime

from google.cloud import firestore
from database._client import get_firestore_client
from database.people_generation import bump_people_generation
from database.firestore_transaction_retry import run_with_transaction_contention_retry
from utils.conversations.summary_delivery import rearm_after_refusal_clear

COLLECTIONS = {'conversation': 'conversations', 'person': 'people', 'task': 'action_items'}
FIELDS = {
    'conversation': ('structured', 'user_title', 'user_overview', 'user_corrections', 'user_corrections_compressed'),
    'person': ('name', 'aliases', 'updated_at'),
    'task': ('description', 'completed', 'completed_at', 'due_at', 'updated_at', 'deleted', 'deleted_at'),
}


def envelope(snapshot, summary):
    return {'_snapshot': snapshot, '_summary': summary}


def encode(value):
    if isinstance(value, datetime):
        return {'__chat_datetime__': value.isoformat()}
    if isinstance(value, bytes):
        return {'__chat_bytes__': base64.b64encode(value).decode()}
    if isinstance(value, dict):
        return {key: encode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [encode(item) for item in value]
    return value


def decode(value):
    if isinstance(value, dict):
        if set(value) == {'__chat_datetime__'}:
            return datetime.fromisoformat(value['__chat_datetime__'])
        if set(value) == {'__chat_bytes__'}:
            return base64.b64decode(value['__chat_bytes__'])
        return {key: decode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decode(item) for item in value]
    return value


def _ref(uid, kind, target_id, client):
    # IDs are a single opaque document segment, never a path authority.
    if not target_id or '/' in target_id or kind not in COLLECTIONS:
        raise ValueError('Invalid edit target')
    return client.collection('users').document(uid).collection(COLLECTIONS[kind]).document(target_id)


def snapshot(uid, kind, target_id, *, firestore_client=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    row = _ref(uid, kind, target_id, client).get()
    if not row.exists:
        raise LookupError('Edit target not found')
    data = row.to_dict()
    return encode({key: data[key] for key in FIELDS[kind] if key in data})


def restore(uid, kind, target_id, expected, previous, *, firestore_client=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = _ref(uid, kind, target_id, client)

    @firestore.transactional
    def apply(tx):
        row = ref.get(transaction=tx)
        if not row.exists:
            raise PermissionError('Edit target removed')
        data = row.to_dict()
        current = encode({key: data[key] for key in FIELDS[kind] if key in data})
        if current != expected:
            raise PermissionError('Edit target changed; undo refused')
        patch = {key: decode(previous[key]) if key in previous else firestore.DELETE_FIELD for key in FIELDS[kind]}
        if kind == 'conversation' and any(previous.get(key) is not None for key in ('user_title', 'user_overview')):
            patch['summary_due_at'] = None
        elif kind == 'conversation':
            restored = {**data, **{key: decode(previous[key]) if key in previous else None for key in FIELDS[kind]}}
            due = rearm_after_refusal_clear(data, restored)
            if due is not None:
                patch['summary_due_at'] = due
        tx.update(ref, patch)
        if kind == 'person':
            bump_people_generation(tx, ref)

    with fenced_action_item_commit(uid) if kind == 'task' else nullcontext():
        run_with_transaction_contention_retry(client.transaction, apply, operation_name='chat_edit_restore')


def apply_update(uid, kind, target_id, expected, updates, *, firestore_client=None):
    """Commit an owned domain's prepared fields, fencing the observed before state."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = _ref(uid, kind, target_id, client)
    allowed = set(FIELDS[kind])
    if kind == 'conversation':
        allowed.add('summary_due_at')
    if not set(updates) <= allowed or ('summary_due_at' in updates and updates['summary_due_at'] is not None):
        raise ValueError('Unsupported chat edit field')

    @firestore.transactional
    def apply(tx):
        row = ref.get(transaction=tx)
        if not row.exists:
            raise PermissionError('Edit target removed')
        data = row.to_dict()
        if data.get('is_locked') or (kind != 'task' and data.get('deleted')):
            raise PermissionError('Edit target unavailable')
        prior = {key: data[key] for key in FIELDS[kind] if key in data}
        if encode(prior) != expected:
            raise PermissionError('Edit target changed before write')
        patch = dict(updates)
        manual = {
            key: None if value is firestore.DELETE_FIELD else value
            for key, value in updates.items()
            if key in ('user_title', 'user_overview')
        }
        if kind == 'conversation' and any(value is not None for value in manual.values()):
            patch['summary_due_at'] = None
        elif kind == 'conversation' and manual:
            patch.pop('summary_due_at', None)
            due = rearm_after_refusal_clear(data, {**data, **updates, **manual})
            if due is not None:
                patch['summary_due_at'] = due
        tx.update(ref, patch)
        if kind == 'person':
            bump_people_generation(tx, ref)
        # Internal debt retirement is outside the reversible user-field snapshot.
        prior.update({key: value for key, value in updates.items() if key in FIELDS[kind]})
        for key in manual:
            if updates[key] is firestore.DELETE_FIELD:
                prior.pop(key, None)
        return encode(prior)

    with fenced_action_item_commit(uid) if kind == 'task' else nullcontext():
        return run_with_transaction_contention_retry(client.transaction, apply, operation_name='chat_edit_apply')
