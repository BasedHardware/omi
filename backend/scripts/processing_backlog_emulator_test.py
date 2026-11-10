#!/usr/bin/env python3
"""Loopback-only atomic backlog totals, consent replay and lease contention."""

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from database import processing_backlog as store


def main():
    if not os.environ.get('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:')):
        raise RuntimeError('requires a loopback Firestore emulator')
    client = firestore.Client(project='demo-held-audio', credentials=AnonymousCredentials())
    uid = f'processing-backlog-{uuid4().hex}'
    with patch.object(store, 'get_firestore_client', lambda: client), patch.object(
        store, 'external_write_fence', lambda uid, **kwargs: nullcontext()
    ):
        conv = client.collection('users').document(uid).collection('conversations').document('text')
        payload = {
            'processing_deferred': True,
            'started_at': datetime.now(timezone.utc),
            'external_data': {'processing_backlog_estimate': {'seconds': 60, 'units': 3}},
        }

        @firestore.transactional
        def persist(tx, incoming):
            prior = conv.get(transaction=tx).to_dict() or {}
            store.stage_transition(tx, uid, 'text', prior, incoming, firestore_client=client)
            tx.set(conv, incoming, merge=True)

        persist(client.transaction(), payload)
        persist(client.transaction(), payload)
        assert store.read(uid)['count'] == 1 and store.read(uid)['units'] == 3
        payload['external_data']['processing_backlog_estimate']['units'] = 5
        persist(client.transaction(), payload)
        assert store.read(uid)['count'] == 1 and store.read(uid)['units'] == 5

        # Real contention: simultaneous confirmations share exactly one job.
        def choose(i):
            return store.start(uid, period='2026-10', remaining=20, cutoff=100, request_key=f'choice-{i}')['token']

        with ThreadPoolExecutor(max_workers=4) as pool:
            tokens = list(pool.map(choose, range(4)))
        assert len(set(tokens)) == 1
        token = tokens[0]
        owner = store.claim(uid, token, '2026-10')
        assert owner and store.claim(uid, token, '2026-10') is None
        assert not store.checkpoint(uid, token, 'wrong-owner', {'remaining': 999})
        assert store.checkpoint(uid, token, owner, {'state': 'waiting_choice', 'lease_until': 0})
        # A lost response retried after completion must not grant another run.
        assert choose(0) == token and store.read(uid)['state'] == 'waiting_choice'
        store.start(
            uid,
            period='2026-10',
            remaining=0,
            cutoff=100,
            request_key='over-budget-upgrade',
            automatic=True,
            begin=False,
        )
        replay = store.start(
            uid, period='2026-11', remaining=200, cutoff=200, request_key='over-budget-upgrade', automatic=True
        )
        assert replay['token'] == token and store.read(uid)['state'] == 'waiting_choice'
        replacement = store.start(uid, period='2026-11', remaining=20, cutoff=200, request_key='nov-choice')
        assert replacement['token'] != token
        assert not store.checkpoint(uid, token, owner, {'state': 'processing'})
        assert store.claim(uid, replacement['token'], '2026-10') is None
        # An upgrade while an earlier partial choice runs queues consent instead
        # of losing the new allowance or replacing the live worker's lease.
        fresh = replacement['token']
        owner2 = store.claim(uid, fresh, '2026-11')
        queued = store.start(
            uid, period='2026-11', remaining=200, cutoff=300, request_key='upgrade-while-running', automatic=True
        )
        assert queued['token'] == fresh and queued['pending_upgrade']['remaining'] == 200
        assert store.finish(uid, fresh, owner2, '2026-11')
        extended = store.read(uid)
        assert extended['token'] != fresh and extended['remaining'] == 200 and extended['cutoff'] == 300
        assert not store.checkpoint(uid, fresh, owner2, {'remaining': 0})
        # Duplicate webhook cannot requeue consumed intent.
        store.start(
            uid, period='2026-11', remaining=300, cutoff=400, request_key='upgrade-while-running', automatic=True
        )
        assert not store.read(uid)['pending_upgrade']
        owner3 = store.claim(uid, extended['token'], '2026-11')
        store.start(
            uid, period='2026-11', remaining=400, cutoff=500, request_key='second-upgrade-while-running', automatic=True
        )
        assert not store.finish(uid, extended['token'], owner3, '2026-12')
        assert store.read(uid)['state'] == 'waiting_choice' and not store.read(uid)['pending_upgrade']
        persist(client.transaction(), {'processing_deferred': False})
        assert store.read(uid)['count'] == 0 and store.read(uid)['units'] == 0
        assert not store.items(uid).document('text').get().exists
        # Failed paging releases choice only without a durable reservation.
        paused = store.start(uid, period='2026-10', remaining=20, cutoff=100, request_key='pause-proof')
        paused_token = paused['token']
        pause_owner = store.claim(uid, paused_token, '2026-10')
        assert not store.finish(uid, paused_token, 'stale-owner', '2026-10')
        assert store.checkpoint(uid, paused_token, pause_owner, {'reserved': {'id': 'attempt'}})
        assert not store.finish(uid, paused_token, pause_owner, '2026-10')
        assert store.read(uid)['state'] == 'processing'
        assert store.checkpoint(uid, paused_token, pause_owner, {'reserved': {}})
        assert not store.finish(uid, paused_token, pause_owner, '2026-10')
        assert store.read(uid)['state'] == 'waiting_choice'
        # Unreserved failures use the same finish path, including queued intent.
        failing = store.start(uid, period='2026-10', remaining=20, cutoff=100, request_key='error-with-upgrade')
        failing_token = failing['token']
        failing_owner = store.claim(uid, failing_token, '2026-10')
        store.start(
            uid, period='2026-10', remaining=300, cutoff=200, request_key='upgrade-during-page-failure', automatic=True
        )
        assert store.finish(uid, failing_token, failing_owner, '2026-10')
        after_error = store.read(uid)
        assert after_error['state'] == 'processing' and after_error['token'] != failing_token
        assert after_error['remaining'] == 300 and not after_error['pending_upgrade']
        assert not store.finish(uid, failing_token, failing_owner, '2026-10')
    print(
        'PASS: atomic totals/update/clear, concurrent consent, completed replay, month/stale-token fences, queued upgrade intent'
    )


if __name__ == '__main__':
    main()
