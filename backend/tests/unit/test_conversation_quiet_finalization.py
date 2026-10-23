"""Durable disconnect obligations exercise the real lifecycle admission fence."""

import asyncio

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.cloud import firestore
from starlette.websockets import WebSocketState

from database import conversation_finalization_jobs as jobs
from database import conversation_quiet_checks as checks
from routers import conversation_finalization as worker
from services import conversation_finalization as service
from routers.listen.contracts import ListenRequest
from routers.listen.runtime import ListenSessionRuntime
from utils.conversations import demand_processing, lifecycle, quiet_finalization as quiet
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)
ROW = ('users', 'synthetic', 'conversations', 'old')
SESSION = ('users', 'synthetic', 'recording_sessions', 'recording-old')


@pytest.fixture
def store(monkeypatch):
    db = StrictFirestore(
        {
            ROW: {
                'source': 'omi',
                'status': 'in_progress',
                'has_content': True,
                'transcript_segments': [{'text': 'synthetic fixture'}],
                'finished_at': NOW,
                'external_data': {'recording_session_id': 'recording-old'},
            },
            SESSION: {
                'uid': 'synthetic',
                'conversation_id': 'old',
                'recording_session_id': 'recording-old',
                'lifecycle_phase': 'in_progress',
                'lease_expires_at': NOW + timedelta(minutes=5),
            },
        }
    )
    monkeypatch.setattr(checks, '_now', lambda: NOW)
    monkeypatch.setattr(jobs, '_now', lambda: NOW)
    monkeypatch.setattr(quiet, 'is_listen_finalization_dispatch_enabled', lambda: True)
    monkeypatch.setattr(quiet, 'is_listen_finalization_dispatch_configured', lambda: True)
    monkeypatch.setattr(lifecycle, 'is_listen_finalization_dispatch_enabled', lambda: True)
    monkeypatch.setattr(lifecycle, 'is_listen_finalization_dispatch_configured', lambda: True)
    monkeypatch.setattr(quiet, 'should_skip_background_account_mutation', lambda *a, **k: False)
    monkeypatch.setattr(quiet, 'enqueue_listen_finalization_job', MagicMock())

    # Keep the actual lifecycle reducer and admission transaction. Only the
    # SDK/client wrapper and irrelevant projection side effect are omitted.
    def create(uid, conversation_id, **kwargs):
        return firestore.transactional(jobs._create_or_get_finalization_intent_txn)(
            db.transaction(),
            db.document('/'.join(ROW)),
            db.collection(jobs.FINALIZATION_JOBS_COLLECTION),
            uid,
            conversation_id,
            kwargs['requires_byok'],
            kwargs['finalization_admission'],
            checks._now(),
            trigger=kwargs['trigger'],
            recovery_cutoff=kwargs['recovery_cutoff'],
            account_deletion_ref=db.collection('account_deletions').document(uid),
            require_expired_recording_lease=kwargs.get('require_expired_recording_lease', False),
            recording_sessions_collection=db.collection('users').document(uid).collection('recording_sessions'),
        )

    monkeypatch.setattr(jobs, 'create_or_get_finalization_intent', create)
    monkeypatch.setattr(lifecycle, 'enqueue_listen_finalization_job', MagicMock())

    monkeypatch.setattr(demand_processing, 'schedule', lambda *a, **k: False)
    return db


def _advance(monkeypatch, seconds):
    monkeypatch.setattr(checks, '_now', lambda: NOW + timedelta(seconds=seconds))
    monkeypatch.setattr(jobs, '_now', lambda: NOW + timedelta(seconds=seconds))


def _job(store):
    return store.rows[('conversation_finalization_jobs', checks.quiet_check_id('synthetic', 'old'))]


@pytest.mark.parametrize('source', ['omi', 'phone'])
def test_disconnect_before_deadline_arms_one_check_without_processing(store, monkeypatch, source):
    store.rows[ROW]['source'] = source
    _advance(monkeypatch, 67)
    quiet.arm('synthetic', 'old', 120, firestore_client=store)
    quiet.arm('synthetic', 'old', 120, firestore_client=store)
    check = _job(store)
    assert len([p for p in store.rows if p[0] == 'conversation_finalization_jobs']) == 1
    assert check['due_at'] == NOW + timedelta(seconds=120)
    assert check['dispatch_generation'] == 1
    assert store.rows[ROW]['status'] == 'in_progress'
    assert 'finalization_job_id' not in store.rows[ROW]
    assert quiet.enqueue_listen_finalization_job.call_args.kwargs['schedule_at'] == int(check['due_at'].timestamp()) + 1


def test_new_identity_reconnect_does_not_orphan_old_conversation(store, monkeypatch):
    quiet.arm('synthetic', 'old', 120, firestore_client=store)
    # Another client identity owns another row; it cannot fence the old row.
    store.rows[('users', 'synthetic', 'conversations', 'new')] = {
        'status': 'in_progress',
        'external_data': {'recording_session_id': 'new-recording'},
    }
    _advance(monkeypatch, 120)
    assert quiet.run(checks.quiet_check_id('synthetic', 'old'), 1, firestore_client=store) == 'deferred'
    assert store.rows[ROW]['status'] == 'in_progress'  # old lease still live
    _advance(monkeypatch, 301)
    gen = _job(store)['dispatch_generation']
    result = quiet.run(checks.quiet_check_id('synthetic', 'old'), gen, firestore_client=store)
    assert result == 'queued'
    processing_id = store.rows[ROW]['finalization_job_id']
    processing = store.rows[('conversation_finalization_jobs', processing_id)]
    assert processing['processing_trigger'] == 'server_recovery'
    assert store.rows[ROW]['status'] == 'processing'
    assert store.rows[('users', 'synthetic', 'conversations', 'new')]['status'] == 'in_progress'
    # A duplicate delivery and the reserved next wake both cannot mint a second job.
    assert quiet.run(checks.quiet_check_id('synthetic', 'old'), gen, firestore_client=store) == 'stale'
    next_gen = _job(store)['dispatch_generation']
    assert quiet.run(checks.quiet_check_id('synthetic', 'old'), next_gen, firestore_client=store) == 'done'
    assert store.rows[ROW]['finalization_revision'] == 1


@pytest.mark.parametrize('same_session', [True, False])
def test_reconnect_continuing_same_conversation_defers_without_finalize(store, monkeypatch, same_session):
    quiet.arm('synthetic', 'old', 120, firestore_client=store)
    _advance(monkeypatch, 301)
    sid = 'recording-old' if same_session else 'recording-new'
    store.rows[ROW]['external_data']['recording_session_id'] = sid
    store.rows[ROW]['finished_at'] = NOW + timedelta(seconds=290)
    store.rows[('users', 'synthetic', 'recording_sessions', sid)] = {
        'uid': 'synthetic',
        'conversation_id': 'old',
        'recording_session_id': sid,
        'lifecycle_phase': 'in_progress',
        'lease_expires_at': NOW + timedelta(minutes=10),
    }
    assert quiet.run(checks.quiet_check_id('synthetic', 'old'), 1, firestore_client=store) == 'deferred'
    assert store.rows[ROW]['status'] == 'in_progress'
    assert 'finalization_job_id' not in store.rows[ROW]
    assert _job(store)['due_at'] >= NOW + timedelta(seconds=410)


def test_reconnect_between_check_and_admission_is_transactionally_fenced(store, monkeypatch):
    quiet.arm('synthetic', 'old', 120, firestore_client=store)
    _advance(monkeypatch, 301)
    request = quiet.lifecycle.request_finalization

    def reconnect(*args, **kwargs):
        store.rows[SESSION]['lease_expires_at'] = NOW + timedelta(minutes=10)
        return request(*args, **kwargs)

    monkeypatch.setattr(quiet.lifecycle, 'request_finalization', reconnect)
    assert (
        quiet.run(checks.quiet_check_id('synthetic', 'old'), 1, firestore_client=store)
        == 'refused_active_recording_session'
    )
    assert 'finalization_job_id' not in store.rows[ROW]


def test_crash_without_teardown_retains_due_obligation(store, monkeypatch):
    store.rows[ROW]['has_content'] = False
    store.rows[ROW]['transcript_segments'] = []
    quiet.arm('synthetic', 'old', 120, firestore_client=store)
    store.rows[ROW]['has_content'] = True
    store.rows[ROW]['transcript_segments'] = [{'text': 'synthetic later content'}]
    _advance(monkeypatch, 361)
    assert quiet.run(checks.quiet_check_id('synthetic', 'old'), 1, firestore_client=store) == 'queued'
    assert store.rows[ROW]['finalization_revision'] == 1


@pytest.mark.parametrize(
    'updates',
    [
        {'deleted': True},
        {'discarded': True},
        {'is_locked': True},
        {'deferred': True},
        {'status': 'completed'},
        {'processing_state': 'local_pending'},
        {'finalization_job_id': 'existing'},
        {'structured': {'title': 'protected'}},
    ],
)
def test_worker_preserves_guards(store, monkeypatch, updates):
    quiet.arm('synthetic', 'old', 120, firestore_client=store)
    store.rows[ROW].update(updates)
    _advance(monkeypatch, 361)
    assert quiet.run(checks.quiet_check_id('synthetic', 'old'), 1, firestore_client=store) == 'done'
    assert 'finalization_revision' not in store.rows[ROW]


def test_custom_quiet_timeout_cannot_be_shortened_by_fallback_admission(store, monkeypatch):
    quiet.arm('synthetic', 'old', 600, firestore_client=store)
    _advance(monkeypatch, 361)
    result = lifecycle.request_finalization(
        'synthetic',
        'old',
        has_byok_keys=False,
        trigger=quiet.ProcessingTrigger.SERVER_RECOVERY,
        require_cloud_tasks=True,
        recovery_cutoff=NOW + timedelta(seconds=61),
        firestore_client=store,
    )
    assert result['status'] == 'refused_not_quiet'
    assert 'finalization_job_id' not in store.rows[ROW]


def test_kill_switch_disables_new_and_already_scheduled_work(store, monkeypatch):
    monkeypatch.setenv('LISTEN_QUIET_FINALIZATION_ENABLED', 'false')
    quiet.arm('synthetic', 'old', 120, firestore_client=store)
    assert not any(p[0] == 'conversation_finalization_jobs' for p in store.rows)
    monkeypatch.setenv('LISTEN_QUIET_FINALIZATION_ENABLED', 'true')
    quiet.arm('synthetic', 'old', 120, firestore_client=store)
    _advance(monkeypatch, 361)
    monkeypatch.setenv('LISTEN_QUIET_FINALIZATION_ENABLED', 'false')
    assert quiet.run(checks.quiet_check_id('synthetic', 'old'), 1, firestore_client=store) == 'disabled'
    assert 'finalization_job_id' not in store.rows[ROW]


@pytest.mark.asyncio
@pytest.mark.parametrize('close_code', [1000, 1001, 1006, 1011])
@pytest.mark.parametrize('enabled', [True, False])
async def test_real_mono_teardown_arms_on_every_close(monkeypatch, close_code, enabled):
    # Minimal collaborators around the real teardown, including deletion gate.
    runtime = object.__new__(ListenSessionRuntime)
    runtime.request = ListenRequest(
        websocket=SimpleNamespace(client_state=WebSocketState.DISCONNECTED), uid='synthetic'
    )
    runtime.state = SimpleNamespace(
        shutdown_event=asyncio.Event(),
        active=True,
        stt_terminal_failure=False,
        close_code=close_code,
        current_conversation_id='old',
        finalization_reason='retry',
    )
    runtime.conversation_creation_timeout = 120
    runtime.task_supervisor = SimpleNamespace(end_session=MagicMock(), drain_all=AsyncMock())
    runtime._finish_live_transcription = MagicMock()
    runtime._record_session_transcript_outcome = MagicMock()
    runtime.transcripts = SimpleNamespace(flush_translations=AsyncMock(), clear=MagicMock())
    runtime.receiver = SimpleNamespace(finish=MagicMock(), flush_multi_channel_tail=AsyncMock(), clear=MagicMock())
    runtime._flush_usage = AsyncMock()
    runtime.is_multi_channel = False
    runtime.language_observations = runtime.pusher_close = runtime.onboarding_handler = None
    runtime.speakers = SimpleNamespace(clear=MagicMock())

    resumed_metadata = {'recording_session_id': 'new-owner', 'retained': 'keep'}

    async def persist(fn, *args, **kwargs):
        if getattr(fn, '__name__', '') == '_account_deletion_blocks_owner_persistence':
            return False
        if getattr(fn, '__name__', '') == 'get_conversation':
            return {'source': 'omi', 'has_content': True, 'external_data': {'recording_session_id': 'old'}}
        if getattr(fn, '__name__', '') == 'update_conversation':
            updates = args[2]
            assert 'external_data' not in updates
            resumed_metadata['conversation_finalization_reason'] = updates[
                'external_data.conversation_finalization_reason'
            ]
            return True
        return fn(*args, **kwargs)

    runtime.persistence = SimpleNamespace(call=persist)
    monkeypatch.setenv('LISTEN_QUIET_FINALIZATION_ENABLED', str(enabled).lower())
    arm = MagicMock()
    monkeypatch.setattr(quiet, 'arm', arm)
    await runtime._teardown_components()
    assert arm.call_count == int(enabled)
    assert resumed_metadata == {
        'recording_session_id': 'new-owner',
        'retained': 'keep',
        'conversation_finalization_reason': 'retry',
    }


def test_account_deletion_fences_recovery_admission(store, monkeypatch):
    quiet.arm('synthetic', 'old', 120, firestore_client=store)
    store.rows[('account_deletions', 'synthetic')] = {'wipe_status': 'running'}
    _advance(monkeypatch, 361)
    assert quiet.run(checks.quiet_check_id('synthetic', 'old'), 1, firestore_client=store) == 'refused_account_deleting'
    assert 'finalization_job_id' not in store.rows[ROW]


def test_byok_recovery_never_substitutes_platform_credentials(store, monkeypatch):
    quiet.arm('synthetic', 'old', 120, requires_byok=True, firestore_client=store)
    # A subsequent credential-free caller cannot erase the requirement.
    quiet.arm('synthetic', 'old', 120, firestore_client=store)
    _advance(monkeypatch, 361)
    assert quiet.run(checks.quiet_check_id('synthetic', 'old'), 1, firestore_client=store) == 'blocked_byok'
    finalization = store.rows[('conversation_finalization_jobs', store.rows[ROW]['finalization_job_id'])]
    assert finalization['requires_byok'] is True
    assert finalization['status'] == 'blocked_byok'
    lifecycle.enqueue_listen_finalization_job.assert_not_called()


def test_reconnect_updates_quiet_timeout_without_losing_due_obligation(store, monkeypatch):
    quiet.arm('synthetic', 'old', 120, firestore_client=store)
    quiet.arm('synthetic', 'old', 600, firestore_client=store)
    _advance(monkeypatch, 361)
    assert quiet.run(checks.quiet_check_id('synthetic', 'old'), 1, firestore_client=store) == 'deferred'
    assert _job(store)['due_at'] == NOW + timedelta(seconds=600)
    assert 'finalization_job_id' not in store.rows[ROW]


def test_opaque_worker_endpoint_runs_the_durable_check(store, monkeypatch):

    quiet.arm('synthetic', 'old', 120, firestore_client=store)
    _advance(monkeypatch, 361)
    actual = quiet.run
    monkeypatch.setattr(quiet, 'run', lambda jid, gen: actual(jid, gen, firestore_client=store))
    app = FastAPI()
    app.include_router(worker.router)
    app.dependency_overrides[worker.verify_listen_finalization_cloud_tasks_oidc] = lambda: 0
    with TestClient(app) as client:
        response = client.post(
            '/v1/conversation-finalization-jobs/run',
            json={
                'job_id': checks.quiet_check_id('synthetic', 'old'),
                'dispatch_generation': 1,
            },
        )
    assert response.status_code == 200
    assert response.json()['status'] == 'queued'
    assert store.rows[ROW]['finalization_revision'] == 1


def test_missing_recording_lease_is_unknown_not_expired(store, monkeypatch):
    quiet.arm('synthetic', 'old', 120, firestore_client=store)
    del store.rows[SESSION]
    _advance(monkeypatch, 361)
    assert quiet.run(checks.quiet_check_id('synthetic', 'old'), 1, firestore_client=store) == 'deferred'
    assert 'finalization_job_id' not in store.rows[ROW]
    result = lifecycle.request_finalization(
        'synthetic',
        'old',
        has_byok_keys=False,
        trigger=quiet.ProcessingTrigger.SERVER_RECOVERY,
        require_cloud_tasks=True,
        recovery_cutoff=NOW,
        require_expired_recording_lease=True,
        firestore_client=store,
    )
    assert result['status'] == 'refused_recording_lease_unknown'


def test_inline_listen_producer_persists_check_without_queue_bindings(store, monkeypatch):
    monkeypatch.setattr(quiet, 'is_listen_finalization_dispatch_enabled', lambda: False)
    monkeypatch.setattr(quiet, 'is_listen_finalization_dispatch_configured', lambda: False)
    quiet.arm('synthetic', 'old', 120, firestore_client=store)
    assert _job(store)['status'] == checks.QUIET_CHECK_STATUS
    assert _job(store)['reconcile_after_at'] == NOW + timedelta(seconds=120)
    quiet.enqueue_listen_finalization_job.assert_not_called()
    # The Cloud Run worker/reconciler, with existing queue bindings, owns the wake.
    monkeypatch.setattr(quiet, 'is_listen_finalization_dispatch_enabled', lambda: True)
    monkeypatch.setattr(quiet, 'is_listen_finalization_dispatch_configured', lambda: True)
    _advance(monkeypatch, 301)
    assert quiet.run(checks.quiet_check_id('synthetic', 'old'), 1, firestore_client=store) == 'queued'
    assert store.rows[ROW]['finalization_revision'] == 1


def test_kill_switch_restores_legacy_admission_for_a_stamped_long_quiet_window(store, monkeypatch):
    quiet.arm('synthetic', 'old', 14400, firestore_client=store)
    monkeypatch.setenv('LISTEN_QUIET_FINALIZATION_ENABLED', 'false')
    _advance(monkeypatch, 3 * 3600)
    result = lifecycle.request_finalization(
        'synthetic',
        'old',
        has_byok_keys=False,
        trigger=quiet.ProcessingTrigger.SERVER_RECOVERY,
        require_cloud_tasks=True,
        recovery_cutoff=NOW + timedelta(hours=1),
        firestore_client=store,
    )
    assert result['status'] == 'queued'


@pytest.mark.parametrize('fails', [False, True])
def test_reconciler_owns_quiet_wakes_and_reports_failures(monkeypatch, fails):

    monkeypatch.setattr(service.jobs_db, 'recover_stranded_byok_jobs', lambda **kw: {'blocked': 0, 'errors': 0})
    monkeypatch.setattr(service, 'is_listen_finalization_dispatch_enabled', lambda: True)
    monkeypatch.setattr(service, '_publish_job_metrics', lambda **kw: None)
    monkeypatch.setattr(
        service.jobs_db,
        'get_finalization_replay_candidates',
        lambda **kw: [
            {'job_id': 'quiet-synthetic', 'kind': checks.QUIET_CHECK_KIND, 'dispatch_generation': 1},
        ],
    )
    run = MagicMock(side_effect=RuntimeError('synthetic') if fails else None, return_value='deferred')
    monkeypatch.setattr(quiet, 'run', run)
    result = service.reconcile_listen_finalization_jobs()
    run.assert_called_once_with('quiet-synthetic', 1, firestore_client=None)
    assert result['enqueue_failed'] == int(fails)
    assert result['requeued'] == int(not fails)


def test_fast_and_legacy_sweeps_have_independent_cursors(store):
    assert jobs.advance_in_progress_content_sweep_cursor(
        0,
        'users/synthetic/conversations/old',
        quiet=True,
        firestore_client=store,
    )
    fast = jobs.get_in_progress_content_sweep_cursor(quiet=True, firestore_client=store)
    legacy = jobs.get_in_progress_content_sweep_cursor(firestore_client=store)
    assert fast['generation'] == 1
    assert legacy['generation'] == 0
    assert legacy['resume_after_path'] is None


def test_legacy_markerless_content_with_unknown_lease_still_has_recovery(store, monkeypatch):
    store.rows[ROW]['has_content'] = False
    del store.rows[SESSION]
    _advance(monkeypatch, 3 * 3600)
    result = lifecycle.request_finalization(
        'synthetic',
        'old',
        has_byok_keys=False,
        trigger=quiet.ProcessingTrigger.SERVER_RECOVERY,
        require_cloud_tasks=True,
        recovery_cutoff=NOW + timedelta(hours=1),
        firestore_client=store,
    )
    assert result['status'] == 'queued'


@pytest.mark.parametrize('elapsed', [120, 301])
def test_cutover_fences_retire_successor_instead_of_rewaking_forever(store, monkeypatch, elapsed):
    quiet.arm('synthetic', 'old', 120, firestore_client=store)
    quiet.enqueue_listen_finalization_job.reset_mock()
    monkeypatch.setattr(quiet, 'should_skip_background_account_mutation', lambda *a, **kw: True)
    _advance(monkeypatch, elapsed)
    assert quiet.run(checks.quiet_check_id('synthetic', 'old'), 1, firestore_client=store) == 'account_fenced'
    assert _job(store)['status'] == 'quiet_done'
    quiet.enqueue_listen_finalization_job.assert_not_called()
    assert 'finalization_job_id' not in store.rows[ROW]


def test_empty_expired_check_returns_durable_cleanup_obligation_only_in_serve(store, monkeypatch):
    store.rows[ROW].update(has_content=False, transcript_segments=[])
    monkeypatch.setenv('LIFECYCLE_V2_MODE', 'serve')
    quiet.arm('synthetic', 'old', 120, firestore_client=store)
    _advance(monkeypatch, 301)
    result = checks.evaluate_quiet_check(checks.quiet_check_id('synthetic', 'old'), 1, firestore_client=store)
    assert result['status'] == 'empty_ready'
    assert _job(store)['status'] == 'waiting_quiet'
    assert _job(store)['dispatch_generation'] == 2
    assert result['recording_session_id'] == 'recording-old'


@pytest.mark.parametrize('deleted', [True, False])
def test_empty_ready_uses_lifecycle_deletion_and_finishes_only_after_success(store, monkeypatch, deleted):
    store.rows[ROW].update(has_content=False, transcript_segments=[])
    monkeypatch.setenv('LIFECYCLE_V2_MODE', 'serve')
    quiet.arm('synthetic', 'old', 120, firestore_client=store)
    _advance(monkeypatch, 301)
    cleanup = MagicMock(return_value=deleted)
    process = MagicMock(side_effect=AssertionError('empty row must not get paid processing'))
    monkeypatch.setattr(lifecycle, 'delete_empty_recording_conversation', cleanup)
    monkeypatch.setattr(lifecycle, 'request_finalization', process)
    result = quiet.run(checks.quiet_check_id('synthetic', 'old'), 1, firestore_client=store)
    assert result == ('empty_deleted' if deleted else 'deferred')
    assert cleanup.call_args.kwargs['require_expired_recording_lease'] is True
    assert _job(store)['status'] == ('quiet_done' if deleted else 'waiting_quiet')
    process.assert_not_called()


def test_quiet_deadline_and_recovery_admission_share_speech_clock_in_serve(store, monkeypatch):
    row = store.rows[ROW]
    row['last_speech_at'] = NOW - timedelta(minutes=5)
    monkeypatch.setenv('LIFECYCLE_V2_MODE', 'shadow')
    assert checks.quiet_deadline(row, 120, uid='synthetic') == NOW + timedelta(seconds=120)
    assert jobs.recovery_admission_refusal('synthetic', row, NOW - timedelta(seconds=120)) == 'not_stale'
    monkeypatch.setenv('LIFECYCLE_V2_MODE', 'serve')
    assert checks.quiet_deadline(row, 120, uid='synthetic') == NOW - timedelta(minutes=3)
    assert jobs.recovery_admission_refusal('synthetic', row, NOW - timedelta(seconds=120)) is None


def _oversized_write_rejection():
    from google.api_core.exceptions import InvalidArgument

    return InvalidArgument(
        "400 Document 'projects/p/databases/(default)/documents/users/synthetic/conversations/old' cannot be "
        "written because its size (1,048,631 bytes) exceeds the maximum allowed size of 1,048,576 bytes."
    )


def test_oversized_conversation_retires_the_quiet_check_instead_of_retrying_forever(store, monkeypatch):
    """#23341: the 1 MiB refusal is permanent, so the check must stop re-waking and the worker must not 5xx."""
    quiet.arm('synthetic', 'old', 120, firestore_client=store)
    _advance(monkeypatch, 361)

    def refuse(*args, **kwargs):
        raise _oversized_write_rejection()

    monkeypatch.setattr(quiet.lifecycle, 'request_finalization', refuse)
    job_id = checks.quiet_check_id('synthetic', 'old')
    assert quiet.run(job_id, 1, firestore_client=store) == 'document_size_limit'
    job = _job(store)
    assert job['status'] == 'quiet_done'
    assert job['last_failure_code'] == 'document_size_limit'
    assert (
        job['reconcile_after_at'] is firestore.DELETE_FIELD
    )  # the fixture keeps the sentinel; Firestore drops the field
    # The successor wake this run dispatched before admission is now inert.
    assert quiet.run(job_id, job['dispatch_generation'], firestore_client=store) == 'stale'
    # User data stays: the conversation row is neither touched nor terminalized here.
    assert store.rows[ROW]['status'] == 'in_progress'
    assert store.rows[ROW]['transcript_segments'] == [{'text': 'synthetic fixture'}]


def test_other_invalid_argument_rejections_still_surface(store, monkeypatch):
    from google.api_core.exceptions import InvalidArgument

    quiet.arm('synthetic', 'old', 120, firestore_client=store)
    _advance(monkeypatch, 361)

    def refuse(*args, **kwargs):
        raise InvalidArgument('400 synthetic unrelated rejection')

    monkeypatch.setattr(quiet.lifecycle, 'request_finalization', refuse)
    with pytest.raises(InvalidArgument):
        quiet.run(checks.quiet_check_id('synthetic', 'old'), 1, firestore_client=store)
    assert _job(store)['status'] == checks.QUIET_CHECK_STATUS


def test_worker_endpoint_acks_an_oversized_conversation_with_200(store, monkeypatch):
    quiet.arm('synthetic', 'old', 120, firestore_client=store)
    _advance(monkeypatch, 361)

    def refuse(*args, **kwargs):
        raise _oversized_write_rejection()

    monkeypatch.setattr(quiet.lifecycle, 'request_finalization', refuse)
    actual = quiet.run
    monkeypatch.setattr(quiet, 'run', lambda jid, gen: actual(jid, gen, firestore_client=store))
    app = FastAPI()
    app.include_router(worker.router)
    app.dependency_overrides[worker.verify_listen_finalization_cloud_tasks_oidc] = lambda: 0
    payload = {'job_id': checks.quiet_check_id('synthetic', 'old'), 'dispatch_generation': 1}
    with TestClient(app) as client:
        first = client.post('/v1/conversation-finalization-jobs/run', json=payload)
        # Cloud Tasks redelivery of the same generation and the dispatched successor both ack.
        second = client.post('/v1/conversation-finalization-jobs/run', json=payload)
        successor = client.post(
            '/v1/conversation-finalization-jobs/run',
            json={'job_id': payload['job_id'], 'dispatch_generation': _job(store)['dispatch_generation']},
        )
    assert (first.status_code, first.json()['status']) == (200, 'document_size_limit')
    assert (second.status_code, second.json()['status']) == (200, 'stale')
    assert (successor.status_code, successor.json()['status']) == (200, 'stale')
