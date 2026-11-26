"""v3 rotation through the real create path on a socket that names its client recording."""

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from database import listen_continuations
from tests.unit.test_listen_reconnect_continuity import CaptureHarness

ROOT = ('users', 'u', 'recording_sessions', 'original')


def _harness(monkeypatch):
    harness = CaptureHarness(monkeypatch)
    call = harness.call

    async def calls(fn, *args, **kwargs):
        if fn is listen_continuations.supersede_live_continuation:
            return fn(*args, firestore_client=harness.store, **kwargs)
        if fn.__name__ == 'update_conversation':
            harness.rows[args[1]].update(args[2])
            return True
        return await call(fn, *args, **kwargs)

    harness.call = calls
    return harness


def _connect(harness):
    controller = harness.connect()
    controller.host.persistence.call = harness.call
    sealed = []

    async def process(cid):
        sealed.append(cid)
        harness.rows[cid]['status'] = 'processing'
        return True

    controller.process_conversation = process
    return controller, sealed


@pytest.mark.anyio
async def test_without_supersede_the_live_pointer_resumes_the_same_row(monkeypatch):
    harness = _harness(monkeypatch)
    controller, _ = _connect(harness)
    await controller.prepare()
    current = controller.host.state.current_conversation_id
    await controller.create_new_in_progress_conversation(rollover=True)
    assert controller.host.state.current_conversation_id == current  # the bug the supersede mode fixes


@pytest.mark.anyio
async def test_consecutive_rotations_move_the_pointer_and_seal_every_recording(monkeypatch):
    harness = _harness(monkeypatch)
    controller, sealed = _connect(harness)
    await controller.prepare()
    ids = [controller.host.state.current_conversation_id]
    for _ in range(4):
        harness.now += timedelta(minutes=3)
        await controller._rotate_v3_recording(ids[-1])
        ids.append(controller.host.state.current_conversation_id)
        assert harness.store.rows[ROOT]['live_continuation']['conversation_id'] == ids[-1]
    assert len(set(ids)) == 5
    assert sealed == ids[:-1]
    assert controller._unsealed_rotations == {} and controller._rotation_retry_at is None
    assert all(harness.rows[cid]['v3_rotation_cap_seconds'] == 300.0 for cid in ids[:-1])
    assert not harness.deleted and harness.rows[ids[-1]]['status'] == 'in_progress'
    # A reconnect resumes the successor, never a sealed recording.
    harness.now += timedelta(seconds=30)
    reconnect, _ = _connect(harness)
    await reconnect.prepare()
    assert reconnect.host.state.current_conversation_id == ids[-1]


def test_supersede_never_steals_a_pointer_another_generation_owns():
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    store = StrictFirestore()
    store.rows[ROOT] = dict(uid='u', recording_session_id='original', live_continuation={'conversation_id': 'other'})
    moved = listen_continuations.supersede_live_continuation(
        'u',
        'original',
        previous_id='old',
        proposed={'conversation_id': 'new', 'recording_session_id': 's'},
        firestore_client=store,
    )
    assert moved == 'other_owner' and store.rows[ROOT]['live_continuation'] == {'conversation_id': 'other'}
    assert (
        listen_continuations.supersede_live_continuation(
            'u', 'missing', previous_id='old', proposed={'conversation_id': 'new'}, firestore_client=store
        )
        == 'absent'
    )


@pytest.mark.anyio
async def test_a_failed_successor_never_takes_the_pointer_and_the_retry_moves_it(monkeypatch):
    harness = _harness(monkeypatch)
    controller, sealed = _connect(harness)
    await controller.prepare()
    first = controller.host.state.current_conversation_id
    arm = controller._persist_policy_and_arm_quiet_check
    failures = iter([RuntimeError('firestore')])

    async def flaky(cid):
        if cid != first:
            error = next(failures, None)
            if error:
                raise error
        return await arm(cid)

    controller._persist_policy_and_arm_quiet_check = flaky
    harness.now += timedelta(minutes=3)
    await controller._rotate_v3_recording(first)
    assert controller.host.state.current_conversation_id == first and not sealed
    assert harness.store.rows[ROOT]['live_continuation']['conversation_id'] == first
    harness.now += timedelta(seconds=61)
    controller._rotation_retry_at = None
    await controller._rotate_v3_recording(first)
    successor = controller.host.state.current_conversation_id
    assert successor != first and sealed == [first]
    assert harness.store.rows[ROOT]['live_continuation']['conversation_id'] == successor


def test_supersede_accepts_a_pointer_this_socket_left_on_its_own_recording():
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    store = StrictFirestore()
    store.rows[ROOT] = dict(uid='u', recording_session_id='original', live_continuation={'conversation_id': 'mine'})
    moved = listen_continuations.supersede_live_continuation(
        'u',
        'original',
        previous_id='old',
        proposed={'conversation_id': 'new', 'recording_session_id': 's'},
        own_ids=['mine', 'old'],
        firestore_client=store,
    )
    assert moved == 'moved' and store.rows[ROOT]['live_continuation']['conversation_id'] == 'new'


@pytest.mark.anyio
async def test_a_failed_pointer_move_does_not_seal_the_previous_recording(monkeypatch):
    from routers.listen import conversations as controller_module

    harness = _harness(monkeypatch)
    controller, sealed = _connect(harness)
    await controller.prepare()
    first = controller.host.state.current_conversation_id
    harness.store.rows[ROOT]['live_continuation'] = {
        'conversation_id': first,
        'recording_session_id': 'original',
    }
    outcomes = []
    monkeypatch.setattr(controller_module, 'record_rotation', outcomes.append)

    def broken(*args, **kwargs):
        raise RuntimeError('firestore')

    def unavailable_readback(*args, **kwargs):
        raise RuntimeError('firestore unavailable')

    monkeypatch.setattr(controller_module, 'supersede_live_continuation', broken)
    monkeypatch.setattr(listen_continuations, 'resolve_live_continuation', unavailable_readback)
    call = harness.call

    async def calls(fn, *args, **kwargs):
        if fn is broken:
            return fn(*args, **kwargs)
        return await call(fn, *args, **kwargs)

    controller.host.persistence.call = calls
    harness.now += timedelta(minutes=3)
    await controller._rotate_v3_recording(first)
    assert controller.host.state.current_conversation_id == first
    assert sealed == [] and controller._unsealed_rotations == {}
    assert harness.store.rows[ROOT]['live_continuation']['conversation_id'] == first
    assert harness.pointer == first
    assert harness.deleted == []
    assert 'pointer_failed' in outcomes and 'rotated' not in outcomes


@pytest.mark.anyio
async def test_an_ambiguous_pointer_write_is_read_back_before_sealing(monkeypatch):
    from routers.listen import conversations as controller_module

    harness = _harness(monkeypatch)
    controller, sealed = _connect(harness)
    await controller.prepare()
    first = controller.host.state.current_conversation_id
    outcomes = []
    monkeypatch.setattr(controller_module, 'record_rotation', outcomes.append)

    def committed_then_timed_out(uid, origin_id, *, previous_id, proposed, **kwargs):
        harness.store.rows[ROOT]['live_continuation'] = dict(proposed)
        raise RuntimeError('response lost after commit')

    monkeypatch.setattr(controller_module, 'supersede_live_continuation', committed_then_timed_out)
    call = harness.call

    async def calls(fn, *args, **kwargs):
        if fn is committed_then_timed_out:
            return fn(*args, **kwargs)
        return await call(fn, *args, **kwargs)

    controller.host.persistence.call = calls
    harness.now += timedelta(minutes=3)
    await controller._rotate_v3_recording(first)
    successor = controller.host.state.current_conversation_id
    assert successor != first and sealed == [first]
    assert harness.store.rows[ROOT]['live_continuation']['conversation_id'] == successor
    assert 'pointer_failed' in outcomes and 'rotated' in outcomes
