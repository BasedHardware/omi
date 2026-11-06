"""Executable invariants. Setup failures are never accepted as known leaks."""

import asyncio
from pathlib import Path
import os
import time
import shutil
from types import SimpleNamespace

import pytest
import httpx
from google.api_core.exceptions import Aborted

from database.conversations import create_audio_files_from_chunks
from database import record_audio
from database import conversation_finalization_jobs as finalization_jobs
from testing.lifecycle_sim.faults import BoundaryFault, InjectedLifecycleFault
from testing.lifecycle_sim.harness import LifecycleSim

# Shared real-Firestore regressions also run in the hermetic lifecycle harness.
from tests.integration.test_batch_held_dead_letter_firestore import (
    lane,  # noqa: F401
    test_worker_fail_expire_and_nightly_redrive_keep_audio_and_cold_queue_integrity,  # noqa: F401
    test_two_forced_requeues_append_once_in_real_firestore,  # noqa: F401
    test_expired_row_survives_rollback_using_only_legacy_dead_redrive,  # noqa: F401
)
from tests.integration.test_batch_projection_held_dead_letter_firestore import (
    held,  # noqa: F401
    test_expiry_content_preserved_and_nightly_flag_off_release_cas,  # noqa: F401
    test_duplicate_nightly_release_increments_attempts_once,  # noqa: F401
    test_pre_change_scan_and_release_recovers_expired_row_with_flag_off,  # noqa: F401
)
from tests.support.lifecycle_state_table import durable_titling_rearm
from testing.listen_pusher_stack.run import Stack, _wait_for_port
from utils.batch_pipeline import live
from utils.batch_pipeline import record_producer_proof, record_seal_sweeper
from utils.conversations.phase import ConversationPhase
from utils.conversations import process_conversation as processing
from utils.enrichment import outbox


class LifecycleInvariantError(AssertionError):
    """Only a final lifecycle invariant may satisfy an expected leak failure."""


def invariant(condition, message):
    if not condition:
        raise LifecycleInvariantError(message)


@pytest.fixture(scope='module')
def stack():
    value = Stack(Path(os.environ['LIFECYCLE_SIM_STATE_DIR']))
    # Reuse the parent's allowlisted Redis endpoint, which product modules
    # loaded during collection already resolved. Own a fresh server there.
    value.redis_port = int(os.environ['REDIS_DB_PORT'])
    value.env['REDIS_DB_PORT'] = str(value.redis_port)
    try:
        binary = shutil.which('redis-server')
        assert binary, 'isolated Redis binary is required'
        child = value._start(
            'redis',
            [binary, '--bind', '127.0.0.1', '--port', str(value.redis_port), '--save', '', '--appendonly', 'no'],
        )
        _wait_for_port(value.redis_port, label='lifecycle Redis', child=child)
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
    # A direct production admission is the positive-control seam: its error
    # propagates rather than being hidden by the drainer's normal retry loop.
    await live.admit_recording(sim.store, sim.job())
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
    persisted = processing.conversations_db.get_conversation(sim.uid, sim.cid)
    assert persisted['structured']['title'] == 'Hermetic finalization'
    assert persisted['structured']['overview'] == 'Provider leaf completed locally.'


@pytest.mark.asyncio
async def test_sealed_record_pending_admitted_within_budget(lifecycle_sim, monkeypatch):
    # PR #24587 fixed the reproduced duplicate entry. Keep this regression green.
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


@pytest.mark.asyncio
async def test_refusal_clock_survives_pod_death_and_reconnect(lifecycle_sim, monkeypatch):
    sim = lifecycle_sim
    sim.seed()
    await sim.start_pusher_with_live_token()
    assert sim.register()
    sim.age()
    async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
        response = await client.post(
            f'http://127.0.0.1:{sim.stack.pusher_port}/__lifecycle/seal',
            json={'uid': sim.uid, 'conversation_id': sim.cid},
        )
    assert response.status_code == 200 and response.json() == {'refusal': 'producer_pending'}
    first = sim.row()['record_seal_refused_at']
    tokens = sim.row()['record_upload_sessions']
    sim.kill_pusher()
    assert sim.row()['record_seal_refused_at'] == first
    # Fresh process retries through the same database helper and durable row.
    await sim.start_pusher_with_live_token()
    async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
        response = await client.post(
            f'http://127.0.0.1:{sim.stack.pusher_port}/__lifecycle/seal',
            json={'uid': sim.uid, 'conversation_id': sim.cid},
        )
    assert response.status_code == 200 and response.json() == {'refusal': 'producer_pending'}
    assert sim.row()['record_seal_refused_at'] == first
    monkeypatch.setattr(record_seal_sweeper, 'time', SimpleNamespace(time=lambda: first + 61))
    report = sim.sweep(live_producer=True)
    assert report['omi_record_seal_refused_count'] == 1
    assert report['omi_record_seal_refused_age_seconds'] >= 60
    assert all(sim.row()['record_upload_sessions'].get(token) == value for token, value in tokens.items())
    # Only exact-token successful drains release custody; the clock grants no authority.
    for token in sim.row()['record_upload_sessions']:
        assert record_audio.set_record_upload_pending(
            sim.uid, sim.cid, token, False, firestore_client=sim.stack.firestore
        )
    assert sim.seal() is None
    assert sim.row()['record_audio_closed']
    assert sim.row()['record_seal_refused_at'] is None
    sim.kill_pusher()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'closed',
    [
        pytest.param(True, id='results-before-finalization'),
        pytest.param(
            False,
            id='closed-before-completed',
            marks=pytest.mark.xfail(
                strict=True,
                raises=LifecycleInvariantError,
                reason='waits on lifecycle capture completion ordering fix, no PR yet (lead ruling a50c5b)',
            ),
        ),
    ],
)
async def test_server_batch_completion_ordering(lifecycle_sim, closed):
    sim = lifecycle_sim
    sim.seed(sessions={} if closed else {'synthetic-open-producer': True})
    start = sim.row()['started_at'].timestamp()
    sim.ref.update(
        {
            'status': 'in_progress',
            'server_batch_only': True,
            'server_batch_audio_start': start,
            'server_batch_audio_end': start + 2,
            'has_content': True,
            'is_locked': False,
            'uses_custom_stt': False,
            'external_data': {},
        }
    )
    if closed:
        assert sim.seal() is None
    else:
        assert sim.seal() == 'producer_pending'
    finalization = await sim.finalize_before_results()
    assert sim.job(), 'finalizer did not persist the batch obligation'
    assert not sim.row().get('transcript_segments'), 'fixture unexpectedly ran the batch worker'
    if closed:
        prematurely_completed = finalization['status'] == 'completed'
        completed_job_id = sim.row()['finalization_job_id']
        outbox_ref = sim.stack.firestore.collection(outbox.COLLECTION).document(outbox.key(sim.uid, sim.cid))
        before_outbox = outbox_ref.get().to_dict() or {}
        await sim.tick()
        assert sim.row().get('transcript_segments'), 'fixture batch results did not commit'
        row = sim.row()
        latest = finalization_jobs.get_finalization_job(
            row['finalization_job_id'], firestore_client=sim.stack.firestore
        )
        assert latest, 'fixture lost its durable finalization job'
        rearmed = latest['status'] in {'queued', 'leased'} and (
            row['finalization_job_id'] != completed_job_id
            or latest['dispatch_generation'] > finalization['dispatch_generation']
        )
        rearmed = rearmed or durable_titling_rearm(before_outbox, outbox_ref.get().to_dict())
        if prematurely_completed:
            invariant(rearmed, 'late batch results committed without a durable titling rearm')
        else:
            invariant(
                latest['status'] == 'queued' or rearmed,
                'batch results committed while finalization remained stranded',
            )
    else:
        row = sim.row()
        invariant(
            row['status'] != 'completed' or (row.get('record_audio_closed') and not row.get('record_upload_sessions')),
            'conversation completed while audio was open and its upload session remained pending',
        )


@pytest.mark.asyncio
@pytest.mark.parametrize('ending', ['exhaustion', 'eviction', 'tombstone', 'missing', 'late_tombstone', 'marker_race'])
async def test_projection_close_debt_survives_socket_and_respects_privacy(lifecycle_sim, monkeypatch, ending):
    from database import record_projection_rebuild as jobs
    from utils import pusher_audio_projection as projection
    from utils import record_projection_rebuild as consumer
    from utils.batch_pipeline.record_seal_budget import SweepBudget

    sim = lifecycle_sim
    sim.seed(sessions={'live': True})
    # Earlier summary scenarios install an empty playback leaf globally. This
    # scenario must exercise the real grouping implementation captured at import.
    monkeypatch.setattr(processing.conversations_db, 'create_audio_files_from_chunks', create_audio_files_from_chunks)
    monkeypatch.setenv('PUSHER_PROJECTION_DEBT_DURABLE_ENABLED', '1')
    monkeypatch.setenv('PUSHER_AUDIO_FILE_INCREMENTAL_ENABLED', '1')
    before = sim.row()

    def retained_objects():
        bucket = sim.storage.bucket(os.environ['BUCKET_PRIVATE_CLOUD_SYNC'])
        return {
            blob.name: (blob.generation, blob.metadata, blob.download_as_bytes())
            for blob in bucket.list_blobs(prefix=f'chunks/{sim.uid}/{sim.cid}/')
        }

    retained_before = retained_objects()
    assert retained_before
    from utils.batch_pipeline import record_projection_rebuild as full_projection

    discovery = full_projection.discover(sim.uid, sim.cid, strict_raw=True)
    assert discovery is not None and discovery[2], discovery
    failures = []
    original_rebuild = consumer.rebuild

    def checked_rebuild(*args):
        try:
            return original_rebuild(*args)
        except Exception as error:
            failures.append(repr(error))
            raise

    monkeypatch.setattr(consumer, 'rebuild', checked_rebuild)
    cache = projection.PusherAudioProjection(sim.uid)
    cache.has_uploaded_paths = True
    cache.close_debt.add(sim.cid)
    marker = sim.stack.firestore.collection(jobs.COLLECTION).document(jobs.marker_id(sim.uid, sim.cid))
    try:
        if ending == 'exhaustion':

            def fail(*_):
                raise OSError('synthetic projection failure')

            monkeypatch.setattr(cache, 'finish', fail)
            assert await cache.finish_pending(sim.cid, set(), set()) is False
            assert await cache.finish_pending(sim.cid, set(), set()) is False
            assert await cache.finish_pending(sim.cid, set(), set()) is True
        await cache.persist_pending()
        assert marker.get().exists
        tombstone = sim.ref.parent.parent.collection('deleted_conversations').document(sim.cid)
        if ending == 'tombstone':
            tombstone.set({'deleted': True})
        elif ending == 'missing':
            sim.ref.delete()
        elif ending == 'late_tombstone':
            apply = jobs.apply_projection

            def race(*args, **kwargs):
                tombstone.set({'deleted': True})
                return apply(*args, **kwargs)

            monkeypatch.setattr(jobs, 'apply_projection', race)
        elif ending == 'marker_race':
            rebuild = consumer.rebuild

            def race(*args):
                result = rebuild(*args)
                jobs.mark_due(*args, firestore_client=sim.stack.firestore)
                return result

            monkeypatch.setattr(consumer, 'rebuild', race)
        report = consumer.run(budget=SweepBudget(30), firestore_client=sim.stack.firestore)
        if ending in {'exhaustion', 'eviction', 'marker_race'}:
            # Existing live producer fences prevent retirement of debt published
            # while a retained worker can still upload. This is a synthetic
            # fixture transition, never a consumer token/seal mutation.
            assert marker.get().exists
            assert sim.row()['record_upload_sessions'] == {'live': True}
            sim.ref.update({'record_upload_sessions': {}})
            before['record_upload_sessions'] = {}
            report = consumer.run(budget=SweepBudget(30), firestore_client=sim.stack.firestore)
        assert not failures
        assert marker.get().exists is (ending == 'marker_race'), report
        if ending == 'missing':
            assert not sim.ref.get().exists
        else:
            after = sim.row()
            if ending in {'tombstone', 'late_tombstone'}:
                assert after == before
            else:
                assert after.get('audio_files')
                assert {k: v for k, v in after.items() if k != 'audio_files'} == before
        # The retained PCM and its metadata are untouched by the repair pass.
        assert live.list_audio_chunks(sim.uid, sim.cid, require_archive=True)
        assert retained_objects() == retained_before
    finally:
        marker.delete()


@pytest.mark.parametrize(
    'ending', ['aged_fenced', 'aged_clear', 'pressure_fenced', 'late_fence', 'marker_race', 'tail']
)
def test_empty_projection_retirement_rechecks_producer_fence(lifecycle_sim, monkeypatch, ending):
    from database import record_projection_rebuild as jobs
    from database.audio_timeline import span_blob_metadata
    from utils import record_projection_rebuild as consumer
    from utils.batch_pipeline.record_seal_budget import SweepBudget

    sim = lifecycle_sim
    sim.seed()
    cid = sim.cid + '-empty'
    ref = sim.ref.parent.document(cid)
    row = {**sim.row(), 'id': cid, 'audio_files': [], 'record_upload_sessions': {}}
    if ending in {'aged_fenced', 'pressure_fenced', 'tail'}:
        row['record_upload_sessions'] = {'live': True}
    ref.set(row)
    # CI shares this collection with earlier stack scenarios. Include a clear
    # peer locally too, so the test cannot assume aggregate counts belong only
    # to its fenced owner. Only clear candidates may be pressure-evicted.
    peer_cid = cid + '-peer'
    peer_ref = sim.ref.parent.document(peer_cid)
    peer_row = {**row, 'id': peer_cid, 'record_upload_sessions': {}}
    peer_ref.set(peer_row)
    peer_marker = sim.stack.firestore.collection(jobs.COLLECTION).document(jobs.marker_id(sim.uid, peer_cid))
    jobs.mark_due(sim.uid, peer_cid, firestore_client=sim.stack.firestore)
    marker = sim.stack.firestore.collection(jobs.COLLECTION).document(jobs.marker_id(sim.uid, cid))
    jobs.mark_due(sim.uid, cid, firestore_client=sim.stack.firestore)
    observed = marker.get()
    monkeypatch.setenv('PUSHER_PROJECTION_DEBT_DURABLE_ENABLED', '1')
    monkeypatch.setattr(processing.conversations_db, 'create_audio_files_from_chunks', create_audio_files_from_chunks)
    # Firestore create_time is immutable. Exercise age eligibility immediately;
    # the unit contract separately supplies an actual eight-day-old snapshot.
    monkeypatch.setattr(consumer, 'NO_OBJECTS_MAX_AGE_SECONDS', 0)
    if ending == 'pressure_fenced':
        marker_count = len(list(sim.stack.firestore.collection(jobs.COLLECTION).stream()))
        assert 2 <= marker_count <= consumer.MAX_PER_PASS
        monkeypatch.setattr(consumer, 'MAX_COLLECTION_MARKERS', marker_count - 1)
    rebuild = consumer.rebuild
    retire = jobs.retire_empty
    decisions = []

    def checked_retirement(uid, conversation_id, **kwargs):
        result = retire(uid, conversation_id, **kwargs)
        if (uid, conversation_id) == (sim.uid, cid):
            decisions.append(result)
        return result

    monkeypatch.setattr(jobs, 'retire_empty', checked_retirement)

    def after_discovery(uid, conversation_id):
        result = rebuild(uid, conversation_id)
        if (uid, conversation_id) != (sim.uid, cid):
            return result
        assert result == 'no_objects'
        if ending == 'late_fence':
            assert record_audio.set_record_upload_pending(
                uid, conversation_id, 'late', True, firestore_client=sim.stack.firestore
            )
        elif ending == 'marker_race':
            jobs.mark_due(uid, conversation_id, firestore_client=sim.stack.firestore)
        return result

    try:
        # This new conversation genuinely has no published audio prefix yet.
        with monkeypatch.context() as first:
            first.setattr(consumer, 'rebuild', after_discovery)
            report = consumer.run(budget=SweepBudget(30), firestore_client=sim.stack.firestore)
        assert not peer_marker.get().exists
        assert peer_ref.get().to_dict() == peer_row
        if ending == 'aged_clear':
            assert not marker.get().exists and ref.get().to_dict() == row
            assert decisions == ['retired_no_objects']
            return
        assert marker.get().exists
        assert marker.get().update_time != observed.update_time
        if ending == 'marker_race':
            assert decisions == ['changed']
        else:
            assert decisions == ['producer_fenced']
            assert ref.get().to_dict()['record_upload_sessions']
        if ending == 'pressure_fenced':
            assert report['gauges']['pressure_blocked'] is False  # The clear peer was evicted.
            assert report['gauges']['pressure_fenced_count'] >= 1
        if ending == 'tail':
            # Only the synthetic producer fixture publishes this late object.
            # The consumer must still own a marker after its earlier empty pass.
            start = row['started_at'].timestamp()
            blob = sim.storage.bucket(os.environ['BUCKET_PRIVATE_CLOUD_SYNC']).blob(
                f'chunks/{sim.uid}/{cid}/{start:.3f}.batch.bin'
            )
            blob.metadata = span_blob_metadata({'start': start, 'samples': 16000, 'sample_rate': 16000})
            blob.upload_from_string(b'\x01\x00' * 16000, if_generation_match=0)
            retained = (blob.generation, blob.metadata, blob.download_as_bytes())
            report = consumer.run(budget=SweepBudget(30), firestore_client=sim.stack.firestore)
            assert ref.get().to_dict()['audio_files'], report
            assert marker.get().exists  # The publishing producer still owns its token.
            assert record_audio.set_record_upload_pending(
                sim.uid, cid, 'live', False, firestore_client=sim.stack.firestore
            )
            consumer.run(budget=SweepBudget(30), firestore_client=sim.stack.firestore)
            assert not marker.get().exists
            assert (blob.generation, blob.metadata, blob.download_as_bytes()) == retained
    finally:
        marker.delete()
        ref.delete()
        peer_marker.delete()
        peer_ref.delete()
