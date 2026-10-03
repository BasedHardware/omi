from datetime import timedelta

import pytest

from config.proactivity_v2 import ProactivityDenied
from database import proactivity as ledger
from tests.unit.test_proactivity_v2_budget import NOW, claim, store


def ready(store, producer='commitment_followup'):
    item = claim(store, producer=producer)
    store.rows[('users', 'u', ledger.ITEMS, item['item_id'])].update(
        state='ready', cost_status='estimated', content='ciphertext'
    )
    return item


def outcome(store, item, action, event=None, surface='ios', now=NOW):
    return ledger.record_outcome(
        uid='u',
        item_id=item['item_id'],
        event_id=event or action,
        action=action,
        surface=surface,
        channel='feed',
        firestore_client=store,
        now=now,
    )


def test_claim_deduplicates_source(store):
    claim(store)
    with pytest.raises(ProactivityDenied, match='duplicate'):
        claim(store)


def test_timeout_is_not_delivery_or_dismissal(store):
    item = ready(store)
    assert not outcome(store, item, 'timeout')['recorded']
    row = store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]
    assert not row['delivered'] and not row['dismissed'] and not row['negative']


def test_cross_device_first_action_and_negative_are_independent(store):
    item = ready(store)
    outcome(store, item, 'shown')
    assert outcome(store, item, 'opened')['acted_24h']
    assert not outcome(store, item, 'opened', event='mac-open', surface='macos')['recorded']
    result = outcome(store, item, 'thumbs_down')
    assert result['acted_24h'] and result['negative']
    with pytest.raises(ProactivityDenied, match='event_conflict'):
        outcome(store, item, 'replied', event='opened')


def test_late_action_does_not_get_24h_credit(store):
    item = ready(store)
    outcome(store, item, 'shown')
    assert not outcome(store, item, 'opened', now=NOW + timedelta(hours=25))['acted_24h']


def test_disable_persists_preference_and_denies_new_claim(store):
    item = ready(store)
    assert outcome(store, item, 'producer_disabled')['negative']
    with pytest.raises(ProactivityDenied, match='producer_disabled'):
        claim(store, event='next')


def test_server_reply_confirms_exposure_once(store):
    item = ready(store, 'conversation_mentor_v2')
    store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]['push_accepted_at'] = NOW
    result = ledger.record_server_outcome(
        item['item_id'], 'replied', uid='u', firestore_client=store, now=NOW + timedelta(hours=1)
    )
    assert result['acted_24h'] and result['recorded']
    assert not ledger.record_server_outcome(
        item['item_id'], 'replied', uid='u', firestore_client=store, now=NOW + timedelta(hours=2)
    )['recorded']


def test_source_deleted_blocks_outcome(store):
    item = ready(store)
    del store.rows[('users', 'u', 'action_items', 'a')]
    with pytest.raises(ProactivityDenied, match='not_found'):
        outcome(store, item, 'opened')


def test_server_reply_window_is_anchored_to_late_push(store):
    item = ready(store, 'conversation_mentor_v2')
    store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]['push_accepted_at'] = NOW + timedelta(hours=23)
    result = ledger.record_server_outcome(
        item['item_id'], 'replied', uid='u', firestore_client=store, now=NOW + timedelta(hours=46)
    )
    assert result['acted_24h']


def test_terminal_bookkeeping_survives_kill_and_deleted_source(store):
    item = claim(store)
    store.rows[(ledger.CONTROLS, 'commitment_followup')]['state'] = 'killed'
    del store.rows[('users', 'u', 'action_items', 'a')]
    ledger.publish_item(
        uid='u',
        item_id=item['item_id'],
        claim_token=item['claim_token'],
        state='failed',
        firestore_client=store,
        now=NOW + timedelta(days=2),
    )
    assert store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]['state'] == 'failed'


def test_push_last_fence_observes_disable(store):
    item = ready(store, 'conversation_mentor_v2')
    store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]['push_state'] = 'claimed'
    ledger.validate_push(uid='u', item_id=item['item_id'], firestore_client=store, now=NOW)
    outcome(store, item, 'producer_disabled')
    with pytest.raises(ProactivityDenied, match='producer_disabled'):
        ledger.validate_push(uid='u', item_id=item['item_id'], firestore_client=store, now=NOW)


def test_server_completion_requires_confirmed_followup_exposure(store):
    item = ready(store)
    result = ledger.record_server_outcome(item['item_id'], 'accepted', uid='u', firestore_client=store, now=NOW)
    assert not result['recorded'] and not result['acted_24h']
    outcome(store, item, 'shown')
    assert ledger.record_server_outcome(item['item_id'], 'accepted', uid='u', firestore_client=store, now=NOW)[
        'acted_24h'
    ]
