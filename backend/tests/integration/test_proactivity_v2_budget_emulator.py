"""Loopback-only real Firestore transaction proof, run through backend/test.sh."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from urllib.parse import urlparse
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from config.proactivity_v2 import AttemptEnvelope, ProactivityDenied
from database import proactivity as ledger
from database.proactivity_budget import BudgetAuthority


class Lease:
    # Independent Redis instances deliberately prove dollars cannot depend on the lease.
    def set(self, *args, **kwargs):
        return True

    def eval(self, *args):
        return 1


def test_concurrent_instances_cannot_exceed_shared_daily_cap():
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if urlparse(f'//{host}').hostname not in {'127.0.0.1', 'localhost', '::1'}:
        pytest.fail('A loopback FIRESTORE_EMULATOR_HOST is required')
    client = firestore.Client(project='demo-proactivity-spine', credentials=AnonymousCredentials())
    now = datetime.now(timezone.utc)
    uid = uuid4().hex
    user = client.collection('users').document(uid)
    user.set(
        {
            'subscription': {'plan': 'plus', 'current_period_end': (now + timedelta(days=2)).timestamp()},
            'mentor_notification_frequency': 3,
        }
    )
    user.collection('action_items').document('synthetic').set({'description': 'synthetic fixture'})
    producers = ('conversation_mentor_v2', 'commitment_followup')
    for name in producers:
        client.collection(ledger.CONTROLS).document(name).set({'version': 1, 'state': 'enabled', 'checked_at': now})
    items = [
        ledger.claim_item(
            uid=uid,
            producer=name,
            source_kind='action_item',
            source_id='synthetic',
            source_revision='1',
            source_event_id='due',
            firestore_client=client,
            now=now,
        )
        for name in producers
    ]
    barrier = Barrier(2)

    def reserve(item):
        authority = BudgetAuthority(firestore_client=client, redis_client=Lease(), clock=lambda: now)
        barrier.wait(timeout=10)
        try:
            return authority.reserve(
                uid=uid,
                item_id=item['item_id'],
                producer=item['producer'],
                call_id=str(uuid4()),
                envelope=AttemptEnvelope('openai', 'gpt-6-luna', 'synthetic', 40000, 'fingerprint', 'generate'),
            )
        except ProactivityDenied as exc:
            return exc.reason

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, items))
    accepted = [result for result in results if not isinstance(result, str)]
    assert len(accepted) == 1, results
    assert 'budget_exhausted' in results
    balance = user.collection(ledger.DAYS).document(now.strftime('%Y-%m-%d')).get().to_dict()
    assert balance['charged_micro_usd'] == 40000
    # A restarted process and completely fresh lease cannot refund the committed hold.
    authority = BudgetAuthority(firestore_client=client, redis_client=Lease(), clock=lambda: now)
    winner = accepted[0]
    assert authority.release_unsent(reservation=winner)
    assert authority.release_unsent(reservation=winner)
    assert user.collection(ledger.DAYS).document(winner.day).get().to_dict()['charged_micro_usd'] == 0
    client.close()


def test_feed_pagination_and_source_purge(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if urlparse(f'//{host}').hostname not in {'127.0.0.1', 'localhost', '::1'}:
        pytest.fail('A loopback FIRESTORE_EMULATOR_HOST is required')
    client = firestore.Client(project='demo-proactivity-spine', credentials=AnonymousCredentials())
    now = datetime.now(timezone.utc)
    uid = uuid4().hex
    user = client.collection('users').document(uid)
    user.set({'subscription': {'plan': 'plus', 'current_period_end': (now + timedelta(days=2)).timestamp()}})
    source = user.collection('action_items').document('synthetic')
    source.set({'description': 'synthetic'})
    client.collection(ledger.CONTROLS).document('commitment_followup').set(
        {'version': 1, 'state': 'enabled', 'checked_at': now}
    )
    items = []
    for index in range(3):
        item = ledger.claim_item(
            uid=uid,
            producer='commitment_followup',
            source_kind='action_item',
            source_id='synthetic',
            source_revision='1',
            source_event_id=str(index),
            firestore_client=client,
            now=now,
        )
        user.collection(ledger.ITEMS).document(item['item_id']).update({'cost_status': 'estimated'})
        ledger.publish_item(
            uid=uid,
            item_id=item['item_id'],
            claim_token=item['claim_token'],
            encrypted_content='synthetic-ciphertext',
            firestore_client=client,
            now=now,
        )
        items.append(item)
    first, cursor, more = ledger.list_feed(uid=uid, limit=2, firestore_client=client, now=now)
    second, _, _ = ledger.list_feed(uid=uid, limit=2, cursor=cursor, firestore_client=client, now=now)
    assert more and len(first) == 2 and len(second) == 1
    assert len({item['item_id'] for item in first + second}) == 3
    from database import action_items

    monkeypatch.setattr(action_items, 'db', client)
    monkeypatch.setattr(action_items, 'bump_action_items_list_version', lambda uid: None)
    assert action_items.delete_action_item(uid, 'synthetic')
    assert ledger.list_feed(uid=uid, firestore_client=client, now=now)[0] == []
    ledger.purge_source_items(uid=uid, source_kind='action_item', source_id='synthetic', firestore_client=client)
    for item in items:
        row = user.collection(ledger.ITEMS).document(item['item_id']).get().to_dict()
        assert 'content' not in row and row['state'] == 'suppressed'
    client.close()
