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
