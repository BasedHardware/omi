"""Owner-scoped title-only context. No transcript reads or new composite index."""

from google.cloud.firestore_v1 import FieldFilter
from database._client import get_firestore_client
from database import conversations
from utils.other.list_budget import budgeted_stream_list


def earlier_titles(uid, start, end, budget, *, firestore_client=None):
    client = firestore_client or get_firestore_client()
    query = (
        client.collection('users')
        .document(uid)
        .collection('conversations')
        .where(filter=FieldFilter('started_at', '>=', start))
        .where(filter=FieldFilter('started_at', '<', end))
        .order_by('started_at', direction='DESCENDING')
        .limit(32)
        .select(
            [
                'started_at',
                'structured.title',
                'user_title',
                'data_protection_level',
                'deleted',
                'discarded',
                'recording',
                'home_hidden',
                'is_locked',
                'sync_merged_into',
            ]
        )
    )
    rows = []
    for doc in budgeted_stream_list(query, budget):
        row = {**(doc.to_dict() or {}), 'id': doc.id}
        if any(
            row.get(k) for k in ('deleted', 'discarded', 'recording', 'home_hidden', 'is_locked', 'sync_merged_into')
        ):
            continue
        if row.get('data_protection_level') == 'private':
            continue
        row = conversations.prepare_conversation_for_read(row, uid, firestore_client=client, read_budget=budget)
        if row and (row.get('structured') or {}).get('title'):
            rows.append({'started_at': row['started_at'], 'title': row['structured']['title']})
    return sorted(rows, key=lambda r: r['started_at'])


def bound_people(uid, ids, budget, *, firestore_client=None):
    client = firestore_client or get_firestore_client()
    coll = client.collection('users').document(uid).collection('people')
    refs = [coll.document(pid) for pid in ids[:20]]
    if not refs:
        return []
    budget.check()
    docs = list(client.get_all(refs, field_paths=['name', 'is_dismissed'], timeout=budget.rpc_timeout(), retry=None))
    budget.charge(len(refs))
    return [{**(d.to_dict() or {}), 'id': d.id} for d in docs if d.exists]


def profile(uid, budget, *, firestore_client=None):
    client = firestore_client or get_firestore_client()
    budget.check()
    doc = (
        client.collection('users')
        .document(uid)
        .get(field_paths=['ai_user_profile', 'time_zone'], timeout=budget.rpc_timeout(), retry=None)
    )
    budget.charge(1)
    row = doc.to_dict() or {}
    return {**(row.get('ai_user_profile') or {}), '_timezone': row.get('time_zone') or 'UTC'}
