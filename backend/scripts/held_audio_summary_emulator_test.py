#!/usr/bin/env python3
"""Local-only legacy-summary migration and concurrent publish contract."""

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_held_audio_emulator_secret_key_32_bytes')
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.query import Query
from google.cloud.firestore_v1.transaction import Transaction
from database.legal_holds import DestructiveOperationInProgress
from utils.sync import cap_hold, live_cap_manifest
from utils.sync.live_cap_publication import Publication


def main():
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        raise RuntimeError('requires a loopback Firestore emulator')
    client = firestore.Client(project='demo-held-audio', credentials=AnonymousCredentials())
    uid = f'held-summary-{uuid4().hex}'
    with patch.object(cap_hold, 'get_firestore_client', lambda: client), patch.object(
        cap_hold, 'external_write_fence', lambda uid: nullcontext()
    ):
        # More than two migration pages, seeded below Firestore's write limit.
        for start in range(0, 805, 400):
            batch = client.batch()
            for i in range(start, min(start + 400, 805)):
                batch.create(
                    cap_hold.holds(uid).document(f'old-{i:04d}'),
                    {'state': 'held', 'seconds': 10.25, 'created_at': i + 1},
                )
            batch.commit()

        fence_calls = 0

        @contextmanager
        def block_after_first_page(uid):
            nonlocal fence_calls
            fence_calls += 1
            if fence_calls > 2:
                raise DestructiveOperationInProgress('synthetic account deletion')
            yield

        # A creator cannot publish while migration is incomplete. The first
        # page commits; deletion fencing rejects the next and leaves a cursor.
        with patch.object(cap_hold, 'external_write_fence', block_after_first_page):
            try:
                cap_hold._publish(uid, 'blocked-new', 0.25, {}, 1000)
            except DestructiveOperationInProgress:
                pass
            else:
                raise AssertionError('publication crossed the deletion fence')
        partial = cap_hold.summary_ref(uid).get().to_dict()
        assert partial['build_owner'] and partial['build_lease_until'] > cap_hold.time.time()
        assert {key: value for key, value in partial.items() if key not in {'build_owner', 'build_lease_until'}} == {
            'version': 1,
            'building': True,
            'cursor': 'old-0399',
            'partial_seconds': 4100.0,
            'partial_count': 400,
        }, partial
        assert not cap_hold.holds(uid).document('blocked-new').get().exists
        assert sum('listed_at' in snap.to_dict() for snap in cap_hold.holds(uid).stream()) == 400
        with patch.object(cap_hold, 'external_write_fence', block_after_first_page):
            try:
                cap_hold.ensure_summary(uid)
            except DestructiveOperationInProgress:
                pass
            else:
                raise AssertionError('retry crossed the deletion fence')
        assert cap_hold.summary_ref(uid).get().to_dict() == partial

        # Simulate the interrupted builder's lease expiring before takeover.
        cap_hold.summary_ref(uid).update({'build_lease_until': 0})
        query_pages, writes_per_commit = [], []
        original_stream, original_commit = Query.stream, Transaction._commit

        def bounded_stream(query, *args, **kwargs):
            if kwargs.get('transaction') is not None:
                assert query._limit == 400
                query_pages.append(query._start_at)
            return original_stream(query, *args, **kwargs)

        def bounded_commit(tx):
            writes_per_commit.append(len(tx._write_pbs))
            assert len(tx._write_pbs) <= 401
            return original_commit(tx)

        def initialize_or_publish(i):
            if i < 4:
                assert cap_hold.ensure_summary(uid)['version'] == 2
                return True
            return cap_hold._publish(uid, f'new-{i - 4}', 0.25, {}, 1000 + i)

        # Actual Firestore transactions contend on the summary and resume the
        # persisted cursor while creators wait, then publish atomic deltas.
        with patch.object(Query, 'stream', bounded_stream), patch.object(Transaction, '_commit', bounded_commit):
            with ThreadPoolExecutor(max_workers=4) as pool:
                assert all(pool.map(initialize_or_publish, range(12)))
        assert query_pages and all(cursor is not None for cursor in query_pages)
        assert writes_per_commit and max(writes_per_commit) <= 401
        assert all('listed_at' in snap.to_dict() for snap in cap_hold.holds(uid).stream())
        total = cap_hold.summary_ref(uid).get().to_dict()
        assert total == {'version': 2, 'seconds': 8253.25, 'count': 813}, total
        # Drifted version-1 summaries without a rebuild marker start afresh.
        cap_hold.summary_ref(uid).set({'version': 1, 'seconds': 0, 'count': 0})
        assert cap_hold.ensure_summary(uid) == total
        # Ready summaries need only their single document read; no fence/query.
        with patch.object(
            cap_hold, 'external_write_fence', side_effect=AssertionError('unexpected fence')
        ), patch.object(cap_hold, 'holds', side_effect=AssertionError('unexpected holds query')):
            assert cap_hold.ensure_summary(uid) == total
        # Duplicate create cannot increment the running summary twice.
        assert not cap_hold._publish(uid, 'new-0', 0.25, {}, 1000)
        assert cap_hold.summary_ref(uid).get().to_dict() == total
        # Real transaction reads before writes and stale/partial receipt idempotence.
        ref = cap_hold.holds(uid).document('old-0000')
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
        # A minute is immutable and born sealed, immediately claimable. Retry
        # lookup must also respect purged receipts after recovery deletes audio.
        uploads = []
        with patch.object(live_cap_manifest, 'get_firestore_client', lambda: client), patch.object(
            live_cap_manifest, 'external_write_fence', lambda uid, **kwargs: nullcontext()
        ), patch.object(
            cap_hold, 'upload_held_audio', side_effect=lambda *a, **k: uploads.append(a) or {'audio_path': 'fake'}
        ):
            before = cap_hold.summary_ref(uid).get().to_dict()
            source = Publication(uid)
            live_cap_manifest.publish(uid, 'unused', source, {'timestamp': 1000}, 60)
            live_total = cap_hold.summary_ref(uid).get().to_dict()
            assert live_total['seconds'] == before['seconds'] + 60
            assert live_total['count'] == before['count'] + 1
            ref = cap_hold.holds(uid).document(source.identity)
            assert cap_hold.claim(uid, ref, cap_hold.time.time())
            live_cap_manifest.publish(uid, 'unused', source, {'timestamp': 1000}, 60)
            ref.set({'state': 'purged', 'live_custody_version': 4})
            live_cap_manifest.publish(uid, 'unused', source, {'timestamp': 1000}, 60)
            assert len(uploads) == 1
            assert cap_hold.summary_ref(uid).get().to_dict() == live_total
    client.recursive_delete(client.collection('users').document(uid))
    print(
        'PASS: 805 legacy rows, paged concurrent rebuild/publish, deletion/retry fences, sealed publication/lease handoff and purged retry'
    )


if __name__ == '__main__':
    main()
