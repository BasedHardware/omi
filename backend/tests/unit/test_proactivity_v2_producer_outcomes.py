"""Actual server hooks exercise the transactional first-event reducer."""

from datetime import timedelta
from types import SimpleNamespace

import database.action_items as tasks
import database.chat as chat
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
    ledger.record_mentor_chat(
        uid='u',
        item_id=item['item_id'],
        claim_token=item['claim_token'],
        status='persisted',
        message_id='chat-message',
        firestore_client=store,
        now=NOW,
    )
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
    ledger.record_mentor_chat(
        uid='u',
        item_id=item['item_id'],
        claim_token=item['claim_token'],
        status='persisted',
        message_id='chat-message',
        firestore_client=store,
        now=NOW,
    )
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


def test_canonical_mentor_human_persistence_observes_after_commit(monkeypatch):
    import inspect

    events = []
    messages = SimpleNamespace(add=lambda payload: events.append('persisted'))
    owner = SimpleNamespace(collection=lambda name: messages)
    monkeypatch.setattr(
        chat, 'db', SimpleNamespace(collection=lambda name: SimpleNamespace(document=lambda uid: owner))
    )
    monkeypatch.setattr(mapping, 'record_mentor_reply', lambda uid, **kwargs: events.append('observed'))
    # Exercise the persistence body; encryption/plan wrappers have independent contract coverage.
    inspect.unwrap(chat.add_message)('u', {'memories': [], 'sender': 'human', 'plugin_id': 'mentor'})
    assert events == ['persisted', 'observed']


def test_canonical_task_completion_observation_is_post_commit(monkeypatch):
    saved, events = {}, []
    document = SimpleNamespace(
        get=lambda: SimpleNamespace(exists=True, to_dict=lambda: {'completed': False}),
        update=lambda values: saved.update(values),
    )
    owner = SimpleNamespace(collection=lambda name: SimpleNamespace(document=lambda task_id: document))
    monkeypatch.setattr(
        tasks, 'db', SimpleNamespace(collection=lambda name: SimpleNamespace(document=lambda uid: owner))
    )
    monkeypatch.setattr(tasks, 'bump_action_items_list_version', lambda uid: None)
    monkeypatch.setattr(tasks, '_record_followup_completion', lambda uid, task_id: events.append(saved['completed']))
    assert tasks.mark_action_item_completed('u', 'a', True)
    assert events == [True]


def test_mentor_reply_can_prove_exposure_when_push_was_denied(store, monkeypatch):
    item = ready(store, producer='conversation_mentor_v2')
    row = store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]
    ledger.record_mentor_chat(
        uid='u',
        item_id=item['item_id'],
        claim_token=item['claim_token'],
        status='persisted',
        message_id='chat-message',
        firestore_client=store,
        now=NOW,
    )
    monkeypatch.setattr(mapping, 'utc_now', lambda: NOW + timedelta(minutes=2))
    monkeypatch.setattr(mapping, 'recent_mentor_query', lambda *args: query_for(store, item))
    mapping.record_mentor_reply('u', firestore_client=store)
    row = store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]
    assert row['delivered'] and row['acted_24h']


def test_server_reducer_refuses_reply_without_persisted_chat_or_exposure(store):
    import pytest
    from config.proactivity_v2 import ProactivityDenied

    item = ready(store, producer='conversation_mentor_v2')
    with pytest.raises(ProactivityDenied, match='chat_unconfirmed'):
        ledger.record_server_outcome(item['item_id'], 'replied', uid='u', firestore_client=store, now=NOW)


def test_record_mentor_reply_tolerates_naive_iso_and_corrupt_anchors_and_missing_item_id(store, monkeypatch):
    item = ready(store, producer='conversation_mentor_v2')
    ledger.record_mentor_chat(
        uid='u',
        item_id=item['item_id'],
        claim_token=item['claim_token'],
        status='persisted',
        message_id='chat-message',
        firestore_client=store,
        now=NOW,
    )
    valid_snapshot = dict(store.rows[('users', 'u', ledger.ITEMS, item['item_id'])])
    valid_snapshot['delivered_at'] = NOW.isoformat().replace('+00:00', 'Z')
    snapshots = [
        SimpleNamespace(to_dict=lambda: {'state': 'ready', 'delivered_at': NOW}),
        SimpleNamespace(
            to_dict=lambda: {
                'item_id': 'old-naive',
                'state': 'ready',
                'delivered_at': (NOW - timedelta(hours=30)).replace(tzinfo=None),
            }
        ),
        SimpleNamespace(
            to_dict=lambda: {
                'item_id': 'corrupt-str',
                'state': 'ready',
                'delivered_at': 'not-a-timestamp',
            }
        ),
        SimpleNamespace(
            to_dict=lambda: {
                'item_id': 'bool-anchor',
                'state': 'ready',
                'delivered_at': True,
            }
        ),
        SimpleNamespace(to_dict=lambda: valid_snapshot),
    ]
    monkeypatch.setattr(mapping, 'utc_now', lambda: NOW + timedelta(minutes=2))
    monkeypatch.setattr(mapping, 'recent_mentor_query', lambda *args: SimpleNamespace(stream=lambda: snapshots))

    mapping.record_mentor_reply('u', firestore_client=store)

    row = store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]
    assert row['acted_24h'] and row['delivered']


def test_record_mentor_reply_credits_item_with_naive_snapshot_anchor(store, monkeypatch):
    item = ready(store, producer='conversation_mentor_v2')
    ledger.record_mentor_chat(
        uid='u',
        item_id=item['item_id'],
        claim_token=item['claim_token'],
        status='persisted',
        message_id='chat-message',
        firestore_client=store,
        now=NOW,
    )
    naive_snapshot = dict(store.rows[('users', 'u', ledger.ITEMS, item['item_id'])])
    naive_snapshot['mentor_chat_persisted_at'] = NOW.replace(tzinfo=None)
    monkeypatch.setattr(mapping, 'utc_now', lambda: NOW + timedelta(minutes=5))
    monkeypatch.setattr(
        mapping,
        'recent_mentor_query',
        lambda *args: SimpleNamespace(stream=lambda: [SimpleNamespace(to_dict=lambda: naive_snapshot)]),
    )

    mapping.record_mentor_reply('u', firestore_client=store)

    row = store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]
    assert row['acted_24h'] and row['delivered']


def test_record_task_completion_skips_items_missing_item_id(store, monkeypatch):
    item = ready(store)
    outcome(store, item, 'shown')
    valid_row = store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]
    snapshots = [
        SimpleNamespace(to_dict=lambda: {'producer': 'commitment_followup', 'state': 'ready'}),
        SimpleNamespace(to_dict=lambda: {'item_id': '', 'producer': 'commitment_followup', 'state': 'ready'}),
        SimpleNamespace(to_dict=lambda: valid_row),
    ]
    monkeypatch.setattr(mapping, 'utc_now', lambda: NOW + timedelta(minutes=2))
    monkeypatch.setattr(mapping, 'task_items_query', lambda *args: SimpleNamespace(stream=lambda: snapshots))

    mapping.record_task_completion('u', 'a', firestore_client=store)

    assert store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]['acted_24h']


def test_coerce_utc_datetime_handles_naive_aware_iso_epoch_and_rejects_bool():
    from datetime import timezone

    naive = NOW.replace(tzinfo=None)
    assert mapping._coerce_utc_datetime(naive) == NOW
    assert mapping._coerce_utc_datetime(NOW) == NOW
    assert mapping._coerce_utc_datetime(NOW.isoformat().replace('+00:00', 'Z')) == NOW
    assert mapping._coerce_utc_datetime(NOW.timestamp()) == NOW
    assert mapping._coerce_utc_datetime(True) is None
    assert mapping._coerce_utc_datetime(False) is None
    assert mapping._coerce_utc_datetime('') is None
    assert mapping._coerce_utc_datetime('   ') is None
    assert mapping._coerce_utc_datetime('not-a-timestamp') is None
    assert mapping._coerce_utc_datetime(naive).tzinfo == timezone.utc
