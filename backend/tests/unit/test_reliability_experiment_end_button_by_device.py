"""Experiment ``end_button_by_device``: an open v3 conversation names the app install behind its latest speech.

Off (the default) the builder writes no such field and the live read serves none, so the ordinary v3
suites assert production's behaviour unchanged. On, the builder copies ``client_device_id`` from the
recording that carries the latest speech line, and ``GET /v1/conversations/live`` hands it to the owner.
"""

from datetime import datetime, timedelta, timezone

import pytest

from config import reliability_experiments
from models.conversation import ConversationsLiveResponse
from routers import conversations as routes
from utils.conversations.v3 import capture_device
from tests.unit.test_conversations_v3_claim_growth import strict, owners_import, path  # noqa: F401
from tests.unit.test_conversations_v3_live_passes import T0, derived, put_recording, reconcile_at, speech, timing

EXPERIMENT = 'end_button_by_device'
PHONE = 'ios_06b76a44'
DESKTOP = 'macos_0a1b2c3d'


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv(reliability_experiments.ENV, EXPERIMENT)


@pytest.fixture
def off(monkeypatch):
    monkeypatch.delenv(reliability_experiments.ENV, raising=False)


@pytest.fixture(autouse=True)
def quiet_builder(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_LIVE_TITLE', 'off')


def test_registered():
    assert EXPERIMENT in reliability_experiments.EXPERIMENTS


def line(recording_id, end):
    return {'conversation_id': recording_id, 'end': end}


def test_latest_is_the_device_of_the_recording_whose_line_ends_last():
    recordings = {'phone': {'client_device_id': PHONE}, 'desktop': {'client_device_id': DESKTOP}}
    assert capture_device.latest([line('phone', 10), line('desktop', 30), line('phone', 20)], recordings) == DESKTOP
    assert capture_device.latest([line('desktop', 30), line('phone', 40)], recordings) == PHONE
    assert capture_device.latest([], recordings) is None


@pytest.mark.parametrize('stored', [None, '', 'ios', 'ios_06B76A44', 'ios_06b76a4', 'pendant_06b76a44', 7])
def test_a_recording_without_a_well_formed_device_names_none(stored):
    assert capture_device.latest([line('r', 10)], {'r': {'client_device_id': stored}}) is None
    assert capture_device.served({capture_device.FIELD: stored}) is None


def test_stamp_sets_the_field_and_clears_a_stale_one():
    row = {}
    capture_device.stamp(row, [line('r', 10)], {'r': {'client_device_id': PHONE}})
    assert row == {capture_device.FIELD: PHONE}
    # The latest speech now comes from a client that sent no device headers: the old name must not stay.
    capture_device.stamp(row, [line('r', 10), line('other', 20)], {'r': {'client_device_id': PHONE}, 'other': {}})
    assert row == {}


def put_second_recording(strict, *, device, starts_after):
    segments = [{'id': 'd0', 'text': 'word ' * 12, 'start': 0.0, 'end': 20.0, 'is_user': True}]
    started = T0 + timedelta(seconds=starts_after)
    strict.rows[path('r2')] = {
        'id': 'r2',
        'recording': True,
        'source': 'omi',
        'status': 'completed',
        'started_at': started,
        'finished_at': started + timedelta(seconds=20),
        'data_protection_level': 'standard',
        'transcript_segments': segments,
        'claims': [],
        'v3_pending': True,
        'v3_pending_since': started + timedelta(seconds=25),
        'v3_speech_landed_at': started + timedelta(seconds=25),
        'client_device_id': device,
    }


@pytest.mark.asyncio
async def test_off_the_builder_writes_no_device(off, strict, monkeypatch):
    timing(monkeypatch, 900, 900)
    segments = speech(4)
    landed = T0 + timedelta(seconds=segments[-1]['end'] + 30)
    put_recording(strict, segments, status='in_progress', landed=landed)
    strict.rows[path('r')]['client_device_id'] = PHONE
    assert await reconcile_at(strict, monkeypatch, landed) == 'committed'
    (row,) = derived(strict)
    assert row['tile_state'] == 'live'
    assert capture_device.FIELD not in row


@pytest.mark.asyncio
async def test_on_the_open_conversation_follows_the_device_behind_its_latest_speech(on, strict, monkeypatch):
    timing(monkeypatch, 900, 900)
    segments = speech(4)
    landed = T0 + timedelta(seconds=segments[-1]['end'] + 30)
    put_recording(strict, segments, status='in_progress', landed=landed)
    strict.rows[path('r')]['client_device_id'] = PHONE
    assert await reconcile_at(strict, monkeypatch, landed) == 'committed'
    (row,) = derived(strict)
    assert row['tile_state'] == 'live' and row[capture_device.FIELD] == PHONE

    # Another device's recording lands with later speech inside the same conversation.
    put_second_recording(strict, device=DESKTOP, starts_after=segments[-1]['end'] + 40)
    assert await reconcile_at(strict, monkeypatch, landed + timedelta(seconds=60)) == 'committed'
    (row,) = derived(strict)
    assert row['v3_recording_ids'] == ['r', 'r2']
    assert row['tile_state'] == 'live' and row[capture_device.FIELD] == DESKTOP


def serve(monkeypatch, **extra):
    now = datetime.now(timezone.utc) - timedelta(minutes=1)
    row = {
        'id': 'open',
        'status': 'in_progress',
        'created_at': now,
        'started_at': now,
        'finished_at': now,
        'v3_derived': True,
        'tile_state': 'live',
        'structured': {'title': 'Plan', 'emoji': '🌳'},
        'v3_recording_ids': ['r'],
        **extra,
    }
    monkeypatch.setattr(routes, 'conversations_v3_enabled', lambda uid: True)
    monkeypatch.setattr(routes.conversations_v3_live, 'recent_windows', lambda uid, **kw: ([row], 1))
    monkeypatch.setattr(routes.v3_client_capability, 'note_capable', lambda uid: None)
    result = routes.get_live_conversation('u', 'store')
    return ConversationsLiveResponse(**result).model_dump(exclude_unset=True)['conversation']


def test_off_the_live_read_serves_no_device_even_when_a_row_holds_one(off, monkeypatch):
    assert capture_device.FIELD not in serve(monkeypatch, **{capture_device.FIELD: PHONE})


def test_on_the_live_read_serves_the_device_to_the_owner(on, monkeypatch):
    assert serve(monkeypatch, **{capture_device.FIELD: PHONE})[capture_device.FIELD] == PHONE


def test_on_the_live_read_serves_nothing_for_a_row_without_one_or_a_locked_one(on, monkeypatch):
    assert capture_device.FIELD not in serve(monkeypatch)
    assert capture_device.FIELD not in serve(monkeypatch, **{capture_device.FIELD: 'not a device id'})
    assert capture_device.FIELD not in serve(monkeypatch, is_locked=True, **{capture_device.FIELD: PHONE})
