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
    with pytest.raises(ProactivityDenied, match='claim_in_progress'):
        claim(store)


def test_timeout_is_not_delivery_or_dismissal(store):
    item = ready(store)
    assert outcome(store, item, 'timeout', event='timeout-id')['recorded']
    row = store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]
    assert not row['delivered'] and not row['dismissed'] and not row['negative']
    assert not row['acted_24h']
    assert row['outcomes']['timeout']['event_id'] == 'timeout-id'
    assert row['outcomes']['timeout']['at'] == NOW
    assert (row['delivered_count'], row['acted_count'], row['negative_count']) == (0, 0, 0)
    before = dict(row)
    assert not outcome(store, item, 'timeout', event='timeout-id')['recorded']
    assert not outcome(store, item, 'timeout', event='another-timeout', surface='macos')['recorded']
    assert row == before
    assert len(row['outcomes']) == 1
    with pytest.raises(ProactivityDenied, match='event_conflict'):
        outcome(store, item, 'opened', event='timeout-id')


def test_timeout_reusing_an_action_id_also_conflicts(store):
    item = ready(store)
    outcome(store, item, 'opened', event='opened-id')
    with pytest.raises(ProactivityDenied, match='event_conflict'):
        outcome(store, item, 'timeout', event='opened-id')


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
    ledger.record_mentor_chat(
        uid='u',
        item_id=item['item_id'],
        claim_token=item['claim_token'],
        status='persisted',
        message_id='chat-message',
        firestore_client=store,
        now=NOW,
    )
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


def test_server_reply_window_is_anchored_to_persisted_message(store):
    item = ready(store, 'conversation_mentor_v2')
    ledger.record_mentor_chat(
        uid='u',
        item_id=item['item_id'],
        claim_token=item['claim_token'],
        status='persisted',
        message_id='chat-message',
        firestore_client=store,
        now=NOW + timedelta(hours=23),
    )
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
    assert result['recorded'] and not result['acted_24h']
    row = store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]
    assert row['outcomes']['accepted']['source'] == 'server'
    assert not row['delivered']
    outcome(store, item, 'shown')
    repeat = ledger.record_server_outcome(item['item_id'], 'accepted', uid='u', firestore_client=store, now=NOW)
    assert not repeat['recorded'] and not repeat['acted_24h']


def write_score(store, item, score=0.6, **patch):
    return ledger.record_usefulness_score(
        **dict(
            uid='u',
            item_id=item['item_id'],
            claim_token=item['claim_token'],
            score=score,
            firestore_client=store,
            now=NOW,
            **patch
        )
    )


def test_usefulness_score_is_numeric_first_write_survives_publication_and_outcomes(store):
    item = claim(store, producer='conversation_mentor_v2')
    write_score(store, item)
    row = store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]
    assert row['usefulness_score'] == 0.6
    assert isinstance(row['usefulness_score'], float)
    write_score(store, item)
    with pytest.raises(ProactivityDenied, match='score_conflict'):
        write_score(store, item, 0.2)
    row['cost_status'] = 'estimated'
    ledger.publish_item(
        uid='u',
        item_id=item['item_id'],
        claim_token=item['claim_token'],
        encrypted_content='ciphertext',
        firestore_client=store,
        now=NOW,
    )
    outcome(store, item, 'shown')
    outcome(store, item, 'replied')
    outcome(store, item, 'thumbs_down')
    row = store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]
    assert row['usefulness_score'] == 0.6 and row['acted_24h'] and row['negative']


@pytest.mark.parametrize('score', [True, -1, 2, float('nan'), float('inf'), '0.5'])
def test_usefulness_storage_rejects_non_numeric_or_unbounded_scores(store, score):
    item = claim(store, producer='conversation_mentor_v2')
    with pytest.raises(ValueError, match='invalid usefulness score'):
        write_score(store, item, score)


@pytest.mark.parametrize(
    'change,reason',
    [
        ({'claim_token': 'other'}, 'duplicate'),
        ({'account_generation': 'retired'}, 'not_found'),
        ({'state': 'suppressed'}, 'duplicate'),
        ({'expires_at': NOW}, 'not_found'),
    ],
)
def test_usefulness_score_respects_claim_and_account_fences(store, change, reason):
    item = claim(store, producer='conversation_mentor_v2')
    store.rows[('users', 'u', ledger.ITEMS, item['item_id'])].update(change)
    with pytest.raises(ProactivityDenied, match=reason):
        write_score(store, item)


def test_followup_cannot_store_mentor_score(store):
    item = claim(store)
    with pytest.raises(ProactivityDenied, match='invalid_producer'):
        write_score(store, item)


@pytest.mark.parametrize('attempted', [False, True])
def test_followup_abandoned_claim_recovery_never_replays_an_attempt(store, attempted):
    item = claim(store)
    row = store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]
    if attempted:
        row.update(attempts={'call': {'state': 'unknown'}}, cost_status='indeterminate', charged_micro_usd=731)
    for name in ['conversation_mentor_v2', 'commitment_followup']:
        store.rows[(ledger.CONTROLS, name)]['checked_at'] = NOW + timedelta(minutes=5)
    kwargs = dict(
        uid='u',
        producer='commitment_followup',
        source_kind='action_item',
        source_id='a',
        source_revision='1',
        source_event_id='due',
        firestore_client=store,
    )
    with pytest.raises(ProactivityDenied, match='claim_in_progress'):
        ledger.claim_item(**kwargs, now=NOW + timedelta(minutes=4))
    if attempted:
        with pytest.raises(ProactivityDenied, match='duplicate'):
            ledger.claim_item(**kwargs, now=NOW + timedelta(minutes=5))
        recovered = store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]
        assert recovered['state'] == 'failed' and recovered['charged_micro_usd'] == 731
        assert recovered['attempts']['call']['state'] == 'unknown'
    else:
        recovered = ledger.claim_item(**kwargs, now=NOW + timedelta(minutes=5))
        assert recovered['item_id'] == item['item_id'] and recovered['claim_token'] != item['claim_token']
        assert not recovered['attempts']
        with pytest.raises(ProactivityDenied, match='duplicate'):
            ledger.publish_item(
                uid='u',
                item_id=item['item_id'],
                claim_token=item['claim_token'],
                state='failed',
                firestore_client=store,
                now=NOW + timedelta(minutes=5),
            )
