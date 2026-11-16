"""Bounded authoritative photo evidence for v3 notes, including transactional fences."""

from database._client import get_firestore_client
from database.conversations import prepare_photo_for_read

LIMIT = 128


def read(uid, cid, *, transaction=None, firestore_client=None):
    client = firestore_client or get_firestore_client()
    query = client.collection('users').document(uid).collection('conversations').document(cid).collection('photos')
    query = query.order_by('__name__').limit(LIMIT)
    photos, cursor = [], None
    while True:
        page = query.start_after(cursor) if cursor is not None else query
        snapshots = list(page.stream(transaction=transaction))
        photos.extend(photo for doc in snapshots if (photo := prepare_photo_for_read(doc.to_dict(), uid)) is not None)
        if len(snapshots) < LIMIT:
            return photos
        cursor = snapshots[-1]
