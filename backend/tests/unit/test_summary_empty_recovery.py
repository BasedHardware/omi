"""Transcript recovery is lifetime-bounded; ownership races spend no empty budget."""

from copy import deepcopy
import importlib
from unittest.mock import Mock

import pytest

from database import summary_processing
from services import summary_debt_repair as repair
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_cross_job_assignment import chunk, intake
from utils.conversations import summary_delivery as delivery
from utils.enrichment import custody, outbox

CONVERSATION = ('users', 'u', 'conversations', 'c')
KEY = outbox.key('u', 'c')
OUTBOX = (outbox.COLLECTION, KEY)


@pytest.fixture(scope='module', autouse=True)
def load_live_writer():
    # Import failures still fail the suite, while per-call CPU guards measure
    # transaction behavior rather than one-time dependency initialization.
    importlib.import_module('database.conversations')


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '0')
    monkeypatch.setattr(repair, 'account_deletion_blocks_user_work', lambda *_: False)
    monkeypatch.setattr(repair, 'assert_batch_write_allowed', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(outbox, '_recent_conversation', lambda *_: False)
    monkeypatch.setattr(outbox, 'owns_runtime', lambda: True)
    monkeypatch.setattr(
        outbox,
        'dispatch_binding',
        lambda **_: {
            'queue': 'synthetic',
            'handler': 'https://worker.invalid/v2/enrichment/run',
            'audience': 'https://worker.invalid/v2/enrichment/run',
            'invoker_sa': 'synthetic@example.invalid',
        },
    )
    monkeypatch.setattr(outbox, '_enqueue', Mock())
    row = {
        **chunk('c', 1000),
        'data_protection_level': 'standard',
        'sync_content_revision': 3,
        'summary_title_provenance': 'server_minimum',
        'structured': {'title': 'Synthetic minimum', 'overview': '', 'title_provenance': 'server_minimum'},
        'summary_first_pending_at': 100,
        'summary_due_at': None,
        'summary_empty_failures': 3,
        'summary_blocked_reason': 'empty_output_exhausted',
        'summary_processing_owner': 'worker',
    }
    pending = {
        'uid': 'u',
        'conversation_id': 'c',
        'language': 'en',
        'owner': 'worker',
        'task_token': 'old-token',
        'version': 1,
        'dormant': True,
        'summary_empty_failures': 3,
        'summary_blocked_reason': 'empty_output_exhausted',
        'due_at': None,
        'lease_until': 0,
        'first_pending_at': 100,
    }
    return StrictFirestore({('users', 'u'): {}, CONVERSATION: row, OUTBOX: pending})


def test_transcript_append_reopens_debt_and_repair_reopens_exhausted_outbox(store):
    before = deepcopy(store.rows[CONVERSATION])
    result, created, survivors = intake(store, chunk('append', 1060), target_id='c')
    row = store.rows[CONVERSATION]
    assert not created and survivors and result['id'] == 'c'
    assert row['sync_content_revision'] == 4
    assert row['summary_blocked_reason'] is None and row['summary_empty_failures'] == 0
    assert row['summary_due_at'] > 100 and row['summary_first_pending_at'] == 100
    assert row['structured'] == before['structured']
    assert delivery.refusal(row) is None
    assert repair.redrive(store, 'u', 'c', now=row['summary_due_at'] + 1)
    pending = store.rows[OUTBOX]
    assert pending['summary_blocked_reason'] is None and pending['summary_empty_failures'] == 0
    assert not pending['dormant'] and pending['summary_expected_revision'] == 4
    assert pending['task_token'] != 'old-token'
    outbox._enqueue.assert_called_once()


def test_same_transcript_replay_keeps_both_rows_blocked(store):
    before = deepcopy(store.rows[CONVERSATION])
    result, created, survivors = intake(store, chunk('c', 1000))
    assert not created and not survivors
    row = store.rows[CONVERSATION]
    assert row['summary_blocked_reason'] == 'empty_output_exhausted'
    assert row['summary_due_at'] is None and row['summary_empty_failures'] == 3
    assert row['structured'] == before['structured']
    assert not repair.redrive(store, 'u', 'c', now=10000)
    assert store.rows[OUTBOX]['task_token'] == 'old-token'
    outbox._enqueue.assert_not_called()


@pytest.mark.parametrize('changed', [False, True])
def test_live_append_recomputes_debt_with_the_transcript_revision(store, monkeypatch, changed):
    from database import conversations as db
    from models.transcript_segment import TranscriptSegment

    monkeypatch.setattr(db, 'invalidate_people_stats_cache', lambda *_: None)
    store.rows[CONVERSATION]['sync_live_target'] = True
    old_segment = TranscriptSegment(
        id='existing', start=0.0, end=9.5, text='The first topic.', speaker_id=0, is_user=False
    ).model_dump()
    store.rows[CONVERSATION]['transcript_segments'] = [old_segment]
    incoming = (
        [{'id': 'new', 'start': 10.0, 'end': 15.0, 'text': 'The next topic.', 'speaker_id': 0, 'is_user': False}]
        if changed
        else [deepcopy(old_segment)]
    )
    db.update_conversation_segments('u', 'c', incoming, live_segments=incoming, firestore_client=store)
    row = store.rows[CONVERSATION]
    assert row['sync_content_revision'] == (4 if changed else 3)
    assert row['summary_empty_failures'] == (0 if changed else 3)
    assert row['summary_blocked_reason'] == (None if changed else 'empty_output_exhausted')
    assert (row['summary_due_at'] is not None) is changed


@pytest.mark.parametrize('revision', [None, 2, 3])
def test_missing_older_or_unchanged_revision_does_not_rearm(store, revision):
    write = {'sync_content_revision': revision}
    delivery.rearm_on_revision_change(store.rows[CONVERSATION], write, now=200)
    assert write == {'sync_content_revision': revision}


@pytest.mark.parametrize('failures', [0, 1, 2])
def test_conversation_owner_mismatch_is_recorded_without_spending_attempts(store, failures):
    store.rows[OUTBOX].update(dormant=False, summary_empty_failures=failures)
    store.rows[CONVERSATION]['summary_processing_owner'] = 'replacement'
    conversation = deepcopy(store.rows[CONVERSATION])
    prior = deepcopy(store.rows[OUTBOX])
    result = summary_processing.record_empty_failure(store, outbox.COLLECTION, KEY, 'worker', 'old-token')
    assert result is summary_processing.EmptyFailureOutcome.OWNER_MISMATCH
    assert store.rows[CONVERSATION] == conversation
    assert store.rows[OUTBOX] == {**prior, 'summary_empty_outcome': 'owner_mismatch'}


@pytest.mark.parametrize('field,value', [('owner', 'replacement'), ('task_token', 'replacement'), ('dormant', True)])
def test_stale_outbox_owner_or_token_cannot_record_anything(store, field, value):
    store.rows[OUTBOX].update(dormant=False)
    store.rows[OUTBOX][field] = value
    before = deepcopy(store.rows)
    assert (
        summary_processing.record_empty_failure(store, outbox.COLLECTION, KEY, 'worker', 'old-token')
        is summary_processing.EmptyFailureOutcome.STALE
    )
    assert store.rows == before


def test_three_owned_empty_outputs_exhaust_once_and_preserve_structured_content(store):
    store.rows[OUTBOX].update(dormant=False, summary_empty_failures=0)
    store.rows[CONVERSATION].update(summary_blocked_reason=None, summary_due_at=220)
    before = deepcopy(store.rows[CONVERSATION]['structured'])
    outcomes = [
        summary_processing.record_empty_failure(store, outbox.COLLECTION, KEY, 'worker', 'old-token') for _ in range(3)
    ]
    assert outcomes == [
        summary_processing.EmptyFailureOutcome.RETRY,
        summary_processing.EmptyFailureOutcome.RETRY,
        summary_processing.EmptyFailureOutcome.BLOCKED,
    ]
    assert store.rows[OUTBOX]['dormant'] and store.rows[OUTBOX]['summary_empty_failures'] == 3
    assert store.rows[CONVERSATION]['summary_due_at'] is None
    assert store.rows[CONVERSATION]['structured'] == before


def test_lost_ack_preserves_a_banked_summary_despite_owner_change(store):
    store.rows[OUTBOX].update(dormant=False, summary_empty_failures=2)
    store.rows[CONVERSATION].update(
        summary_processing_owner='winner', summary_output_present=True, summary_completed_at=150
    )
    before = deepcopy(store.rows[CONVERSATION])
    assert (
        summary_processing.record_empty_failure(store, outbox.COLLECTION, KEY, 'worker', 'old-token')
        is summary_processing.EmptyFailureOutcome.BLOCKED
    )
    assert store.rows[CONVERSATION] == before
    assert store.rows[OUTBOX]['summary_seen']


def test_repeated_empty_cycles_stop_after_nine_calls_even_with_more_transcripts(store):
    store.rows[OUTBOX].update(dormant=False, summary_empty_failures=0, summary_blocked_reason=None)
    store.rows[CONVERSATION].update(summary_empty_failures=0, summary_blocked_reason=None, summary_due_at=220)
    calls = 0
    for cycle in range(3):
        token = store.rows[OUTBOX]['task_token']
        for expected in (
            summary_processing.EmptyFailureOutcome.RETRY,
            summary_processing.EmptyFailureOutcome.RETRY,
            summary_processing.EmptyFailureOutcome.BLOCKED,
        ):
            assert summary_processing.record_empty_failure(store, outbox.COLLECTION, KEY, 'worker', token) is expected
            calls += 1
        reason = delivery.EMPTY_LIFETIME_BLOCKED_REASON if cycle == 2 else delivery.EMPTY_BLOCKED_REASON
        assert store.rows[CONVERSATION]['summary_blocked_reason'] == reason
        assert store.rows[OUTBOX]['summary_blocked_reason'] == reason
        intake(store, chunk(f'append-{cycle}', 1060 + cycle * 60), target_id='c')
        row = store.rows[CONVERSATION]
        if cycle < 2:
            assert row['summary_empty_rearms'] == cycle + 1
            assert repair.redrive(store, 'u', 'c', now=row['summary_due_at'] + 1)
            store.rows[OUTBOX]['owner'] = 'worker'
        else:
            assert row['summary_empty_rearms'] == 2
            assert row['summary_due_at'] is None
            assert not repair.redrive(store, 'u', 'c', now=10000)
    assert calls == 9
    for revision in range(3, 6):
        intake(store, chunk(f'append-{revision}', 1060 + revision * 60), target_id='c')
        row = store.rows[CONVERSATION]
        assert row['summary_blocked_reason'] == delivery.EMPTY_LIFETIME_BLOCKED_REASON
        assert row['summary_empty_rearms'] == 2 and row['summary_due_at'] is None
        assert delivery.refusal(row) == delivery.EMPTY_LIFETIME_BLOCKED_REASON
        assert not repair.redrive(store, 'u', 'c', now=10000)
    assert store.rows[OUTBOX]['dormant']


@pytest.mark.parametrize('rearms', [0, 2])
def test_final_record_replacement_rearms_in_its_assignment_transaction(store, rearms):
    store.rows[CONVERSATION].update(summary_empty_rearms=rearms, record_lane_owner='batch_live_v1')
    incoming = chunk('final', 1000, text='New final recording transcript.')
    incoming['transcript_segments'][0]['id'] = 'final-segment'
    incoming['_batch_replace_live'] = {'start': 1000, 'end': 1010}
    intake(store, incoming, target_id='c')
    row = store.rows[CONVERSATION]
    assert row['sync_content_revision'] == 4
    assert row['transcript_segments'][0]['text'] == 'New final recording transcript.'
    assert row['summary_empty_rearms'] == min(rearms + 1, 2)
    assert row['summary_empty_failures'] == (0 if rearms == 0 else 3)
    assert (row['summary_due_at'] is not None) is (rearms == 0)
    assert row['summary_blocked_reason'] == (None if rearms == 0 else delivery.EMPTY_LIFETIME_BLOCKED_REASON)


@pytest.mark.parametrize('reason', sorted(delivery.EMPTY_BLOCKED_REASONS))
def test_redirect_custody_cannot_reopen_either_empty_budget(store, monkeypatch, reason):
    store.rows[OUTBOX]['summary_blocked_reason'] = reason
    donor_key = outbox.key('u', 'donor')
    source = (outbox.COLLECTION, donor_key)
    store.rows[source] = {
        **store.rows[OUTBOX],
        'conversation_id': 'donor',
        'dormant': False,
        'due_at': 220,
    }

    def privacy_snapshot(_client, _transaction, _uid, *, conversation_ids, snapshots):
        snapshots['conversations'] = {
            'donor': {'deleted': True, 'sync_merged_into': 'c'},
            'c': {'deleted': False},
        }

    monkeypatch.setattr(outbox, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(custody, 'assert_batch_write_allowed', privacy_snapshot)
    assert custody.transfer_redirect(donor_key, 'old-token', 'worker', 'c', now=200) is None
    assert source not in store.rows
    pending = store.rows[OUTBOX]
    assert pending['dormant'] and pending['due_at'] is None
    assert pending['summary_blocked_reason'] == reason and pending['summary_empty_failures'] == 3
