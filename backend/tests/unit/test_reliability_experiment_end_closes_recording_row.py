"""Experiment ``end_open_conversation``: an End also closes the recording row to later audio.

An uploaded unit joins the nearest recording row within about two minutes. Off (the default) that is
all: a unit recorded after an End joins the row that began before it, so one recording row sits in both
the ended conversation and the next one. On, the batch projection reads the Ends around the unit's
first speech and the attach step leaves alone any row that began on the other side of an End: audio
recorded after the End starts a new recording row, and audio recorded before it that lands late still
joins the row it belongs to.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from config import reliability_experiments
from database import conversations as conversations_db
from database import conversations_v3_manual_cuts as cuts_db
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.conversations.v3 import manual_cuts
from utils.conversations.v3.end_sides import ATTACH_KEY, separated_by_end

EXPERIMENT = 'end_open_conversation'
T0 = datetime(2026, 11, 25, 5, 12, 40, tzinfo=timezone.utc)
END = T0 + timedelta(seconds=15)


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv(reliability_experiments.ENV, EXPERIMENT)
    monkeypatch.setattr(manual_cuts, 'conversations_v3_enabled', lambda uid: True)


@pytest.fixture
def off(monkeypatch):
    monkeypatch.delenv(reliability_experiments.ENV, raising=False)
    monkeypatch.setattr(manual_cuts, 'conversations_v3_enabled', lambda uid: True)


def unit(name, at, seconds=5, *, ends=None):
    """One uploaded phone file's transcript, as the batch projection hands it to the attach step."""
    row = {
        'id': name,
        'source': 'omi',
        'status': 'completed',
        'data_protection_level': 'standard',
        'structured': {},
        'recording': True,
        'started_at': at,
        'finished_at': at + timedelta(seconds=seconds),
        'created_at': at,
        'transcript_segments': [
            {
                'id': f'{name}-line',
                'text': f'Synthetic speech {name}.',
                'speaker': 'SPEAKER_00',
                'speaker_id': 0,
                'is_user': False,
                'start': 0.0,
                'end': float(seconds),
                'speaker_id_scope': f'sync:{name}',
            }
        ],
    }
    if ends is not None:
        row[ATTACH_KEY] = ends
    return row


@pytest.fixture
def attach(monkeypatch):
    store = StrictFirestore()
    monkeypatch.setattr(conversations_db, 'stop_quiet_check_for_conversation', lambda *a, **k: None)
    monkeypatch.setattr(conversations_db, 'index_sync_assignment', lambda *a, **k: None)
    monkeypatch.setattr(conversations_db, 'db', store)

    def run(incoming):
        row, _, _ = conversations_db.assign_sync_conversation('owner', incoming, firestore_client=store)
        return row['id']

    return store, run


def rows(store):
    return {
        path[3]: row
        for path, row in store.rows.items()
        if len(path) == 4 and path[2] == 'conversations' and not row.get('sync_merged_into')
    }


def test_baseline_a_unit_recorded_after_an_end_joins_the_row_that_began_before_it(attach):
    store, run = attach
    first = run(unit('before', T0))
    assert run(unit('after', END + timedelta(seconds=10))) == first
    assert len(rows(store)) == 1


def test_a_unit_recorded_after_an_end_starts_a_new_recording_row(attach):
    store, run = attach
    first = run(unit('before', T0))
    second = run(unit('after', END + timedelta(seconds=10), ends=(END, None)))
    assert second != first
    assert set(rows(store)) == {first, second}
    # The closed row keeps exactly what it had.
    assert rows(store)[first]['finished_at'] == T0 + timedelta(seconds=5)
    # Later audio on the same side joins the new row, not the closed one.
    assert run(unit('after-2', END + timedelta(seconds=25), ends=(END, None))) == second
    assert len(rows(store)) == 2


def test_late_audio_from_before_the_end_still_joins_the_closed_row(attach):
    store, run = attach
    first = run(unit('before', T0))
    second = run(unit('after', END + timedelta(seconds=10), ends=(END, None)))
    # Recorded 7 s after the first unit, before the End, but transcribed last.
    assert run(unit('late', T0 + timedelta(seconds=7), ends=(None, END))) == first
    assert set(rows(store)) == {first, second}


def test_the_ends_are_never_stored(attach):
    store, run = attach
    run(unit('before', T0))
    run(unit('after', END + timedelta(seconds=10), ends=(END, None)))
    assert all(ATTACH_KEY not in row for row in store.rows.values())


@pytest.mark.parametrize(
    'row_start, ends, expected',
    [
        (T0, None, False),
        (T0, (None, None), False),
        (T0, (END, None), True),  # Row began before the End, unit is after it.
        (END, (END, None), False),  # Row began at the End: same side as the unit.
        (END + timedelta(seconds=1), (END, None), False),
        (END + timedelta(seconds=1), (None, END), True),  # Row began after the End, unit is before it.
        (T0, (None, END), False),
        ('not a time', (END, None), False),
    ],
)
def test_separated_by_end(row_start, ends, expected):
    assert separated_by_end(row_start, ends) is expected


def test_off_reads_nothing(off, monkeypatch):
    around = Mock()
    monkeypatch.setattr(cuts_db, 'around', around)
    assert manual_cuts.ends_around('owner', unit('after', END)) is None
    around.assert_not_called()


def test_on_reads_the_ends_around_the_units_first_speech(on, monkeypatch):
    around = Mock(return_value=(END, None))
    monkeypatch.setattr(cuts_db, 'around', around)
    incoming = unit('after', END + timedelta(seconds=10))
    incoming['transcript_segments'][0]['start'] = 2.0
    assert manual_cuts.ends_around('owner', incoming, firestore_client='client') == (END, None)
    around.assert_called_once_with('owner', END + timedelta(seconds=12), firestore_client='client')


def test_on_without_any_end_nearby_changes_nothing(on, monkeypatch):
    monkeypatch.setattr(cuts_db, 'around', Mock(return_value=(None, None)))
    assert manual_cuts.ends_around('owner', unit('after', END)) is None


def test_on_skips_an_owner_outside_v3_a_unit_without_speech_and_any_fault(on, monkeypatch):
    around = Mock(side_effect=RuntimeError('synthetic read failure'))
    monkeypatch.setattr(cuts_db, 'around', around)
    assert manual_cuts.ends_around('owner', unit('after', END)) is None  # A fault keeps the baseline.
    silent = unit('silent', END)
    silent['transcript_segments'] = []
    around.reset_mock()
    assert manual_cuts.ends_around('owner', silent) is None
    monkeypatch.setattr(manual_cuts, 'conversations_v3_enabled', lambda uid: False)
    assert manual_cuts.ends_around('owner', unit('after', END)) is None
    around.assert_not_called()


def test_the_batch_projection_hands_the_ends_to_the_attach_step_only_when_on(monkeypatch):
    from tests.unit.test_batch_projection_v3_admission import _run_projection

    monkeypatch.setattr(manual_cuts, 'conversations_v3_enabled', lambda uid: True)
    monkeypatch.setattr(manual_cuts, 'ends_around', Mock(return_value=None))
    incoming, _, _ = _run_projection(monkeypatch, admitted=True)
    assert ATTACH_KEY not in incoming

    monkeypatch.setattr(manual_cuts, 'ends_around', Mock(return_value=(END, None)))
    incoming, _, finished = _run_projection(monkeypatch, admitted=True)
    assert incoming[ATTACH_KEY] == (END, None)
    assert finished == [True]
