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
async def test_a_failed_pointer_move_still_finishes_the_successor_and_counts_it(monkeypatch):
    from routers.listen import conversations as controller_module

    harness = _harness(monkeypatch)
    controller, sealed = _connect(harness)
    await controller.prepare()
    first = controller.host.state.current_conversation_id
    outcomes = []
    monkeypatch.setattr(controller_module, 'record_rotation', outcomes.append)

    def broken(*args, **kwargs):
        raise RuntimeError('firestore')

    monkeypatch.setattr(controller_module, 'supersede_live_continuation', broken)
    call = harness.call

    async def calls(fn, *args, **kwargs):
        if fn is broken:
            return fn(*args, **kwargs)
        return await call(fn, *args, **kwargs)

    controller.host.persistence.call = calls
    events = len(harness.events)
    harness.now += timedelta(minutes=3)
    await controller._rotate_v3_recording(first)
    successor = controller.host.state.current_conversation_id
    assert successor != first and sealed == [first]
    assert 'pointer_failed' in outcomes and 'rotated' in outcomes
    assert harness.pointer == successor  # the Redis in-progress id and the tail ran
    assert len(harness.events) > events  # send_conversation_session reached the phone


@pytest.mark.anyio
async def test_rotation_successor_stays_v3_for_a_held_out_owner(monkeypatch):
    """SCA-2918: a held-out owner's capture in flight rotates into a v3 successor, not a legacy row."""
    from utils.conversations.v3 import triggers

    monkeypatch.setattr(triggers, 'conversations_v3_enabled', lambda uid: True)
    monkeypatch.setattr(triggers, 'v3_intake_held_out', lambda uid: True)
    monkeypatch.setattr(triggers, '_mark_resolved', lambda uid, row: row.update(recording=True))
    harness = _harness(monkeypatch)
    inner = harness.call
    continuations = []

    async def calls(fn, *args, **kwargs):
        if fn.__name__ == 'create_in_progress_conversation':
            # The lifecycle create's own intake decision, ahead of the harness store write.
            continuations.append(kwargs.get('v3_continuation', False))
            triggers.mark_new(args[0], args[1], continuation=kwargs.get('v3_continuation', False))
        return await inner(fn, *args, **kwargs)

    harness.call = calls
    controller, sealed = _connect(harness)
    await controller.prepare()
    first = controller.host.state.current_conversation_id
    # Mid-capture: this recording was admitted to v3 before the owner was held out.
    harness.rows[first]['recording'] = True
    harness.now += timedelta(minutes=3)
    await controller._rotate_v3_recording(first)
    successor = controller.host.state.current_conversation_id
    assert successor != first and sealed == [first]
    assert continuations == [False, True]
    assert harness.rows[successor]['recording'] is True
