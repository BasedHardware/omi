"""A kept sync piece held for notes shows on Home as Processing, not as a hidden fragment.

Shape from prod 2026-11-18: a phone-WAL piece of an open batch-only live capture.
Its server-minimum title and moving finished_at kept it under the settling hold
for as long as the capture lasted, so Home showed neither row.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import conversations as conversations_db
from tests.unit.test_sync_donor_tombstone_visibility import _install_listing
from utils.conversations import home_step
from utils.conversations.fragment_visibility import (
    SETTLING_MAX_HOLD_SECONDS,
    held_for_notes,
    is_settling_fragment,
)

NOW = datetime.now(timezone.utc)


def piece(id='piece', **updates):
    row = {
        'id': id,
        'status': 'completed',
        'source': 'omi',
        'discarded': False,
        'created_at': NOW - timedelta(minutes=18),
        'started_at': NOW - timedelta(minutes=18),
        'finished_at': NOW - timedelta(seconds=20),
        'structured': {'title': "Yo, what's up?", 'overview': '', 'title_provenance': 'server_minimum'},
        'sync_relevance': 'keep',
        'has_content': True,
        'sync_content_revision': 40,
        'sync_processing_hold': {
            'held': True,
            'pending_since': (NOW - timedelta(minutes=18)).timestamp(),
            'last_content_at': (NOW - timedelta(seconds=15)).timestamp(),
        },
        'sync_bridge_pending': {'target_id': 'live', 'expires_at': (NOW - timedelta(minutes=8)).timestamp()},
    }
    row.update(updates)
    return row


def released(row):
    return {**row, 'sync_processing_hold': {'held': False}, 'sync_bridge_pending': None}


def test_the_held_piece_is_a_processing_row_on_the_legacy_home_list():
    row = piece()
    assert held_for_notes(row)
    assert not is_settling_fragment(row, show_held=True)
    assert conversations_db.is_visible_conversation(row, presentation=True, show_held=True)
    assert home_step.classify(row, show_held=True) == home_step.WRITING_NOTES


def test_every_other_reader_keeps_the_settling_hold():
    row = piece()
    assert is_settling_fragment(row)
    assert not conversations_db.is_visible_conversation(row, presentation=True)
    assert home_step.classify(row) == home_step.NOISE


@pytest.mark.parametrize('layer', [{'recording': True}, {'v3_derived': True}])
def test_v3_layer_rows_never_qualify(layer):
    row = piece(**layer)
    assert not held_for_notes(row)
    assert is_settling_fragment(row, show_held=True)


def test_without_a_hold_the_stand_in_still_waits_off_home():
    assert is_settling_fragment(released(piece()))


@pytest.mark.parametrize(
    'waiting',
    [
        {'sync_bridge_pending': None},
        {'sync_processing_hold': {'held': False}},
    ],
)
def test_either_the_quiet_hold_or_the_live_bridge_is_enough(waiting):
    row = piece(**waiting)
    assert held_for_notes(row) and home_step.classify(row, show_held=True) == home_step.WRITING_NOTES


@pytest.mark.parametrize(
    'filler',
    [
        {'sync_relevance': 'review'},
        {'has_content': False},
        {'summary_blocked_reason': 'content_below_floor'},
        {'relevance_decision': {'verdict': 'keep', 'decided_by': 'rule', 'reason': 'content_below_floor'}},
        {'relevance_decision': {'verdict': 'discard', 'decided_by': 'rule', 'reason': 'filler_only'}},
        {'relevance_decision': {'verdict': 'discard', 'decided_by': 'model', 'reason': 'low_signal'}},
        {'discarded': True},
        {'summary_blocked_reason': 'local_only'},
        {'deleted': True, 'sync_merged_into': 'live'},
    ],
)
def test_filler_blocked_and_merged_pieces_stay_off_home(filler):
    row = piece(**filler)
    assert not held_for_notes(row)
    assert not conversations_db.is_visible_conversation(row, presentation=True, show_held=True)


def test_the_open_bridge_window_still_hides_the_piece():
    row = piece(sync_bridge_pending={'target_id': 'live', 'expires_at': (NOW + timedelta(minutes=5)).timestamp()})
    assert held_for_notes(row)
    assert not conversations_db.is_visible_conversation(row, presentation=True, show_held=True)


def test_a_lost_obligation_cannot_keep_the_row_processing():
    stale = (NOW - timedelta(seconds=SETTLING_MAX_HOLD_SECONDS)).timestamp()
    row = piece(
        finished_at=NOW - timedelta(seconds=SETTLING_MAX_HOLD_SECONDS),
        sync_processing_hold={'held': True, 'last_content_at': stale},
    )
    assert not held_for_notes(row)
    assert home_step.classify(row, show_held=True) == home_step.NOISE


def test_arrival_clock_wins_over_an_old_recorded_end():
    # Offline backlog: recorded hours ago, uploaded and held now.
    row = piece(finished_at=NOW - timedelta(hours=6))
    assert held_for_notes(row) and home_step.classify(row, show_held=True) == home_step.WRITING_NOTES
    assert home_step.classify(row) == home_step.NOISE


def test_landed_notes_are_ready_even_while_the_bridge_field_remains():
    row = piece(structured={'title': 'Planning the launch', 'overview': 'We set the date.'})
    assert home_step.classify(row, show_held=True) == home_step.READY


def _home(monkeypatch, rows, *, v3=False, query=''):
    from routers import conversations as routes
    from utils.other import endpoints as auth

    from tests.unit.test_sync_donor_tombstone_visibility import _ListingCollection, _ListingDoc, _ListingQuery

    def select(collection, fields):
        # The indexed slim read: only projected fields reach the visibility check.
        return _ListingQuery(
            [
                _ListingDoc(doc.id, {key: value for key, value in doc.to_dict().items() if key in fields})
                for doc in collection._query._docs
            ]
        )

    monkeypatch.setattr(_ListingCollection, 'select', select, raising=False)
    monkeypatch.setattr(conversations_db, 'indexed_list_reads_enabled', lambda: True)
    monkeypatch.setattr(routes, 'conversations_v3_enabled', lambda uid: v3)
    _install_listing(monkeypatch, {row['id']: row for row in rows})
    monkeypatch.setattr(routes, '_heal_locked_conversations_if_eligible', lambda *a: None)
    monkeypatch.setattr(
        routes.ListVersionCheck, 'start', lambda *a: SimpleNamespace(not_modified=None, finish=lambda *a, **kw: None)
    )
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: 'u'
    with TestClient(app) as client:
        response = client.get('/v1/conversations' + query)
    assert response.status_code == 200
    return response.json()


def test_home_list_returns_one_processing_member_per_piece(monkeypatch):
    live = {
        'id': 'live',
        'status': 'in_progress',
        'discarded': False,
        'record_lane_owner': 'batch_live_v1',
        'created_at': NOW - timedelta(minutes=18),
        'started_at': NOW - timedelta(minutes=18),
        'finished_at': NOW,
        'structured': {'title': '', 'overview': ''},
        'data_protection_level': 'standard',
    }
    earlier = {
        'id': 'earlier',
        'status': 'completed',
        'discarded': False,
        'created_at': NOW - timedelta(hours=1),
        'started_at': NOW - timedelta(hours=1),
        'finished_at': NOW - timedelta(minutes=50),
        'structured': {'title': 'Standup', 'overview': 'We met.'},
        'data_protection_level': 'standard',
    }
    filler = piece('filler', sync_relevance='review', created_at=NOW - timedelta(minutes=30))
    # Held by the quiet hold alone, so the slim read must carry sync_processing_hold.
    second = piece(
        'second',
        created_at=NOW - timedelta(minutes=10),
        started_at=NOW - timedelta(minutes=10),
        sync_bridge_pending=None,
    )
    rows = [live, earlier, filler, piece(data_protection_level='standard'), second]

    before = _home(monkeypatch, [released(row) if row['id'] in {'piece', 'second'} else row for row in rows])
    assert [row['id'] for row in before] == ['earlier']

    after = _home(monkeypatch, rows)
    assert [(row['id'], row.get('home_step')) for row in after] == [
        ('second', 'writing_notes'),
        ('piece', 'writing_notes'),
        ('earlier', 'ready'),
    ]
    assert after[1]['status'] == 'completed'

    # Filtered views keep their existing behavior.
    filtered = _home(monkeypatch, rows, query='?statuses=completed')
    assert [row['id'] for row in filtered] == ['earlier']


def test_a_v3_owner_never_sees_a_held_legacy_piece(monkeypatch):
    # Prod shape e87bfed2: a legacy-layer piece bridged to a v3 recording row.
    recording = {
        'id': 'rec',
        'status': 'in_progress',
        'recording': True,
        'discarded': False,
        'created_at': NOW - timedelta(minutes=18),
        'started_at': NOW - timedelta(minutes=18),
        'finished_at': NOW,
        'structured': {'title': '', 'overview': ''},
        'data_protection_level': 'standard',
    }
    derived = {
        'id': 'derived',
        'status': 'completed',
        'v3_derived': True,
        'discarded': False,
        'created_at': NOW - timedelta(hours=1),
        'started_at': NOW - timedelta(hours=1),
        'finished_at': NOW - timedelta(minutes=50),
        'structured': {'title': 'Standup', 'overview': 'We met.'},
        'data_protection_level': 'standard',
    }
    held = piece(
        'e87bfed2',
        recording=None,
        v3_derived=None,
        data_protection_level='standard',
        sync_bridge_pending={'target_id': 'rec', 'expires_at': (NOW - timedelta(minutes=8)).timestamp()},
    )
    rows = [recording, derived, held]
    assert [row['id'] for row in _home(monkeypatch, rows, v3=True)] == ['derived']
    assert [row['id'] for row in _home(monkeypatch, rows, v3=False)] == ['e87bfed2', 'derived']
