"""A per-moment write into a closed episode the composer owns spends no model call.

Membership, cursors, receipts and member activity are still recorded in the same CAS, so the
composer (which reads every member's whole transcript) sees the member; only the notes are its own.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from config import episodes as config
from database import episodes as episodes_db
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_episodes_service import (  # noqa: F401  (autouse fixtures are imported to apply here)
    T0,
    TAIL,
    UID,
    FakeModel,
    _collaborators,
    _consumed,
    _enabled,
    _moment,
    _row,
    _segments,
    _speaker_names,
)
from utils.episodes import composer, service


@pytest.fixture
def composer_on(monkeypatch):
    monkeypatch.delenv(config.EPISODE_COMPOSER_ENV, raising=False)
    scheduled = []
    monkeypatch.setattr(composer, 'schedule', lambda uid, eid, **_: scheduled.append(eid) or True)
    return scheduled


def _closed_after_tail(store, model):
    service.record_moment(UID, _moment('c1'), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    first = episodes_db.get_current_episode(UID, firestore_client=store)
    idle = _collaborators(model, now=T0 + timedelta(hours=2), store=store)
    assert service.live_episode(UID, collaborators=idle) is None
    service.on_conversation_finalized(UID, 'c1', _row(text=TAIL), trigger='client_finalize', collaborators=idle)
    return first, episodes_db.get_episode(UID, first['id'], firestore_client=store)


def test_closed_tail_records_bookkeeping_without_a_model_call(composer_on):
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']}, {'bullets': ['A', 'B']})
    first, closed = _closed_after_tail(store, model)
    assert len(model.calls) == 1  # only the live moment; the closing tail spent nothing
    assert closed['bullets'] == ['A']  # notes untouched: the composer writes them
    assert closed['usage']['calls'] == first['usage']['calls']
    assert 'c1' in closed['conversation_ids']
    # The tail's speech was consumed: cursor advanced and receipts written in the same CAS.
    assert closed['applied']['c1'] > first['applied']['c1']
    receipts_on = _consumed(store)[0]
    assert [m['heading'] for m in closed['moments']] == [m['heading'] for m in first['moments']]
    assert composer_on  # the member finalize still schedules the compose
    # Same consumption bookkeeping as the model path (composer off), minus the notes.
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv(config.EPISODE_COMPOSER_ENV, 'off')
        service.reset_for_tests()
        store_off = StrictFirestore()
        _first_off, closed_off = _closed_after_tail(
            store_off, FakeModel({'title': 'Lunch', 'bullets': ['A']}, {'bullets': ['A', 'B']})
        )
    assert receipts_on == _consumed(store_off)[0]
    assert closed['applied'] == closed_off['applied']
    assert closed['conversation_ids'] == closed_off['conversation_ids']
    assert closed['member_activity'] == closed_off['member_activity']


def test_composer_off_keeps_the_tail_notes_update(monkeypatch):
    monkeypatch.setenv(config.EPISODE_COMPOSER_ENV, 'off')
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']}, {'bullets': ['A', 'B']})
    _first, closed = _closed_after_tail(store, model)
    assert len(model.calls) == 2 and closed['bullets'] == ['A', 'B']


def test_a_live_episode_still_gets_live_notes(composer_on):
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']}, {'bullets': ['A', 'B']})
    c = _collaborators(model, now=T0 + timedelta(minutes=1), store=store)
    service.record_moment(UID, _moment('c1'), c)
    service.record_moment(
        UID, _moment('c1', minutes=3, start=120.0), _collaborators(model, now=T0 + timedelta(minutes=5), store=store)
    )
    live = episodes_db.get_current_episode(UID, firestore_client=store)
    assert len(model.calls) == 2 and live['bullets'] == ['A', 'B']


def _replay_row():
    # Long enough for several recovery batches (each at most 3,000 characters).
    sentence = 'we went over the deployment plan for the agents and the sandbox again in detail'
    text = '. '.join(f'{sentence} part {i}' for i in range(120))
    return {
        'id': 'c1',
        'source': 'omi',
        'started_at': T0,
        'finished_at': T0 + timedelta(minutes=30),
        'transcript_segments': _segments(text, start=200.0),
    }


def test_sync_replay_into_a_closed_episode_finishes_every_batch_without_model_calls(composer_on):
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']}, {'bullets': ['A', 'B']})
    first, closed = _closed_after_tail(store, model)
    calls_before = len(model.calls)
    c = _collaborators(model, now=T0 + timedelta(hours=3), store=store)
    row = _replay_row()
    assert len(list(service.recovery.moments('c1', row, now=T0 + timedelta(hours=3), calendar_identity=None))) > 1
    # The replay loop stops on any outcome but applied/skipped_applied: every batch must report applied.
    assert service._record_recovered(UID, first['id'], 'c1', row, c) == 'applied'
    after = episodes_db.get_episode(UID, first['id'], firestore_client=store)
    assert len(model.calls) == calls_before
    assert after['bullets'] == closed['bullets'] and after['moments'] == closed['moments']
    assert after['applied']['c1'] >= max(s['end'] for s in row['transcript_segments'])
    content, _ = service.episode_receipts.get_consumed_ids(
        UID, service.recovery.receipt_namespace('c1'), all_shards=True, firestore_client=store
    )
    assert content
    # A repeated replay consumes nothing new.
    assert service._record_recovered(UID, first['id'], 'c1', row, c) in {'applied', 'skipped_applied'}
    again = episodes_db.get_episode(UID, first['id'], firestore_client=store)
    assert again['applied'] == after['applied'] and len(model.calls) == calls_before


def test_a_member_still_processing_keeps_the_model_path(composer_on, monkeypatch):
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']}, {'bullets': ['A', 'B']})
    monkeypatch.setattr(
        composer,
        'owns_closed_notes',
        lambda uid, episode, cid, c: False,  # another member never finishes: compose would wait
    )
    _first, closed = _closed_after_tail(store, model)
    assert len(model.calls) == 2 and closed['bullets'] == ['A', 'B']


def test_owns_closed_notes_requires_every_other_member_done(composer_on, monkeypatch):
    rows = {'c2': {'status': 'processing'}, 'c3': {'status': 'completed'}}
    monkeypatch.setattr(composer.conversations_db, 'get_conversation', lambda uid, cid, **_: rows.get(cid))
    episode = {'status': 'closed', 'started_at': T0, 'conversation_ids': ['c1', 'c2', 'c3']}
    assert composer.owns_closed_notes(UID, episode, 'c1', None) is False
    rows['c2']['status'] = 'completed'
    assert composer.owns_closed_notes(UID, episode, 'c1', None) is True
    assert composer.owns_closed_notes(UID, {**episode, 'compose_failures': 4}, 'c1', None) is False
