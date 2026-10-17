#!/usr/bin/env python3
"""Local-only legacy-summary migration and concurrent publish contract."""

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_held_audio_emulator_secret_key_32_bytes')
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from utils.sync import cap_hold


def main():
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        raise RuntimeError('requires a loopback Firestore emulator')
    client = firestore.Client(project='demo-held-audio', credentials=AnonymousCredentials())
    uid = f'held-summary-{uuid4().hex}'
    with patch.object(cap_hold, 'get_firestore_client', lambda: client), patch.object(
        cap_hold, 'external_write_fence', lambda uid: nullcontext()
    ):
        batch = client.batch()
        for i in range(205):
            batch.create(
                cap_hold.holds(uid).document(f'old-{i}'), {'state': 'held', 'seconds': 10.25, 'created_at': i + 1}
            )
        batch.commit()
        # Missing summary, then the old (unversioned, drifted) summary both rebuild.
        assert cap_hold.ensure_summary(uid) == {'version': 2, 'seconds': 2101.25, 'count': 205}
        assert all('listed_at' in snap.to_dict() for snap in cap_hold.holds(uid).stream())
        cap_hold.summary_ref(uid).set({'seconds': 0, 'count': 0})
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda i: cap_hold._publish(uid, f'new-{i}', 0.25, {}, 1000 + i), range(8)))
        assert all(results)
        total = cap_hold.summary_ref(uid).get().to_dict()
        assert total == {'version': 2, 'seconds': 2103.25, 'count': 213}, total
        # Duplicate create cannot increment the running summary twice.
        assert not cap_hold._publish(uid, 'new-0', 0.25, {}, 1000)
        assert cap_hold.summary_ref(uid).get().to_dict() == total
        # Real transaction reads before writes and stale/partial receipt idempotence.
        ref = cap_hold.holds(uid).document('old-0')
        row = cap_hold.claim(uid, ref, cap_hold.time.time())
        token = row['lease_token']
        for _ in range(2):
            assert cap_hold.checkpoint(
                uid,
                ref,
                token,
                {
                    'piece_plan': {'a': {'seconds': 0.25}, 'b': {'seconds': 5}},
                    'piece_receipts': {'a': {'state': 'transcribed'}},
                },
            )
        assert cap_hold.summary_ref(uid).get().to_dict()['seconds'] == total['seconds'] - 5.25
        assert not cap_hold.checkpoint(uid, ref, 'stale', {'state': 'completed'})
    client.recursive_delete(client.collection('users').document(uid))
    print('PASS: 205 legacy rows, concurrent lazy rebuild/publish, duplicate and partial retry fences')


if __name__ == '__main__':
    main()
