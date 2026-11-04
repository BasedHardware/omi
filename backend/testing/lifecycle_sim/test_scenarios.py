"""Executable invariants. Setup failures are never accepted as known leaks."""

import asyncio
from pathlib import Path
import os
import time
from types import SimpleNamespace

import pytest
from google.api_core.exceptions import Aborted

from database import record_audio
from testing.lifecycle_sim.faults import BoundaryFault, InjectedLifecycleFault
from testing.lifecycle_sim.harness import LifecycleSim
from testing.listen_pusher_stack.run import Stack
from utils.batch_pipeline import live
from utils.batch_pipeline import record_producer_proof
from utils.conversations.phase import ConversationPhase


class LifecycleInvariantError(AssertionError):
    """Only a final lifecycle invariant may satisfy an expected leak failure."""


def invariant(condition, message):
    if not condition:
        raise LifecycleInvariantError(message)


@pytest.fixture(scope='module')
def stack():
    value = Stack(Path(os.environ['LIFECYCLE_SIM_STATE_DIR']))
    try:
        yield value
    finally:
        value.close()


@pytest.fixture
def lifecycle_sim(stack):
    sim = LifecycleSim(stack)
    try:
        yield sim
    finally:
        sim.close()


@pytest.mark.asyncio
async def test_happy_path_reaches_complete(lifecycle_sim):
    sim = lifecycle_sim
    sim.seed()
    assert sim.seal() is None
    assert sim.register()
    assert sim.job()['state'] == 'record_pending'
    for _ in range(3):
        await sim.tick()
        if sim.phase in {ConversationPhase.TRANSCRIBED, ConversationPhase.COMPLETE, ConversationPhase.SETTLED}:
            break
    assert sim.phase in {ConversationPhase.TRANSCRIBED, ConversationPhase.COMPLETE, ConversationPhase.SETTLED}
    await sim.complete()
    assert sim.phase in {
        ConversationPhase.COMPLETE,
        ConversationPhase.SETTLED,
    }, 'happy control did not persist its summary'


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True, raises=LifecycleInvariantError, reason='waits on freshtitles record_pending drain lease fix PR #24587'
)
async def test_sealed_record_pending_admitted_within_budget(lifecycle_sim, monkeypatch):
    sim = lifecycle_sim
    sim.seed()
    assert sim.seal() is None
    assert sim.register()
    sim.age()
    # Hold only the first admission at its entry, without replacing its body.
    # A second replica either observes its claim and returns, or enters the
    # same admission concurrently. Both schedules are released without sleeps.
    original = live.admit_recording
    first_entered, duplicate_entered, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    active, peak = 0, 0
    errors = []

    async def observe(store, pending, **kwargs):
        nonlocal active, peak
        if pending['segment_id'] != sim.segment:
            return await original(store, pending, **kwargs)
        active += 1
        peak = max(active, peak)
        first_entered.set()
        if active > 1:
            duplicate_entered.set()
        try:
            await release.wait()
            return await original(store, pending, **kwargs)
        except Exception as error:
            errors.append(error)
            raise
        finally:
            active -= 1

    monkeypatch.setattr(live, 'admit_recording', observe)
    first = asyncio.create_task(sim.drain())
    second = None
    duplicate = None
    try:
        await asyncio.wait_for(first_entered.wait(), timeout=10)
        second = asyncio.create_task(sim.drain())
        duplicate = asyncio.create_task(duplicate_entered.wait())
        done, _ = await asyncio.wait({second, duplicate}, timeout=10, return_when=asyncio.FIRST_COMPLETED)
        assert done, 'second drain did not reach an observable boundary'
    finally:
        release.set()
        await asyncio.gather(*(task for task in (first, second) if task is not None))
        if duplicate is not None:
            duplicate.cancel()
            await asyncio.gather(duplicate, return_exceptions=True)
    monkeypatch.setattr(live, 'admit_recording', original)
    assert all(isinstance(error, Aborted) for error in errors), 'admission failed for a non-contention reason'
    await sim.tick()
    assert sim.phase in {
        ConversationPhase.TRANSCRIBED,
        ConversationPhase.COMPLETE,
        ConversationPhase.SETTLED,
    }, 'fixture could not drive the admitted row to a transcript'
    invariant(peak == 1, f'record_pending entered admission concurrently on {peak} replicas; expected one lease owner')


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True, raises=LifecycleInvariantError, reason='waits on freshtitles no-batch-job-after-seal fix, no PR yet'
)
async def test_sealed_no_job_registered_recovered(lifecycle_sim):
    sim = lifecycle_sim
    sim.seed()
    assert sim.seal() is None
    sim.fault = BoundaryFault('register', sim.uid, sim.cid)
    with pytest.raises(InjectedLifecycleFault):
        sim.register()
    assert sim.fault.fired and not sim.job()
    sim.fault = None
    for _ in range(3):
        sim.sweep()
        sim.recover_nojob()
        await sim.tick()
    invariant(sim.job(), 'sealed capture has no registration after sweeper and no-job recovery')
    invariant(
        sim.phase in {ConversationPhase.TRANSCRIBED, ConversationPhase.COMPLETE, ConversationPhase.SETTLED},
        'recovered no-job capture missed transcription budget',
    )


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True, raises=LifecycleInvariantError, reason='waits on freshtitles failed-upload retry fix, no PR yet'
)
async def test_upload_failed_gets_retried(lifecycle_sim):
    sim = lifecycle_sim
    sim.seed()
    assert sim.register()
    assert record_audio.mark_record_upload_failed(sim.uid, sim.cid, firestore_client=sim.stack.firestore)
    assert sim.row()['record_upload_failed']
    assert record_audio.set_record_upload_pending(sim.uid, sim.cid, 'retry', True, firestore_client=sim.stack.firestore)
    sim.reupload()
    # Only the new producer's token is cleared; no fixture edits the sticky bit.
    assert record_audio.set_record_upload_pending(
        sim.uid, sim.cid, 'retry', False, firestore_client=sim.stack.firestore
    )
    sim.seal()
    sim.age()
    for _ in range(3):
        sim.sweep()
        await sim.tick()
        sim.age(61)
    invariant(
        sim.phase in {ConversationPhase.TRANSCRIBED, ConversationPhase.COMPLETE, ConversationPhase.SETTLED},
        'successful re-upload remains failed and outside custody',
    )


@pytest.mark.asyncio
async def test_open_sessions_dead_producer_sealed_within_budget(lifecycle_sim, monkeypatch):
    sim = lifecycle_sim
    sim.seed()
    await sim.start_pusher_with_live_token()
    assert sim.register()
    sim.age()
    assert sim.seal() == 'producer_pending'
    sim.kill_pusher()
    assert sim.row()['record_upload_sessions'], 'process death unexpectedly removed its durable tokens'
    # Cross the integer process-start safety margin with fake proof time. No
    # token timestamps or custody fields are edited and no sleep is needed.
    sim.proof_time = time.time() + 3
    monkeypatch.setattr(record_producer_proof, 'time', SimpleNamespace(time=lambda: sim.proof_time))
    for _ in range(3):
        sim.sweep()
        await sim.tick()
        sim.age(61)
    assert sim.row().get('record_audio_closed'), 'dead-producer capture missed seal budget'
    assert sim.phase in {ConversationPhase.TRANSCRIBED, ConversationPhase.COMPLETE, ConversationPhase.SETTLED}
