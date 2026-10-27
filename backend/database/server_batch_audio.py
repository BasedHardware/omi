"""Committed original-audio content and bounds for server batch capture."""

import math
from datetime import datetime, timezone

from google.cloud import firestore

from config.server_batch import owned as server_batch_owned
from database._client import get_firestore_client, run_transactional


def note_server_batch_audio(uid: str, conversation_id: str, start: float, end: float, *, firestore_client=None) -> bool:
    """Retain audio-only content after a committed original-audio window.

    Window/reconnect bounds merge monotonically in the same transaction that
    fences empty cleanup. No per-frame reads or transcript fields are added.
    """
    if not (math.isfinite(start) and math.isfinite(end) and start < end):
        raise ValueError('desktop batch requires a nonempty finite capture span')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)

    @firestore.transactional
    def note(transaction):
        snapshot = ref.get(transaction=transaction)
        row = snapshot.to_dict() or {}
        if (
            not snapshot.exists
            or not server_batch_owned(row)
            or not row.get('private_cloud_sync_enabled')
            or row.get('uses_custom_stt')
            or row.get('data_protection_level', 'enhanced') not in {'standard', 'enhanced'}
            or any(row.get(key) for key in ('deleted', 'discarded', 'is_locked'))
        ):
            return False
        first = min(start, row.get('server_batch_audio_start', start))
        last = max(end, row.get('server_batch_audio_end', end))
        transaction.update(
            ref,
            {
                'server_batch_audio_start': first,
                'server_batch_audio_end': last,
                'started_at': datetime.fromtimestamp(first, timezone.utc),
                'finished_at': datetime.fromtimestamp(last, timezone.utc),
                'has_content': True,
                'server_batch_audio_received': True,
            },
        )
        return True

    return run_transactional(client, note)


def close_server_batch_audio(uid: str, conversation_id: str, *, firestore_client=None) -> bool:
    """Publish the archive-close barrier before empty cleanup or batch handoff."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)

    @firestore.transactional
    def close(transaction):
        snapshot = ref.get(transaction=transaction)
        row = snapshot.to_dict() or {}
        if (
            not snapshot.exists
            or not server_batch_owned(row)
            or any(row.get(key) for key in ('deleted', 'discarded', 'is_locked'))
        ):
            return False
        transaction.update(ref, {'server_batch_audio_closed': True})
        return True

    return run_transactional(client, close)


def note_server_batch_audio_received(uid: str, conversation_id: str, *, firestore_client=None) -> bool:
    """Fence lease cleanup once the first frame is buffered, even before commit."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)

    @firestore.transactional
    def received(transaction):
        snapshot = ref.get(transaction=transaction)
        row = snapshot.to_dict() or {}
        if (
            not snapshot.exists
            or not server_batch_owned(row)
            or any(row.get(key) for key in ('deleted', 'discarded', 'is_locked'))
        ):
            return False
        if row.get('server_batch_audio_received') is not True:
            transaction.update(ref, {'server_batch_audio_received': True})
        return True

    return run_transactional(client, received)
