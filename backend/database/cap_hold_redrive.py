"""Rotating discovery of existing durable choices and unfinished live sources.

No intent is manufactured here. A cursor advances even past blocked owners so
repeated bounded pages eventually cover every pre-existing obligation.
"""

from google.cloud import firestore
from database._client import get_data_plane_firestore_client as get_firestore_client

PAGE = 5
KINDS = {
    'choices': ('processing_backlog', 'processing'),
    'staging': ('stt_cap_holds', ['staging', 'sealing']),
    'cleanup': ('stt_cap_holds', True),
}


def page(kind: str, *, after: str | None = None, firestore_client=None):
    client = firestore_client or get_firestore_client()
    collection, state = KINDS[kind]
    field = 'staging_cleanup' if kind == 'cleanup' else 'state'
    query = client.collection_group(collection).where(
        filter=firestore.FieldFilter(field, 'in' if kind == 'staging' else '==', state)
    )
    query = query.order_by('__name__')
    if after:
        query = query.start_after({'__name__': client.document(after)})
    return list(query.limit(PAGE).stream(timeout=10))


def discover(kind: str):
    client = get_firestore_client()
    cursor = client.collection('cap_hold_redrive').document(kind)
    after = (cursor.get(timeout=10).to_dict() or {}).get('after')
    rows = page(kind, after=after, firestore_client=client)
    # Advance BEFORE awaited work. A killed sweep may revisit this owner on the
    # next rotation; it cannot pin discovery forever on a poison first page.
    cursor.set({'after': rows[-1].reference.path if len(rows) == PAGE else None}, timeout=10)
    return rows
