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
        persist(client.transaction(), {'processing_deferred': False})
        assert store.read(uid)['count'] == 0 and store.read(uid)['units'] == 0
        assert not store.items(uid).document('text').get().exists
    print('PASS: atomic totals/update/clear, concurrent consent, completed replay, month and stale-token fences')


if __name__ == '__main__':
    main()
