"""Actual server hooks exercise the transactional first-event reducer."""

from datetime import timedelta
from types import SimpleNamespace

from database import proactivity as ledger
from database import proactivity_producers as mapping
from tests.unit.test_proactivity_v2_budget import NOW, store
from tests.unit.test_proactivity_v2_ledger import outcome, ready


def query_for(store, item):
    return SimpleNamespace(
        stream=lambda: [SimpleNamespace(to_dict=lambda: store.rows[('users', 'u', ledger.ITEMS, item['item_id'])])]
    )


def test_first_mentor_thread_reply_within_24h_credited_once(store, monkeypatch):
    item = ready(store, producer='conversation_mentor_v2')
    row = store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]
    row['push_accepted_at'] = NOW
    monkeypatch.setattr(mapping, 'utc_now', lambda: NOW + timedelta(minutes=2))
    monkeypatch.setattr(mapping, 'recent_mentor_query', lambda *args: query_for(store, item))
    mapping.record_mentor_reply('u', firestore_client=store)
    row = store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]
    original = dict(row['outcomes']['replied'])
    mapping.record_mentor_reply('u', firestore_client=store)
    assert row['acted_24h'] and row['delivered']
    assert row['outcomes']['replied'] == original


def test_mentor_reply_after_24h_no_credit(store, monkeypatch):
    item = ready(store, producer='conversation_mentor_v2')
    row = store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]
    row['push_accepted_at'] = NOW
    monkeypatch.setattr(mapping, 'utc_now', lambda: NOW + timedelta(hours=24, seconds=1))
    monkeypatch.setattr(mapping, 'recent_mentor_query', lambda *args: query_for(store, item))
    mapping.record_mentor_reply('u', firestore_client=store)
    assert not row['acted_24h']


def test_task_completed_after_feed_exposure_credited(store, monkeypatch):
    item = ready(store)
    outcome(store, item, 'shown')
    monkeypatch.setattr(mapping, 'utc_now', lambda: NOW + timedelta(minutes=2))
    monkeypatch.setattr(mapping, 'task_items_query', lambda *args: query_for(store, item))
    mapping.record_task_completion('u', 'a', firestore_client=store)
    row = store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]
    assert row['acted_24h']
    assert row['outcomes']['accepted']['surface'] == 'server'


def test_completion_before_exposure_cannot_gain_credit_on_retry(store, monkeypatch):
    item = ready(store)
    monkeypatch.setattr(mapping, 'utc_now', lambda: NOW)
    monkeypatch.setattr(mapping, 'task_items_query', lambda *args: query_for(store, item))
    mapping.record_task_completion('u', 'a', firestore_client=store)
    outcome(store, item, 'shown', now=NOW + timedelta(minutes=1))
    mapping.record_task_completion('u', 'a', firestore_client=store)
    assert not store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]['acted_24h']


def test_followup_publish_source_guard_checks_inside_transaction(store):
    import pytest
    from config.proactivity_v2 import ProactivityDenied
    from tests.unit.test_proactivity_v2_budget import claim

    item = claim(store)
    store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]['cost_status'] = 'estimated'
    store.rows[('users', 'u', 'action_items', 'a')]['completed'] = True
    with pytest.raises(ProactivityDenied, match='source_changed'):
        ledger.publish_item(
            uid='u',
            item_id=item['item_id'],
            claim_token=item['claim_token'],
            encrypted_content='ciphertext',
            source_guard={'completed': False},
            firestore_client=store,
            now=NOW,
        )
    assert store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]['state'] == 'claimed'
