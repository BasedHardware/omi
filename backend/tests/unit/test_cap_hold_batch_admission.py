"""Cap-held audio re-enters through batch admission once legacy is draining or dark (synthetic only)."""

import io
import json
import wave
from types import SimpleNamespace

import pytest
from fastapi.responses import JSONResponse

from utils.batch_pipeline import cap_hold_admission as adapter
from utils.batch_pipeline import intake
from utils.sync import cap_hold, cap_hold_recovery
from utils.sync.legacy_dark import LegacySyncMode
from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

UID = 'synthetic-owner'


def _wav(path, seconds, rate=16000):
    with wave.open(str(path), 'wb') as stream:
        stream.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        stream.writeframes(b'\1\0' * int(seconds * rate))


def test_derived_content_id_is_stable_per_hold_and_never_the_legacy_one():
    first = adapter.held_content_id(UID, 'hold-1')
    assert first == adapter.held_content_id(UID, 'hold-1')
    assert first != adapter.held_content_id(UID, 'hold-2') != adapter.held_content_id('other', 'hold-1')
    assert len(first) == 64


@pytest.mark.parametrize(
    'row,expected',
    [
        ({'state': 'held'}, True),
        ({'state': 'held', 'piece_plan': {'a': {}}}, True),  # planning spends nothing
        ({'state': 'held', 'piece_receipts': {'a': {'state': 'dispatched'}}}, False),
        ({'state': 'held', 'processed_paths': ['a']}, False),
        ({'state': 'staging'}, False),
        ({'state': 'sealing'}, False),
        ({'state': 'batch_admitted', 'batch_job_id': 'bp_x'}, False),
        ({'state': 'completed'}, False),
    ],
)
def test_only_unspent_sealed_holds_are_eligible(row, expected):
    assert adapter.eligible(row) is expected
    assert adapter.enabled_for(row, LegacySyncMode.DRAINING) is expected
    assert adapter.enabled_for(row, LegacySyncMode.DARK) is expected
    assert adapter.enabled_for(row, LegacySyncMode.ON) is False


def test_held_wav_becomes_bounded_units_on_the_capture_clock(tmp_path):
    path = tmp_path / 'held.wav'
    _wav(path, 5.0, rate=8000)  # resampled to 16 kHz canonical PCM
    units = list(adapter.wav_units(str(path), 1000.0, 2.0))
    assert [u.capture_at for u in units] == [1000.0, 1002.0, 1004.0]
    assert [round(u.duration_seconds, 3) for u in units] == [2.0, 2.0, 1.0]
    with pytest.raises(ValueError):
        list(adapter.wav_units(str(path), 1000.0, 7201))


@pytest.fixture
def held(monkeypatch, tmp_path):
    meta = {
        'timestamp': 1700000000,
        'source': 'omi',
        'target_conversation_id': 'conv-1',
        'client_device_id': 'device-1',
        'client_platform': 'ios',
    }
    monkeypatch.setattr(cap_hold, 'metadata', lambda uid, row: dict(meta))
    monkeypatch.setattr(cap_hold, 'read_audio', lambda uid, row, path: _wav(path, 3.0))

    class Directory:
        name = str(tmp_path)
        cleaned = False

        def cleanup(self):
            Directory.cleaned = True

    monkeypatch.setattr(cap_hold, 'recovery_directory', lambda uid: Directory())
    calls = []
    answer = {'response': JSONResponse(status_code=202, content={'status': 'queued'})}

    async def accept_upload(**kwargs):
        calls.append(kwargs)
        units = list(kwargs['decode'](3600))
        assert units and units[0].capture_at == 1700000000.0
        return answer['response']

    monkeypatch.setattr(intake, 'accept_upload', accept_upload)
    return SimpleNamespace(calls=calls, answer=answer, directory=Directory, snapshot=SimpleNamespace(id='hold-1'))


@pytest.mark.asyncio
async def test_admits_under_the_derived_identity_and_is_idempotent(held):
    first = await adapter.admit_held(UID, held.snapshot, {'state': 'held'})
    second = await adapter.admit_held(UID, held.snapshot, {'state': 'held'})
    content_id = adapter.held_content_id(UID, 'hold-1')
    assert first == second == adapter.HeldAdmission('admitted', 'bp_' + content_id[:32])
    call = held.calls[0]
    assert call['content_id'] == content_id and call['job_id'] == content_id[:32]
    assert call['should_lock'] is False and 'byok_enabled' not in call
    assert (call['conversation_id'], call['source'], call['lane']) == ('conv-1', 'omi', 'backfill')
    assert held.calls[1]['content_id'] == content_id  # a retried sweep re-presents the same content
    assert held.directory.cleaned


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'response,expected',
    [
        (
            JSONResponse(status_code=409, content={'code': 'sync_content_in_progress', 'job_id': 'OWN'}),
            'already_admitted',
        ),
        (JSONResponse(status_code=409, content={'code': 'sync_content_in_progress', 'job_id': 'bp_other'}), 'retry'),
        (JSONResponse(status_code=409, content={'code': 'sync_batch_privacy_blocked'}), 'privacy_blocked'),
        (JSONResponse(status_code=503, content={'code': 'sync_batch_unavailable'}), 'retry'),
        (None, 'retry'),
    ],
)
async def test_non_admission_answers_never_hand_the_hold_off(held, response, expected):
    own = 'bp_' + adapter.held_content_id(UID, 'hold-1')[:32]
    if response is not None and json.loads(response.body).get('job_id') == 'OWN':
        response = JSONResponse(status_code=409, content={'code': 'sync_content_in_progress', 'job_id': own})
    held.answer['response'] = response
    assert (await adapter.admit_held(UID, held.snapshot, {'state': 'held'})).outcome == expected


@pytest.mark.asyncio
async def test_holds_with_legacy_spend_are_refused(held):
    with pytest.raises(ValueError):
        await adapter.admit_held(UID, held.snapshot, {'state': 'held', 'piece_receipts': {'a': {}}})
    assert held.calls == []


# --- the recover_selected hook ---------------------------------------------------------------------


@pytest.fixture
def hook(monkeypatch):
    events = []
    row = {'state': 'held', 'lease_token': 'lease'}
    monkeypatch.setattr(cap_hold, 'claim', lambda uid, ref, now: dict(row))
    monkeypatch.setattr(cap_hold, 'release', lambda uid, ref, token: events.append(('release', token)))

    async def save(uid, snapshot, current, updates):
        events.append(('save', updates))
        current.update(updates)
        return True

    async def legacy(uid, snapshot, current):
        events.append(('legacy',))
        return True

    monkeypatch.setattr(cap_hold_recovery, '_save', save)
    monkeypatch.setattr(cap_hold_recovery, '_recover_row', legacy)
    monkeypatch.setattr(cap_hold_recovery, '_erase', lambda uid, snapshot, current: events.append(('erase',)))
    monkeypatch.setattr(cap_hold_recovery, '_settle_and_erase', lambda *a: events.append(('settle_and_erase',)))
    monkeypatch.setattr(cap_hold_recovery, '_new_dispatch_allowed', lambda uid, lane: True)

    async def selected_lane(uid, current):
        return 'sync'  # main #22494: recovery follows the hold's original lane (missing legacy origin = sync)

    monkeypatch.setattr(cap_hold_recovery, '_selected_lane', selected_lane)
    snapshot = SimpleNamespace(id='hold-1', reference=object(), to_dict=lambda: dict(row))
    return SimpleNamespace(events=events, snapshot=snapshot, row=row)


@pytest.mark.asyncio
async def test_draining_hands_the_hold_to_batch_and_never_runs_legacy(hook, monkeypatch):
    monkeypatch.setattr(adapter, 'enabled_for', lambda row, mode=None: True)

    async def admit(uid, snapshot, row):
        return adapter.HeldAdmission('admitted', 'bp_job')

    monkeypatch.setattr(adapter, 'admit_held', admit)
    # The funded-capacity reservation (lane 6) lands before the hand-off is durable.
    monkeypatch.setattr(
        cap_hold_recovery.cap_hold_reservations,
        'reserve',
        lambda uid, hold_id, **kwargs: hook.events.append(('reserve', hold_id, kwargs['batch_job_id'])),
    )
    assert await cap_hold_recovery.recover_selected(UID, hook.snapshot) is True
    assert hook.events == [
        ('reserve', 'hold-1', 'bp_job'),
        ('save', {'state': 'batch_admitted', 'batch_job_id': 'bp_job'}),
        ('erase',),
        ('release', 'lease'),
    ]


@pytest.mark.asyncio
async def test_unadmitted_hold_stays_held_for_the_next_sweep(hook, monkeypatch):
    monkeypatch.setattr(adapter, 'enabled_for', lambda row, mode=None: True)

    async def admit(uid, snapshot, row):
        return adapter.HeldAdmission('retry')

    monkeypatch.setattr(adapter, 'admit_held', admit)
    assert await cap_hold_recovery.recover_selected(UID, hook.snapshot) is False
    assert hook.events == [('release', 'lease')]


@pytest.mark.asyncio
async def test_on_keeps_the_legacy_recovery_path(hook, monkeypatch):
    monkeypatch.setattr(adapter, 'enabled_for', lambda row, mode=None: False)
    assert await cap_hold_recovery.recover_selected(UID, hook.snapshot) is True
    assert ('legacy',) in hook.events and ('erase',) not in hook.events


@pytest.mark.asyncio
async def test_restricted_or_capped_owner_keeps_the_audio_held(hook, monkeypatch):
    monkeypatch.setattr(adapter, 'enabled_for', lambda row, mode=None: True)
    monkeypatch.setattr(cap_hold_recovery, '_new_dispatch_allowed', lambda uid, lane: False)
    monkeypatch.setattr(adapter, 'admit_held', lambda *a: pytest.fail('gated owner admitted'))
    assert await cap_hold_recovery.recover_selected(UID, hook.snapshot) is False
    assert hook.events == [('release', 'lease')]


@pytest.mark.asyncio
async def test_reselecting_a_batch_admitted_row_is_a_no_op(hook, monkeypatch):
    hook.row.update(state='batch_admitted', batch_job_id='bp_job')
    monkeypatch.setattr(cap_hold, 'claim', lambda *a: pytest.fail('terminal hand-off claimed again'))
    monkeypatch.setattr(adapter, 'admit_held', lambda *a: pytest.fail('terminal hand-off re-admitted'))
    assert await cap_hold_recovery.recover_selected(UID, hook.snapshot) is True
    assert hook.events == [('erase',)]  # finishes an interrupted erase only; never settles (no double bill)


def test_batch_admitted_transition_leaves_nothing_held_so_checkpoint_decrements_the_summary():
    held = {'state': 'held', 'seconds': 42.0}
    assert cap_hold.remaining_seconds(held) == 42.0
    assert cap_hold.remaining_seconds({**held, 'state': 'batch_admitted', 'batch_job_id': 'bp_job'}) == 0.0


def test_checkpoint_decrements_the_held_summary_once_on_batch_admitted(monkeypatch):
    from contextlib import nullcontext
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    path = ('users', UID, 'stt_cap_holds', 'hold-1')
    summary = ('users', UID, cap_hold.SUMMARY_COLLECTION, 'current')
    client = StrictFirestore(
        {
            path: {'state': 'held', 'seconds': 42.0, 'lease_until': 0},
            summary: {'version': 2, 'seconds': 42.0, 'count': 1},
        }
    )
    ref = client.document('/'.join(path))
    monkeypatch.setattr(cap_hold, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(cap_hold, 'external_write_fence', lambda _: nullcontext())
    monkeypatch.setattr(cap_hold, 'ensure_summary', lambda uid: None)
    monkeypatch.setattr(cap_hold, 'forget_request_reads', lambda uid: None)
    monkeypatch.setattr(cap_hold.time, 'time', lambda: 100.0)
    token = cap_hold.claim(UID, ref, 100.0)['lease_token']
    handoff = {'state': 'batch_admitted', 'batch_job_id': 'bp_job'}
    assert cap_hold.checkpoint(UID, ref, token, handoff)
    assert client.rows[summary] == {'version': 2, 'seconds': 0.0, 'count': 0}
    assert cap_hold.checkpoint(UID, ref, token, handoff)  # a retried save never double-decrements
    assert client.rows[summary] == {'version': 2, 'seconds': 0.0, 'count': 0}
