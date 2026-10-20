#!/usr/bin/env python3
"""Real-SDK sync/live overlap admission race, emulator only.

A same-device live stub with no transcript yet must still be a discovery hint:
the assignment transaction then reads that document, so a listen writer landing
its first transcript concurrently makes Firestore abort the assignment commit,
and the fresh-transaction retry revalidates and adopts the live row instead of
publishing a twin. Inject the abort once at the real BatchGet boundary (the
emulator does not deterministically emit read-time Aborted under load), after
landing the live content, then prove single-row convergence.
"""

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

if not os.environ.get('FIRESTORE_EMULATOR_HOST'):
    raise SystemExit('FIRESTORE_EMULATOR_HOST required; no cloud fallback')
os.environ.setdefault('GOOGLE_CLOUD_PROJECT', 'demo-sync-live-overlap')
os.environ.setdefault('ENCRYPTION_SECRET', 'sync_live_overlap_emulator_synthetic_32_bytes')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google.api_core.exceptions import Aborted
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from database import conversations as db


def main():
    client = firestore.Client(project=os.environ['GOOGLE_CLOUD_PROJECT'], credentials=AnonymousCredentials())
    uid = 'sync-live-overlap-' + uuid.uuid4().hex
    user = client.collection('users').document(uid)
    begun = datetime.now(timezone.utc)
    db._sync_conversation_search_index = lambda *args: None
    db.invalidate_people_stats_cache = lambda *args: None

    stub = user.collection('conversations').document('live')
    stub.set(
        {
            'id': 'live',
            'started_at': begun,
            'finished_at': begun + timedelta(seconds=600),
            'created_at': begun,
            'source': 'omi',
            'client_device_id': 'pendant',
            'is_locked': False,
            'deleted': False,
            'discarded': False,
            'status': 'in_progress',
            # No transcript, no capture provenance yet: the listen writer has
            # created the row but its first segment write has not landed.
            'has_content': False,
            'transcript_segments': [],
            'data_protection_level': 'standard',
        }
    )

    incoming = {
        'id': 'wal',
        'started_at': begun + timedelta(seconds=100),
        'finished_at': begun + timedelta(seconds=109.5),
        'source': 'omi',
        'client_device_id': 'pendant',
        'data_protection_level': 'standard',
        'discarded': False,
        'status': 'completed',
        'transcript_segments': [
            {
                'id': 'segment-wal',
                'start': 0.0,
                'end': 9.5,
                'text': 'Synthetic overlap speech for the same device.',
                'speaker_id': 0,
                'is_user': False,
            }
        ],
    }

    def land_live_content():
        # The listen writer's first transcript lands on the stub while the
        # sync assignment transaction is between its read and its commit.
        stub.update(
            {
                'has_content': True,
                'transcript_segments': [
                    {
                        'id': 'segment-live',
                        'start': 20.0,
                        'end': 29.5,
                        'text': 'Synthetic live speech already captured.',
                        'speaker_id': 0,
                        'is_user': False,
                    }
                ],
                'capture_evidence': {'version': 1, 'origin': 'live'},
            }
        )

    transport = client._firestore_api._transport
    original = transport._wrapped_methods[transport.batch_get_documents]
    transactions = []
    injected = False

    def aborted_read(request, **kwargs):
        nonlocal injected
        if request.transaction:
            transactions.append(bytes(request.transaction))
            if not injected and any(doc.endswith(stub.path) for doc in getattr(request, 'documents', [])):
                injected = True
                land_live_content()
                raise Aborted('synthetic read-time contention')
        return original(request, **kwargs)

    os.environ['SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED'] = 'true'
    os.environ['SYNC_LIVE_OVERLAP_ENABLED'] = 'true'
    os.environ['SYNC_LINEAGE_LIVE_DEDUPE_ENABLED'] = 'off'
    os.environ['SYNC_SAFETY_WAL_DEDUPE_ENABLED'] = 'off'

    try:
        transport._wrapped_methods[transport.batch_get_documents] = aborted_read
        result, created, _ = db.assign_sync_conversation(uid, incoming, firestore_client=client)
        assert injected, 'assignment never read the hinted stub; discovery dropped it'
        assert len(set(transactions)) >= 2, 'no fresh-transaction retry after contention'
        assert not created and result['id'] == 'live', f'adopted row expected, got {result["id"]}'
        segments = db._decode_transcript_segments_strict(
            uid, result['transcript_segments'], bool(result.get('transcript_segments_compressed'))
        )
        texts = sorted(s['text'] for s in segments)
        assert texts == [
            'Synthetic live speech already captured.',
            'Synthetic overlap speech for the same device.',
        ], texts
        stored = {s.id for s in user.collection('conversations').stream()}
        assert stored == {'live'}, f'published a twin row: {stored}'
        saved = stub.get().to_dict()
        assert saved['started_at'] == begun, 'adopted live origin moved'
        # A replay of the same upload stays idempotent on the merged row.
        replay, created, survivors = db.assign_sync_conversation(uid, incoming, firestore_client=client)
        assert not created and not survivors and replay['id'] == 'live'
        print('PASS: coarse hint -> transactional read -> contention retry adopts live row; no twin')
    finally:
        transport._wrapped_methods[transport.batch_get_documents] = original
        for name in ['conversations', 'sync_assignment']:
            for snap in user.collection(name).stream():
                snap.reference.delete()
        client.close()


if __name__ == '__main__':
    main()
