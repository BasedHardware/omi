"""WP-B: real lifecycle transitions and their independently derived shadow."""

from datetime import datetime, timedelta, timezone
import math
from types import SimpleNamespace

import pytest

from testing.lifecycle_sim.test_scenarios import lifecycle_sim, stack  # noqa: F401 -- shared pytest fixtures
from testing.lifecycle_sim import harness
from database import record_audio
from database.record_partial import finish_partial
from tests.support.lifecycle_state_table import ORDERING_RULES, durable_titling_rearm, ordering_holds
from utils.batch_pipeline import live, record_producer_proof, record_seal_sweeper, record_seal_repair
from utils.conversations.phase import ConversationPhase, derive_conversation_phase
from utils.enrichment import outbox
from utils.other.storage import upload_audio_chunks_batch


@pytest.mark.asyncio
@pytest.mark.parametrize('elapsed', [61, 3600], ids=['admission-due', 'long-quiet-window'])
async def test_fault_free_capture_exits_each_entered_phase_within_ticks(lifecycle_sim, elapsed):
    sim = lifecycle_sim
    assert sim.fault is None
    sim.seed()
    assert derive_conversation_phase(sim.row()) == ConversationPhase.CAPTURING
    assert sim.seal() is None
    assert derive_conversation_phase(sim.row()) == ConversationPhase.SEALED
    assert sim.register()
    assert sim.job()['state'] == 'record_pending'
    assert derive_conversation_phase(sim.row()) == ConversationPhase.SEALED
    sim.age(elapsed)
    for _ in range(3):
        await sim.tick()
        if sim.row().get('record_projection_revision'):
            break
        sim.age(61)
    projected = sim.row()
    assert projected.get('record_projection_revision'), 'bounded admission/worker ticks did not persist projection'
    assert projected.get('transcript_segments'), 'projection omitted the real worker transcript'
    assert derive_conversation_phase(projected) in {
        ConversationPhase.TRANSCRIBED,
        ConversationPhase.COMPLETE,
        ConversationPhase.SETTLED,
    }
    await sim.complete()
    assert sim.row()['structured']['overview'] == 'Provider leaf completed locally.'
    assert derive_conversation_phase(sim.row()) == ConversationPhase.SETTLED


@pytest.mark.asyncio
async def test_completed_without_results_rearms_titling_when_result_commits(lifecycle_sim, monkeypatch):
    sim = lifecycle_sim
    sim.seed()
    start = sim.row()['started_at'].timestamp()
    # A real retained three-minute capture makes later titling meaningful;
    # the two-second happy-path fixture may legitimately waive summary debt.
    assert upload_audio_chunks_batch(
        [
            {
                'data': b'\x01\x00' * (178 * 16000),
                'timestamp': start + 2,
                'span': {'start': start + 2, 'samples': 178 * 16000, 'sample_rate': 16000},
            }
        ],
        sim.uid,
        sim.cid,
        'standard',
        sample_rate=16000,
    )
    finished = datetime.fromtimestamp(start + 180, timezone.utc)
    sim.ref.update(
        {
            'status': 'in_progress',
            'server_batch_only': True,
            'server_batch_audio_start': start,
            'server_batch_audio_end': start + 180,
            'finished_at': finished,
            'recorded_end': finished,
            'has_content': True,
            'is_locked': False,
            'uses_custom_stt': False,
            'external_data': {},
        }
    )
    assert sim.seal() is None
    finalization = await sim.finalize_before_results()
    assert finalization['status'] == 'completed', 'fixture did not reach the early-completion boundary'
    assert not sim.row().get('transcript_segments')
    target = sim.stack.firestore.collection(outbox.COLLECTION).document(outbox.key(sim.uid, sim.cid))
    before = target.get().to_dict() or {}
    monkeypatch.setattr(outbox, '_enqueue', lambda *args, **kwargs: None)
    monkeypatch.setenv('SYNC_TASKS_QUEUE', 'lifecycle-property-local')
    monkeypatch.setenv('SYNC_TASKS_HANDLER_URL', 'https://lifecycle.invalid/run')
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'synthetic@example.invalid')
    sim.age(61)
    await sim.tick()
    assert sim.row().get('record_projection_revision'), 'late result projection did not commit'
    assert sim.row().get('transcript_segments'), 'late result did not persist transcript'
    pending = target.get().to_dict() or {}
    assert pending and not pending.get('dormant'), 'late result did not leave a durable titling obligation'
    assert pending['version'] > before.get('version', 0)
    due_at = pending.get('due_at')
    assert pending.get('task_token') and type(due_at) in (int, float) and math.isfinite(due_at)
    assert pending.get('conversation_id') == sim.cid
    result = sim.store.run(lambda tx: tx.get('results', sim.segment))
    assert result.get('result'), 'the rearm proof must follow a durable worker result'
    rearmed = durable_titling_rearm(before, pending)
    assert ordering_holds(
        ORDERING_RULES[0],
        sim.row(),
        batch_result_count=int(bool(result.get('result'))),
        rearm_on_result_commit=rearmed,
        completed_before_results=finalization['status'] == 'completed',
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('elapsed', [3600, 30 * 86400], ids=['hour-old', 'month-old'])
async def test_no_audio_live_producer_survives_age_until_exact_finish(lifecycle_sim, monkeypatch, elapsed):
    sim = lifecycle_sim
    sim.stack.seed_user(sim.uid)
    entered = datetime.now(timezone.utc)
    sim.ref.set(
        {
            'id': sim.cid,
            'created_at': entered,
            'started_at': entered,
            'finished_at': entered,
            'status': 'in_progress',
            'record_lane_owner': 'batch_live_v1',
            'private_cloud_sync_enabled': True,
            'data_protection_level': 'standard',
            'language': 'en',
            'source': 'omi',
            'record_audio_closed': False,
            'record_upload_sessions': {},
            'record_upload_revision': 0,
            'transcript_segments': [],
            'photos': [],
            'discarded': False,
            'deleted': False,
        }
    )
    session = 'synthetic-empty-session'
    producer = {'pod': 'synthetic-live-pusher', 'process_started_at': entered.timestamp() - 3600}
    assert record_audio.set_record_upload_pending(
        sim.uid, sim.cid, session, True, producer=producer, firestore_client=sim.stack.firestore
    )
    tokens = dict(sim.row()['record_upload_sessions'])
    assert live.list_audio_chunks(sim.uid, sim.cid, require_archive=True) == []
    assert derive_conversation_phase(sim.row()) == ConversationPhase.CAPTURING
    # 7a6181 / lead2 9d457c: no producer TTL. Age is never proof of death.
    future = (entered + timedelta(seconds=elapsed)).timestamp()
    sim.proof_time = future
    for module in (harness, record_seal_sweeper, record_producer_proof):
        monkeypatch.setattr(module, 'time', SimpleNamespace(time=lambda: future))
    for _ in range(3):
        assert not record_producer_proof.producer_tokens_dead(tokens, sim.proof(live_producer=True))
        sim.sweep(live_producer=True)
        await sim.tick()
    assert sim.row()['record_upload_sessions'] == tokens
    assert not sim.row().get('record_audio_closed')
    assert record_audio.set_record_upload_pending(
        sim.uid, sim.cid, session + '-other', False, firestore_client=sim.stack.firestore
    )
    assert sim.row()['record_upload_sessions'] == tokens, 'another session cleared this live producer'
    assert record_audio.set_record_upload_pending(
        sim.uid, sim.cid, session, False, firestore_client=sim.stack.firestore
    )
    assert not sim.row()['record_upload_sessions']
    assert sim.seal() is None
    assert sim.row()['record_audio_closed']


@pytest.mark.asyncio
async def test_full_tail_proven_dead_repair_clears_only_after_proof(lifecycle_sim):
    sim = lifecycle_sim
    sim.seed()
    producer = {'pod': 'synthetic-repair-pusher', 'process_started_at': datetime.now(timezone.utc).timestamp() - 3600}
    assert record_audio.set_record_upload_pending(
        sim.uid, sim.cid, 'synthetic-repair-session', True, producer=producer, firestore_client=sim.stack.firestore
    )
    assert sim.register()
    sim.age(61)
    tokens = dict(sim.row()['record_upload_sessions'])
    assert not record_producer_proof.producer_tokens_dead(tokens, sim.proof(live_producer=True))
    sim.sweep(live_producer=True)
    assert sim.row()['record_upload_sessions'] == tokens
    assert not sim.row().get('record_audio_closed')
    assert record_producer_proof.producer_tokens_dead(tokens, sim.proof())
    sim.sweep()
    assert not sim.row().get('record_upload_sessions')
    assert sim.row().get('record_audio_closed')
    for _ in range(3):
        await sim.tick()
        if sim.row().get('record_projection_revision'):
            break
        sim.age(61)
    assert sim.row().get('record_projection_revision')


@pytest.mark.asyncio
@pytest.mark.parametrize('exit_name', ['seal', 'partial_finish', 'reactivated'])
async def test_leased_lapsed_token_has_named_exit(lifecycle_sim, monkeypatch, exit_name):
    """Real Firestore transactions: computed expiry never fabricates tail proof."""

    sim = lifecycle_sim
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')

    class CaptureClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) - timedelta(hours=3)

    with monkeypatch.context() as capture_clock:
        capture_clock.setattr(harness, 'datetime', CaptureClock)
        sim.seed()
    assert sim.register()
    now = datetime.now(timezone.utc).timestamp()
    token = {
        'pod': 'synthetic-lease-pusher',
        'process_started_at': now - 86400,
        'last_signal_at': now - 7200,
        'lease_expires_at': now - 3600,
        'signal_source': 'frames',
    }
    sim.ref.update({'record_upload_sessions': {'lease': token}})
    assert record_producer_proof.producer_tokens_dead(
        {'lease': token}, sim.proof(live_producer=True), uid=sim.uid, row=sim.row(), job=sim.job()
    )
    if exit_name == 'reactivated':
        revision = sim.row()['record_upload_revision']
        from database import record_custody_append

        assert record_custody_append.begin(sim.uid, sim.cid, 'custody:lifecycle', firestore_client=sim.stack.firestore)
        assert sim.row()['record_upload_revision'] == revision
        sim.sweep(live_producer=True)
        assert 'custody:lifecycle' in sim.row()['record_upload_sessions']
        # A completed durable archive append refreshes only its own custody
        # fence. The original frame token stays lapsed until that socket sends
        # another durable frame batch.
        record_audio.renew_record_token_lease(
            sim.uid, sim.cid, source='custody_append', session='custody:lifecycle', firestore_client=sim.stack.firestore
        )
        assert sim.row()['record_upload_revision'] == revision
        record_custody_append.finish(
            sim.uid, sim.cid, 'custody:lifecycle', accepted=True, firestore_client=sim.stack.firestore
        )
        assert sim.row()['record_upload_revision'] == revision + 1
        record_audio.renew_record_token_lease(
            sim.uid,
            sim.cid,
            source='frames',
            session='lease',
            producer=token,
            firestore_client=sim.stack.firestore,
        )
        assert sim.row()['record_upload_revision'] == revision + 2
        sim.sweep(live_producer=True)
        assert sim.row()['record_upload_sessions']
        assert not sim.row()['record_audio_closed']
    elif exit_name == 'partial_finish':
        # An old finished_at with retained bytes ending earlier must not seal.
        sim.ref.update({'finished_at': sim.row()['finished_at'] + timedelta(seconds=10)})
        plan = record_seal_repair.plan_seals(
            sim.store,
            [sim.job_ref.id],
            sim.storage,
            sim.artifacts,
            producer_proof=sim.proof(live_producer=True),
        )
        assert plan['entries'][0]['disposition'] == 'proof_refused'
        assert plan['entries'][0]['proof_reason'] == 'tail_lagging'
        result = finish_partial(
            sim.store, sim.ref.path, reason='tail_lagging', proof=sim.proof(live_producer=True), now=now
        )
        assert result == 'partial_finished'
        assert not sim.row()['record_upload_sessions']
        assert sim.row()['record_audio_partial']
        assert not sim.row()['record_audio_closed']
        assert sim.job()['partial_coordinator']
    else:
        plan = record_seal_repair.plan_seals(
            sim.store, [sim.job_ref.id], sim.storage, sim.artifacts, producer_proof=sim.proof(live_producer=True)
        )
        assert plan['entries'][0]['disposition'] == 'eligible'
        assert record_seal_repair.apply_seals(sim.store, plan, plan['plan_sha256']) == {'sealed': 1}
        assert not sim.row()['record_upload_sessions']
        assert sim.row()['record_audio_closed']
