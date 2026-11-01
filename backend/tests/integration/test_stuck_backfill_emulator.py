"""Real Firestore close/restore, admission, lease races and global rate fences."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
import uuid

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database import stuck_backfill as backfill, conversation_finalization_jobs as jobs, conversations
from utils.conversations import lifecycle
from utils.conversations.processing_trigger import ProcessingTrigger, trigger_for_finalization_job

pytestmark = pytest.mark.integration


@pytest.fixture
def store(monkeypatch):
    if not os.getenv('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('loopback Firestore emulator required')
    client = firestore.Client(project='demo-p61', credentials=AnonymousCredentials())
    uid = 'p61-' + uuid.uuid4().hex
    user = client.collection('users').document(uid)
    user.set({'data_protection_level': 'enhanced'})
    monkeypatch.setattr(jobs, 'invalidate_people_stats_cache', lambda *_: None)
    yield client, uid, user
    client.close()


def seed(store, cid='noise', **extra):
    client, uid, user = store
    now = datetime.now(timezone.utc)
    ref = user.collection('conversations').document(cid)
    row = {
        'id': cid,
        'status': 'in_progress',
        'source': 'omi',
        'finished_at': now - timedelta(days=2),
        'transcript_segments': [],
        'audio_files': [],
        **extra,
    }
    ref.set(conversations.encode_conversation_for_write(uid, row))
    return ref, ref.get(), now - timedelta(hours=1)


def close(store, ref, snap, cutoff, **kwargs):
    client, uid, _ = store
    return backfill.close_noise(
        uid,
        ref.id,
        expected_revision=backfill.revision(snap),
        cutoff=cutoff,
        expected_session_revision=kwargs.get('session_revision'),
        run_id='run',
        firestore_client=client,
    )


def test_metadata_only_close_restore_retains_exact_encoded_content(store):
    ref, snap, cutoff = seed(store)
    before = snap.to_dict()
    stamp = close(store, ref, snap, cutoff)
    after = ref.get().to_dict()
    assert after['status'] == 'completed' and after['discarded'] is True
    assert after['terminal_no_derived_effects'] is True
    for key in before:
        if key not in {'status', 'discarded', 'terminal_no_derived_effects'}:
            assert after[key] == before[key]
    assert backfill.revision(ref.get()) == stamp
    client, uid, _ = store
    backfill.restore_noise(uid, ref.id, expected_closed_revision=stamp, run_id='run', firestore_client=client)
    assert ref.get().to_dict() == before


@pytest.mark.parametrize(
    'change',
    [
        {'is_locked': True},
        {'status': 'processing'},
        {'transcript_segments': [{'text': 'new speech'}]},
        {'finalization_job_id': 'other'},
    ],
)
def test_changed_metadata_or_content_refuses_close(store, change):
    ref, snap, cutoff = seed(store)
    ref.update(change)
    before = ref.get().to_dict()
    with pytest.raises(backfill.BackfillConflict, match='revision_changed'):
        close(store, ref, snap, cutoff)
    assert ref.get().to_dict() == before


def test_restore_refuses_any_intervening_write_and_wrong_run(store):
    ref, snap, cutoff = seed(store)
    stamp = close(store, ref, snap, cutoff)
    client, uid, _ = store
    with pytest.raises(backfill.BackfillConflict, match='not_matching_close'):
        backfill.restore_noise(uid, ref.id, expected_closed_revision=stamp, run_id='wrong', firestore_client=client)
    ref.update({'is_locked': True})
    with pytest.raises(backfill.BackfillConflict, match='revision_changed'):
        backfill.restore_noise(uid, ref.id, expected_closed_revision=stamp, run_id='run', firestore_client=client)


def test_session_lease_change_without_conversation_change_refuses_close(store):
    client, uid, user = store
    ref, snap, cutoff = seed(store, external_data={'recording_session_id': 'session'})
    session = user.collection('recording_sessions').document('session')
    session.set(
        {
            'uid': uid,
            'recording_session_id': 'session',
            'conversation_id': ref.id,
            'lifecycle_phase': 'in_progress',
            'lease_expires_at': datetime.now(timezone.utc) + timedelta(minutes=1),
        }
    )
    with pytest.raises(backfill.BackfillConflict, match='session_changed'):
        close(store, ref, snap, cutoff)
    with pytest.raises(backfill.BackfillConflict, match='active_session'):
        close(store, ref, snap, cutoff, session_revision=backfill.revision(session.get()))


def admit(store, ref, snap, cutoff):
    client, uid, _ = store
    return jobs.create_or_get_finalization_intent(
        uid,
        ref.id,
        requires_byok=False,
        finalization_admission=lambda row: lifecycle._finalization_admission(row, ref.id),
        trigger=ProcessingTrigger.SILENT_BACKFILL,
        expected_update_time=snap.update_time,
        backfill_run_id='run',
        recovery_cutoff=cutoff,
        firestore_client=client,
    )


def test_silent_admission_is_immutable_and_serializes_one_owner(store):
    first, snap, cutoff = seed(store, 'first', transcript_segments=[{'text': 'synthetic speech'}])
    second, snap2, _ = seed(store, 'second', transcript_segments=[{'text': 'other speech'}])
    client, uid, user = store
    result = admit(store, first, snap, cutoff)
    assert result['created']
    job = jobs.get_finalization_job(result['job_id'], firestore_client=client)
    assert trigger_for_finalization_job(job) is ProcessingTrigger.SILENT_BACKFILL
    assert job['delivery_policy'] == backfill.POLICY
    assert user.collection('backfill_state').document('inflight').get().to_dict()['job_id'] == result['job_id']
    refused = admit(store, second, snap2, cutoff)
    assert not refused['created'] and refused['status'] == 'refused_owner_inflight'
    changed = admit(store, first, snap, cutoff)
    assert not changed['created'] and changed['status'] == 'refused_revision_changed'


def test_concurrent_close_has_one_winner(store):
    ref, snap, cutoff = seed(store)

    def attempt(_):
        try:
            close(store, ref, snap, cutoff)
            return 'closed'
        except backfill.BackfillConflict:
            return 'refused'

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, range(2))) == ['closed', 'refused']


def test_global_reservation_paces_and_reads_kill_switch(store):
    client, _, _ = store
    run = uuid.uuid4().hex
    ref = client.collection('stuck_backfill_runs').document(run)
    ref.set(
        {
            'enabled': True,
            'approved_plan_sha256': 'digest',
            'admissions_per_minute': 10,
            'max_admissions': 10,
            'max_modeled_usd': 1,
            'verified_delivery_policy': backfill.POLICY,
            'verified_release_sha': 'synthetic-sha',
            'silent_canary_evidence_ref': 'synthetic-canary',
            'queue_consumers_evidence_ref': 'synthetic-consumers',
        }
    )
    assert backfill.reserve_admission(run, 'digest', 0.0033, firestore_client=client) == 0
    assert backfill.reserve_admission(run, 'digest', 0.0033, firestore_client=client) > 0
    assert ref.get().to_dict()['admitted'] == 1
    ref.update({'enabled': False})
    with pytest.raises(backfill.BackfillConflict, match='run_disabled'):
        backfill.reserve_admission(run, 'digest', 0.0033, firestore_client=client)


@pytest.mark.parametrize(
    'protected',
    [
        {'is_locked': True},
        {'discarded': True},
        {'deferred': True},
        {'processing_state': 'local_pending'},
        {'finalization_job_id': 'bound-job'},
        {'user_title': 'Synthetic manual title'},
    ],
)
def test_noise_close_refuses_protected_current_snapshot(store, protected):
    ref, snap, cutoff = seed(store, **protected)
    with pytest.raises(backfill.BackfillConflict, match='refused_'):
        close(store, ref, snap, cutoff)
    assert ref.get().to_dict() == snap.to_dict()


def test_close_retains_nonempty_encoded_transcript_and_audio_refs(store):
    ref, snap, cutoff = seed(
        store,
        transcript_segments=[{'text': 'short synthetic utterance', 'start': 0, 'end': 2}],
        audio_files=[{'id': 'synthetic-audio', 'url': 'gs://demo-p61/synthetic'}],
    )
    before = snap.to_dict()
    close(store, ref, snap, cutoff)
    after = ref.get().to_dict()
    assert after['transcript_segments'] == before['transcript_segments']
    assert after['audio_files'] == before['audio_files']


def test_restore_refuses_new_job_binding(store):
    ref, snap, cutoff = seed(store)
    stamp = close(store, ref, snap, cutoff)
    client, uid, _ = store
    ref.update({'finalization_job_id': 'new-synthetic-job'})
    with pytest.raises(backfill.BackfillConflict, match='revision_changed'):
        backfill.restore_noise(uid, ref.id, expected_closed_revision=stamp, run_id='run', firestore_client=client)


def test_concurrent_historical_admission_allows_only_one_row_per_owner(store):
    first, one, cutoff = seed(store, 'one', transcript_segments=[{'text': 'synthetic speech'}])
    second, two, _ = seed(store, 'two', transcript_segments=[{'text': 'other speech'}])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda pair: admit(store, pair[0], pair[1], cutoff), [(first, one), (second, two)]))
    assert sum(r['created'] for r in results) == 1
    assert any(r['status'] == 'refused_owner_inflight' for r in results)


def test_silent_byok_owner_is_not_admitted_with_platform_credentials(store):
    client, _, user = store
    user.update({'byok': {'active': True}})
    ref, snap, cutoff = seed(store, transcript_segments=[{'text': 'synthetic speech'}])
    result = admit(store, ref, snap, cutoff)
    assert not result['created'] and result['status'] == 'refused_byok'
    assert ref.get().to_dict()['status'] == 'in_progress'


def test_silent_storage_keeps_current_encoded_transcript_and_audio(store, monkeypatch):
    import inspect

    ref, snap, _ = seed(
        store,
        transcript_segments=[{'text': 'synthetic retained speech', 'start': 0, 'end': 30}],
        audio_files=[{'id': 'synthetic-audio', 'url': 'gs://demo-p61/synthetic'}],
    )
    before = snap.to_dict()
    client, uid, _ = store
    monkeypatch.setattr(conversations, 'db', client)
    monkeypatch.setattr(conversations, 'invalidate_people_stats_cache', lambda *_: None)
    monkeypatch.setattr(conversations, '_sync_conversation_search_index', lambda *_: None)
    monkeypatch.setattr(conversations.summary_delivery, 'merge_result', lambda *_: None)
    monkeypatch.setattr(conversations.processing_backlog, 'stage_transition', lambda *_args, **_kwargs: False)
    persist = inspect.unwrap(conversations.persist_processing_result_with_lifecycle)
    assert persist(
        uid,
        {
            'id': ref.id,
            'status': 'completed',
            'discarded': False,
            'relevance_decision': {'trigger': 'silent_backfill', 'verdict': 'keep'},
            'structured': {'title': 'Synthetic summary', 'overview': 'Synthetic persisted notes'},
            'transcript_segments': [],
            'audio_files': [],
        },
    )
    after = ref.get().to_dict()
    assert after['transcript_segments'] == before['transcript_segments']
    assert after['audio_files'] == before['audio_files']
    assert after['structured']['overview'] == 'Synthetic persisted notes'


@pytest.mark.parametrize(
    'patch,reason',
    [
        ({'max_admissions': 0}, 'admission_budget'),
        ({'max_modeled_usd': 0}, 'modeled_budget'),
        ({'admissions_per_minute': 0}, 'unsafe_rate'),
        ({'approved_plan_sha256': 'changed'}, 'plan_changed'),
    ],
)
def test_run_reservation_budget_and_binding_refusals(store, patch, reason):
    client, _, _ = store
    run = uuid.uuid4().hex
    ref = client.collection('stuck_backfill_runs').document(run)
    ref.set(
        {
            'enabled': True,
            'approved_plan_sha256': 'digest',
            'admissions_per_minute': 10,
            'max_admissions': 10,
            'max_modeled_usd': 1,
            'verified_delivery_policy': backfill.POLICY,
            'verified_release_sha': 'synthetic',
            'silent_canary_evidence_ref': 'synthetic',
            'queue_consumers_evidence_ref': 'synthetic',
            **patch,
        }
    )
    before = ref.get().to_dict()
    with pytest.raises(backfill.BackfillConflict, match=reason):
        backfill.reserve_admission(run, 'digest', 0.0033, firestore_client=client)
    assert ref.get().to_dict() == before


def test_noise_close_and_restore_recheck_privacy_and_orphan_jobs(store):
    client, uid, user = store
    ref, snap, cutoff = seed(store)
    user.update({'data_protection_level': 'e2ee'})
    with pytest.raises(backfill.BackfillConflict, match='privacy'):
        close(store, ref, snap, cutoff)
    user.update({'data_protection_level': 'enhanced'})
    stamp = close(store, ref, snap, cutoff)
    job_id = jobs._job_id(uid, ref.id, 1)
    client.collection(jobs.FINALIZATION_JOBS_COLLECTION).document(job_id).set({'status': 'queued'})
    with pytest.raises(backfill.BackfillConflict, match='job_exists'):
        backfill.restore_noise(uid, ref.id, expected_closed_revision=stamp, run_id='run', firestore_client=client)


@pytest.mark.parametrize('sid', [42, 'bad/session'])
def test_silent_admission_refuses_malformed_session_without_writing(store, sid):
    ref, snap, cutoff = seed(
        store, transcript_segments=[{'text': 'synthetic'}], external_data={'recording_session_id': sid}
    )
    result = admit(store, ref, snap, cutoff)
    assert result['status'] == 'refused_invalid_session' and not result['created']
    assert ref.get().to_dict() == snap.to_dict()


def test_silent_worker_http_replay_uses_real_claim_fanout_and_completion(store, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from unittest.mock import Mock, AsyncMock
    from routers import conversation_finalization as router
    from utils.conversations import finalizer, demand_processing
    from utils.cloud_tasks import verify_listen_finalization_cloud_tasks_oidc
    from models.conversation_enums import ConversationStatus

    client, uid, _ = store
    ref, snap, cutoff = seed(store, transcript_segments=[{'text': 'synthetic substantive speech'}])
    intent = admit(store, ref, snap, cutoff)
    # A previous provider attempt persisted notes then died before its fanout ACK.
    ref.update(
        {
            'status': 'completed',
            'terminal_no_derived_effects': True,
            'structured': {'title': 'Synthetic retained notes', 'overview': 'Synthetic summary'},
        }
    )
    monkeypatch.setattr(jobs, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(router, 'try_acquire_job_run_lock', lambda *_: 'synthetic-lock')
    monkeypatch.setattr(router, 'release_job_run_lock', lambda *_: None)
    monkeypatch.setattr(router, 'should_skip_background_account_mutation', lambda *_: False)
    monkeypatch.setattr(demand_processing, 'admit', lambda *_args, **_kwargs: True)

    async def inline(_executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(router, 'run_blocking', inline)
    monkeypatch.setattr(finalizer, 'run_blocking', inline)

    async def load(_uid, _cid, *_):
        assert (_uid, _cid) == (uid, ref.id)
        data = ref.get().to_dict()
        return (
            None,
            data,
            SimpleNamespace(
                id=ref.id,
                status=ConversationStatus.completed,
                language='en',
                discarded=False,
                geolocation=None,
                structured=data['structured'],
            ),
        )

    monkeypatch.setattr(finalizer, '_load_admitted_conversation', load)
    for name in [
        'process_conversation',
        'extract_memories',
        'link_duplicate_captures',
        'record_finalized_meeting_receipt',
        'schedule_person_voice_learning_retry',
    ]:
        monkeypatch.setattr(finalizer, name, Mock(side_effect=AssertionError('silent replay escaped')))
    for name in [
        'smart_merge_step',
        'trigger_external_integrations',
        '_episode_after_finalization',
        'resolve_frame_request_authority',
    ]:
        monkeypatch.setattr(finalizer, name, AsyncMock(side_effect=AssertionError('silent replay escaped')))
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[verify_listen_finalization_cloud_tasks_oidc] = lambda: 0
    with TestClient(app) as http:
        payload = {'job_id': intent['job_id'], 'dispatch_generation': intent['dispatch_generation']}
        response = http.post('/v1/conversation-finalization-jobs/run', json=payload)
        assert response.status_code == 200 and response.json()['status'] == 'done'
        replay = http.post('/v1/conversation-finalization-jobs/run', json=payload)
        assert replay.status_code == 200 and replay.json()['status'] == 'acked'
    job = jobs.get_finalization_job(intent['job_id'], firestore_client=client)
    assert job['status'] == 'completed' and job['fanout_status'] == 'completed'
    assert job['terminal_outcome'] == 'success'
    assert ref.get().to_dict()['structured']['overview'] == 'Synthetic summary'
