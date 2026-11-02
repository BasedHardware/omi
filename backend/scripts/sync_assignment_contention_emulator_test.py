#!/usr/bin/env python3
"""Real-SDK sync assignment retry and concurrent convergence, emulator only.

The emulator does not deterministically emit a read-time Aborted under load.
Inject that envelope once at its real BatchGet transport boundary, then prove
fresh begin/read/rollback/restart/commit and decoded segment durability. Also
run two simultaneous production adapter calls without injected errors.
"""

import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

if not os.environ.get('FIRESTORE_EMULATOR_HOST'):
    raise SystemExit('FIRESTORE_EMULATOR_HOST required; no cloud fallback')
os.environ.setdefault('GOOGLE_CLOUD_PROJECT', 'demo-sync-assignment')
os.environ.setdefault('ENCRYPTION_SECRET', 'sync_assignment_emulator_synthetic_32_bytes')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google.api_core.exceptions import Aborted
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from database import conversations as db


def main():
    client = firestore.Client(project=os.environ['GOOGLE_CLOUD_PROJECT'], credentials=AnonymousCredentials())
    uid = 'sync-assignment-emulator-' + uuid.uuid4().hex
    user = client.collection('users').document(uid)
    begun = datetime.now(timezone.utc)
    db._sync_conversation_search_index = lambda *args: None
    db.invalidate_people_stats_cache = lambda *args: None

    def chunk(index):
        return {
            'id': 'chunk-' + str(index),
            'started_at': begun + timedelta(seconds=index * 30),
            'finished_at': begun + timedelta(seconds=index * 30 + 9.5),
            'source': 'omi',
            'client_device_id': None,
            'data_protection_level': 'standard',
            'discarded': False,
            'status': 'completed',
            'transcript_segments': [
                {
                    'id': 'segment-' + str(index),
                    'start': 0.0,
                    'end': 9.5,
                    'text': 'Synthetic emulator recording.',
                    'speaker_id': 0,
                    'is_user': False,
                }
            ],
        }

    transport = client._firestore_api._transport
    original = transport._wrapped_methods[transport.batch_get_documents]
    transactions = []
    injected = False

    def aborted_read(request, **kwargs):
        nonlocal injected
        if request.transaction:
            transactions.append(bytes(request.transaction))
            if not injected:
                injected = True
                raise Aborted('synthetic read-time contention')
        return original(request, **kwargs)

    def persist(index):
        return db.assign_sync_conversation(uid, chunk(index), firestore_client=client)

    try:
        # Default-off must preserve the existing failure boundary and write nothing.
        os.environ.pop('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', None)
        transport._wrapped_methods[transport.batch_get_documents] = aborted_read
        try:
            persist(0)
        except Aborted:
            pass
        else:
            raise AssertionError('default-off unexpectedly replayed the read abort')
        assert not list(user.collection('conversations').stream())

        os.environ['SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED'] = 'true'
        injected = False
        transactions.clear()
        persist(0)
        assert len(set(transactions)) == 2, 'retry must use a fresh transaction id'
        transport._wrapped_methods[transport.batch_get_documents] = original
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(persist, [1, 2]))
        # Exact upload replay is idempotent after a retry and concurrent append.
        persist(0)
        rows = [s.to_dict() for s in user.collection('conversations').stream()]
        active = [r for r in rows if not r.get('deleted')]
        assert len(active) == 1
        segments = db._decode_transcript_segments_strict(
            uid, active[0]['transcript_segments'], bool(active[0].get('transcript_segments_compressed'))
        )
        assert sorted(s['id'] for s in segments) == ['segment-0', 'segment-1', 'segment-2']
        print('PASS: default-off failure, fresh transaction retry, concurrent append, replay; 3/3 unique segments')
    finally:
        transport._wrapped_methods[transport.batch_get_documents] = original
        for name in ['conversations', 'sync_assignment']:
            for snap in user.collection(name).stream():
                snap.reference.delete()
        client.close()


if __name__ == '__main__':
    main()
