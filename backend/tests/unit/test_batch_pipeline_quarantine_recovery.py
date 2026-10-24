"""Synthetic recovery through real CAS/privacy/assignment/accounting transactions."""

from copy import deepcopy
from dataclasses import asdict, replace
from unittest.mock import Mock

from types import SimpleNamespace
import pytest

from config.batch_pipeline import recovery_owners
from config.policy import resolve_batch_policy, resolve_stage_policy
from database.batch_pipeline_privacy import privacy_owner_key
from database.batch_pipeline_projection import ProjectionStore
from database.batch_pipeline_projection_protocol import ProjectionBlocked, ProjectionReplay
from database.batch_pipeline_store import FirestoreStore
from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline.contracts import ProjectionBinding, Priority, WorkItem
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.quarantine_recovery import QuarantineRecovery
from utils.batch_pipeline.scheduler import Scheduler, owner_key


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_MODE', 'on')
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST', 'synthetic-owner')
    monkeypatch.delenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', raising=False)
    binding = ProjectionBinding('synthetic-owner', 'bp_upload', 'content', ('bad', 'good'))
    item = WorkItem('bad', binding.owner_id, 1, 'gs://synthetic/audio', 5, Priority.FRESH, privacy_generation=0)
    result = {'segment_id': 'good', 'result_uri': 'gs://synthetic/good', 'outcome': 'success'}
    rows = {
        ('users', binding.owner_id): {'data_protection_level': 'standard'},
        ('batch_pipeline_prod_jobs', 'bad'): {
            **asdict(item),
            'projection_binding': asdict(binding),
            'owner_key': owner_key(binding.owner_id),
            'protocol_version': 1,
            'state': 'quarantined',
            'quarantine_reason': 'worker_failed',
            'recovery_state': 'held',
            'merge_pending': False,
            'token': '',
            'lease_until': 0,
            'enqueued_at': 0,
        },
        ('batch_pipeline_prod_jobs', 'good'): {
            **asdict(replace(item, segment_id='good', capture_at=10)),
            'state': 'committed',
            'projection_binding': asdict(binding),
            'result': result,
        },
        ('batch_pipeline_prod_results', 'good'): {
            'protocol_version': 1,
            'segment_id': 'good',
            'owner_key': owner_key(binding.owner_id),
            'capture_at': 10,
            'previous_segment_id': None,
            'result': result,
            'projection_state': 'quarantine_held',
            'projection': {
                'state': 'ready',
                'speech_seconds': 3,
                'conversation_id': None,
                'created': False,
            },
        },
        ('batch_pipeline_prod_owners', owner_key(binding.owner_id)): {
            'watermark': {'capture_at': 10, 'segment_id': 'good'},
            'log_tail': 'good',
            'log_sequence': 1,
            'projection_watermark': 'good',
        },
        ('users', binding.owner_id, 'sync_content_ledger', binding.content_id): {
            'dispatch_protocol': 'batch_v1',
            'status': 'processing',
            'job_id': binding.job_id,
            'batch_pipeline': {
                'protocol_version': 1,
                'namespace': 'batch_pipeline_prod',
                'segment_ids': list(binding.segment_ids),
            },
        },
    }
    client = StrictFirestore(rows)
    store = FirestoreStore('batch_pipeline_prod', firestore_client=client)
    artifacts = Mock()
    artifacts.fetch_audio.return_value = b'synthetic-only'
    artifacts.persist_recovery_result.return_value = 'gs://synthetic/recovered'
    artifacts.find_recovery_result.return_value = None
    artifacts.load_result.return_value = {'synthetic': True}
    stt = Mock(return_value={'synthetic': True})
    recovery = QuarantineRecovery(store, artifacts, stt=stt, clock=lambda: 100)
    return client, store, binding, artifacts, stt, recovery


def row(client, table='jobs', sid='bad'):
    return client.rows[(f'batch_pipeline_prod_{table}', sid)]


@pytest.mark.parametrize('mode,owners', [('off', 'synthetic-owner'), ('bad', 'synthetic-owner'), ('on', '')])
def test_gate_default_off_and_empty_allowlist_do_no_io(setup, monkeypatch, mode, owners):
    _, _, _, artifacts, stt, recovery = setup
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_MODE', mode)
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST', owners)
    assert not recovery_owners()
    assert recovery.recover('bad', 'synthetic-owner') == 'disabled'
    stt.assert_not_called()
    artifacts.fetch_audio.assert_not_called()
    monkeypatch.delenv('BATCH_PIPELINE_RECOVERY_MODE')
    assert not recovery_owners()


@pytest.mark.parametrize('change', ['lease', 'token', 'result', 'assignment', 'binding', 'legacy'])
def test_handoff_refuses_live_or_receipted_or_foreign_work(setup, change):
    client, _, _, _, stt, recovery = setup
    job = row(client)
    if change == 'lease':
        job['lease_until'] = 200
    elif change == 'token':
        job['token'] = 'old-gpu-flight'
    elif change == 'result':
        job['result'] = {'result_uri': 'already'}
    elif change == 'assignment':
        client.rows[('batch_pipeline_prod_results', 'bad')] = {'projection': {'state': 'persisted'}}
    elif change == 'binding':
        job['projection_binding']['content_id'] = 'foreign'
    else:
        client.rows[('users', 'synthetic-owner', 'sync_content_ledger', 'content')]['dispatch_protocol'] = 'legacy'
    assert recovery.recover('bad', 'synthetic-owner') == 'held'
    stt.assert_not_called()


def test_lease_loss_during_download_blocks_dispatch_and_stale_gpu_cannot_publish(setup):
    client, store, _, artifacts, stt, recovery = setup
    artifacts.fetch_audio.side_effect = lambda _: row(client).update(recovery_state='cancelled') or b'synthetic'
    assert recovery.recover('bad', 'synthetic-owner') == 'held'
    stt.assert_not_called()
    queue = Scheduler(store)
    assert not queue.heartbeat('bad', 'stale-gpu-token', 100)
    from utils.batch_pipeline.contracts import WorkResult

    assert not queue.complete(WorkResult('bad', 'gs://synthetic/stale'), 'stale-gpu-token', 100)


def test_double_delivery_uses_one_stt_and_original_late_capture_identity(setup, monkeypatch):
    client, store, binding, artifacts, stt, recovery = setup
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    assert recovery.recover('bad', binding.owner_id) == 'held'
    assert stt.call_count == 1
    assert artifacts.persist_recovery_result.call_count == 1
    # Exercise the ordinary merge policy on the real handoff job. Query is a
    # supplied hint only; all job/log/privacy writes still use strict transactions.
    monkeypatch.setattr('database.batch_pipeline_store.first_pending', lambda *args, **kwargs: deepcopy(row(client)))
    entry = OrderedMerge(store).commit_next(binding.owner_id, 101)
    assert entry['segment_id'] == 'bad' and entry['capture_at'] == 1
    assert entry['late_capture'] and entry['previous_segment_id'] == 'good'
    assert entry['recovery_version'] == 1 and entry['log_sequence'] == 2
    assert row(client, 'owners', owner_key(binding.owner_id))['watermark']['segment_id'] == 'good'


def test_lost_start_reply_does_not_repeat_stt(setup, monkeypatch):
    client, _, binding, _, stt, recovery = setup
    start = recovery.protocol.start

    def lost(*args, **kwargs):
        assert start(*args, **kwargs)
        raise TimeoutError('synthetic')

    monkeypatch.setattr(recovery.protocol, 'start', lost)
    with pytest.raises(TimeoutError):
        recovery.recover('bad', binding.owner_id)
    assert row(client)['recovery_state'] == 'running'
    assert recovery.recover('bad', binding.owner_id) == 'held'
    stt.assert_not_called()


def test_lost_storage_reply_reconciles_artifact_without_repeating_stt(setup):
    client, _, binding, artifacts, stt, recovery = setup
    artifacts.persist_recovery_result.side_effect = TimeoutError('synthetic')
    assert recovery.recover('bad', binding.owner_id) == 'result_held'
    artifacts.find_recovery_result.return_value = 'gs://synthetic/recovered'
    assert recovery.recover('bad', binding.owner_id) == 'reconciled'
    assert stt.call_count == 1 and row(client)['state'] == 'result_ready'
    assert row(client)['ready_at'] > 0  # Re-entry restarts the bounded merge head wait.


def test_lost_settle_reply_is_reread_without_stt(setup, monkeypatch):
    _, _, binding, _, stt, recovery = setup
    settle = recovery.protocol.settle

    def lost(*args):
        assert settle(*args)
        raise TimeoutError('synthetic')

    monkeypatch.setattr(recovery.protocol, 'settle', lost)
    assert recovery.recover('bad', binding.owner_id) == 'result_held'
    assert recovery.recover('bad', binding.owner_id) == 'held'
    assert stt.call_count == 1


@pytest.mark.parametrize('change', ['account', 'source', 'protection', 'generation'])
@pytest.mark.parametrize('phase', ['download', 'stt'])
def test_deletion_or_protection_change_cancels_mid_recovery(setup, change, phase):
    client, _, binding, artifacts, stt, recovery = setup

    def revoke(*args):
        if change == 'account':
            client.rows[('account_deletions', binding.owner_id)] = {'wipe_status': 'pending'}
        elif change == 'source':
            row(client)['conversation_id'] = 'deleted-source'
            client.rows[('users', binding.owner_id, 'deleted_conversations', 'deleted-source')] = {'deleted': True}
        elif change == 'protection':
            client.rows[('users', binding.owner_id)]['data_protection_level'] = 'e2ee'
        else:
            client.rows[('batch_pipeline_privacy', privacy_owner_key(binding.owner_id))] = {'generation': 1}
        return b'synthetic' if phase == 'download' else {'synthetic': True}

    if phase == 'download':
        artifacts.fetch_audio.side_effect = revoke
    else:
        stt.side_effect = revoke
    assert recovery.recover('bad', binding.owner_id) == 'cancelled'
    assert row(client)['recovery_state'] == 'cancelled'
    assert row(client)['state'] == 'quarantined'
    if phase == 'download':
        stt.assert_not_called()
    assert ('batch_pipeline_prod_results', 'bad') not in client.rows


def test_failed_stt_is_permanently_held_without_loop_or_sensitive_logs(setup, caplog):
    client, _, binding, _, stt, recovery = setup
    stt.side_effect = RuntimeError('PRIVATE_SYNTHETIC_SENTINEL')
    assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    for _ in range(3):
        assert recovery.recover('bad', binding.owner_id) == 'held'
    assert stt.call_count == 1 and row(client)['recovery_state'] == 'failed_held'
    assert row(client)['state'] == 'quarantined' and 'result' not in row(client)
    assert 'PRIVATE_SYNTHETIC_SENTINEL' not in caplog.text


def test_ambiguous_started_intent_is_held_after_bounded_dwell(setup):
    client, _, binding, _, stt, recovery = setup
    prepared = recovery.protocol.prepare('bad', binding.owner_id, 0)
    assert recovery.protocol.start('bad', prepared['recovery']['token'], 0)
    recovery.clock = lambda: 901
    assert recovery.recover('bad', binding.owner_id) == 'held'
    assert row(client)['recovery_state'] == 'failed_held'
    stt.assert_not_called()


def test_crash_after_assignment_replays_receipt_and_meters_once(setup):
    client, store, binding, _, stt, recovery = setup
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    result = row(client)['result']
    row(client)['state'] = 'committed'
    client.rows[('batch_pipeline_prod_results', 'bad')] = {
        'protocol_version': 1,
        'segment_id': 'bad',
        'owner_key': owner_key(binding.owner_id),
        'capture_at': 1,
        'previous_segment_id': 'good',
        'late_capture': True,
        'result': result,
        'projection_state': 'pending',
    }
    projection = ProjectionStore(store)
    binding = projection.read('bad')[2]
    session = projection.session('bad', binding, 101)

    def assign(transaction):
        session.prepare(transaction)
        session.speech_seconds = 2
        session.persist(transaction)

    projection.run(assign)
    # Simulate loss of the assignment reply/process: a fresh session sees the
    # original durable receipt and cannot assign or advance its cursor again.
    with pytest.raises(ProjectionReplay):
        projection.check(projection.session('bad', binding, 102))
    projection.ready('bad', binding, 103)
    accounting = {'seconds': 5.0, 'source': 'sync_fresh', 'updates': {}, 'hour': 'synthetic-hour'}
    first = projection.complete('bad', binding, 104, accounting)
    assert first is not None
    ledger_key = ('users', binding.owner_id, 'sync_content_ledger', binding.content_id)
    original_usage = client.rows[ledger_key]['usage_committed_at']
    assert row(client, 'results', 'good')['projection_state'] == 'ready'
    assert projection.complete('bad', binding, 105, accounting) == first
    assert client.rows[ledger_key]['usage_committed_at'] == original_usage
    # The strict fixture does not model hourly merge writes; exercise the real
    # transaction's metering marker and no-double-charge guard without widening it.
    assert sum(sum('usage_committed_at' in data for _, data in tx.updates) for tx in client.transactions) == 1
    assert stt.call_count == 1


@pytest.fixture
def legacy_dependencies():
    # Provider/model imports are fixture setup, not protocol work.
    import importlib

    for module in (
        'models.conversation',
        'models.conversation_enums',
        'utils.conversations.deterministic_minimum',
        'utils.conversations.final_pass_assignment',
        'utils.sync.intake_completion',
    ):
        importlib.import_module(module)
    from utils.stt import pre_recorded, local_vad as vad
    from utils.batch_pipeline.projection_parts import split_result
    from utils.batch_pipeline.projection import build_incoming
    from utils import fair_use
    from database import llm_usage, hourly_usage_updates

    return pre_recorded, vad, split_result, build_incoming, fair_use, llm_usage, hourly_usage_updates


def test_legacy_adapter_preserves_original_clocks_and_uses_one_sync_client_attempt(monkeypatch, legacy_dependencies):
    import io
    import wave

    pre_recorded, vad, split_result, build_incoming, *_ = legacy_dependencies
    from utils.batch_pipeline.quarantine_recovery import transcribe

    data = io.BytesIO()
    with wave.open(data, 'wb') as wav:
        wav.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        wav.writeframes(b'\0' * (5 * 32000))
    binding = ProjectionBinding('synthetic-owner', 'job', 'content', ('bad',))
    item = WorkItem('bad', binding.owner_id, 100, 'gs://synthetic/audio', 5, Priority.FRESH)
    client = Mock(return_value=([{'text': 'Synthetic.', 'timestamp': [2.2, 3.1], 'speaker': 'SPEAKER_01'}], 'en'))
    monkeypatch.setattr(pre_recorded, 'prerecorded_from_bytes', client)
    monkeypatch.setattr(vad, 'offline_pcm_speech_segments', lambda pcm: [{'start': 2, 'end': 4}])
    from utils.batch_pipeline.audio import with_context

    registered = with_context(data.getvalue(), {'synthetic_provenance': 'PRIVATE_MANIFEST_SENTINEL'})
    payload = transcribe(item, binding, registered)
    assert client.call_count == 1 and client.call_args.kwargs['attempts'] == 2
    assert client.call_args.args[0] == data.getvalue()
    assert b'PRIVATE_MANIFEST_SENTINEL' not in client.call_args.args[0]
    assert payload['speech_seconds'] == 2  # VAD, not whole-unit duration or word estimate
    part, part_payload = split_result(item, payload)[0]
    incoming = build_incoming(part, binding, part_payload)
    first = incoming['transcript_segments'][0]
    assert incoming['started_at'].timestamp() + first['start'] == 102.2
    assert incoming['started_at'].timestamp() + first['end'] == 103.1
    assert first['speaker'] == 'SPEAKER_01'
    assert first['id'] and first['speaker_id_scope'].startswith('sync:')
    client.return_value = ([], 'en')
    with pytest.raises(ValueError, match='empty_asr'):
        transcribe(item, binding, data.getvalue())


def test_projector_replay_bills_fair_use_once_and_releases_retention_after_all_receipts(
    setup, monkeypatch, legacy_dependencies
):
    from utils.batch_pipeline.projection import Projector
    from utils.batch_pipeline import retention

    *_, fair_use, llm_usage, hourly_usage_updates = legacy_dependencies

    client, store, binding, artifacts, stt, recovery = setup
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    row(client)['state'] = 'committed'
    client.rows[('batch_pipeline_prod_results', 'bad')] = {
        'protocol_version': 1,
        'segment_id': 'bad',
        'owner_key': owner_key(binding.owner_id),
        'capture_at': 1,
        'previous_segment_id': 'good',
        'result': row(client)['result'],
        'projection_state': 'persisted',
        'projection': {'state': 'persisted', 'conversation_id': None, 'created': False, 'speech_seconds': 2},
    }
    monkeypatch.setattr(llm_usage, 'resolve_usage_plan_id', lambda *args, **kwargs: 'synthetic-plan')
    # This fixture cannot model merge=True hourly writes. The real ledger marker
    # and fair-use idempotency boundary remain active; no fake transaction escape.
    monkeypatch.setattr(hourly_usage_updates, 'prepare_hourly_usage_updates', lambda *args, **kwargs: {})
    meter = Mock()
    monkeypatch.setattr(fair_use, 'record_speech_ms', meter)

    def expire(*args):
        assert client.rows[('users', binding.owner_id, 'sync_content_ledger', 'content')]['status'] == 'completed'
        assert all(row(client, 'results', sid)['projection']['state'] == 'ready' for sid in binding.segment_ids)
        return True

    monkeypatch.setattr(retention, 'expire_completed_segment', expire)
    projector = Projector(store, artifacts.load_result, publish=Mock(), clock=lambda: 104)
    assert projector.project('bad') is not None
    assert projector.project('bad') is not None
    meter.assert_called_once_with(
        binding.owner_id, 5000, source='sync_fresh', idempotency_key=binding.content_id, raise_on_error=True
    )
    artifacts.load_result.assert_not_called()  # persisted assignment replay never rebuilds a transcript
    assert stt.call_count == 1


def test_reentrant_delivery_while_provider_is_running_never_calls_stt_twice(setup):
    _, _, binding, _, stt, recovery = setup

    def during_request(*args):
        assert recovery.recover('bad', binding.owner_id) == 'held'
        return {'synthetic': True}

    stt.side_effect = during_request
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    assert stt.call_count == 1


def test_recovery_cas_lost_token_and_artifact_registration_are_fenced(setup):
    from utils.batch_pipeline.retention import register_batch_artifact
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    client, store, binding, _, stt, recovery = setup
    job = recovery.protocol.prepare('bad', binding.owner_id, 100)
    token = job['recovery']['token']
    row(client)['recovery']['token'] = 'b' * 32
    assert not recovery.protocol.start('bad', token, 100)
    assert recovery.protocol.start('bad', 'b' * 32, 100)
    with pytest.raises(BatchPrivacyBlocked, match='result_lease_lost'):
        register_batch_artifact(store, binding.owner_id, 'bad', f'gs://synthetic/{token}.enc', 'results', 0)
    register_batch_artifact(store, binding.owner_id, 'bad', 'gs://synthetic/' + 'b' * 32 + '.enc', 'results', 0)
    assert sum(path[0] == 'batch_pipeline_prod_artifacts' for path in client.rows) == 1
    row(client)['recovery_state'] = 'failed_held'
    with pytest.raises(BatchPrivacyBlocked):
        register_batch_artifact(store, binding.owner_id, 'bad', 'gs://synthetic/' + 'b' * 32 + '.enc', 'results', 0)
    stt.assert_not_called()


@pytest.mark.parametrize('enforce', [False, True])
def test_exhausted_recovery_never_starts_a_provider_call(setup, monkeypatch, enforce):
    from types import SimpleNamespace
    from utils import stt_cap_dispatch as cap

    _, _, _, artifacts, stt, recovery = setup
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(enforce))
    monkeypatch.setattr(
        cap, 'funded_allowance', Mock(return_value=SimpleNamespace(managed=False, reason='plan_allowance_exhausted'))
    )
    result = recovery.recover('bad', 'synthetic-owner')
    if enforce:
        assert result == 'held'
        stt.assert_not_called()
        artifacts.fetch_audio.assert_not_called()
    else:
        stt.assert_called_once()
        cap.funded_allowance.assert_not_called()


def test_recovery_rechecks_after_audio_download(setup, monkeypatch):
    from utils.batch_pipeline import quarantine_recovery as module

    _, _, _, artifacts, stt, recovery = setup
    monkeypatch.setattr(module, 'sync_allowed', Mock(side_effect=[True, False]))
    assert recovery.recover('bad', 'synthetic-owner') == 'held'
    artifacts.fetch_audio.assert_called_once()
    stt.assert_not_called()


def test_unavailable_completion_lookup_is_not_reported_as_genuine_exhaustion(setup, monkeypatch):
    from types import SimpleNamespace
    from utils.batch_pipeline import quarantine_recovery as module

    _, _, _, _, _, recovery = setup
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setattr(module, 'sync_allowed', Mock(return_value=True))
    monkeypatch.setattr(
        module, 'funded_allowance', Mock(return_value=SimpleNamespace(managed=False, reason='allowance_unavailable'))
    )
    metric = Mock()
    monkeypatch.setattr(module, 'record_audio', metric)
    assert recovery.recover('bad', 'synthetic-owner') == 'recovered'
    metric.assert_called_once_with('sync', 'accepted', 'unknown', 5, False)


def test_all_admitted_gate_drains_non_allowlisted_obligations_without_admission_flag(setup, monkeypatch):
    client, _, binding, _, stt, recovery = setup
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST', '')
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_ALL_ADMITTED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'false')
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    assert recovery.recover('bad', binding.owner_id) == 'held'
    assert stt.call_count == 1 and row(client)['recovery_state'] == 'recovered'


def test_authoritative_projection_preserves_pyannote_groups_and_gap_abstention(monkeypatch, legacy_dependencies):
    _, _, _, build_incoming, *_ = legacy_dependencies
    monkeypatch.setenv('BATCH_PIPELINE_AUTHORITATIVE_LABELS_ENABLED', 'true')
    binding = ProjectionBinding('synthetic-owner', 'job', 'content', ('unit',))
    item = WorkItem('part', binding.owner_id, 100, 'gs://synthetic/audio', 5, Priority.FRESH)
    payload = {
        'audio_seconds': 5,
        'words_provider': 'parakeet',
        'words': [
            {'word': 'First.', 'timestamp': [0, 1]},
            {'word': 'Gap.', 'timestamp': [2, 3]},
            {'word': 'Last.', 'timestamp': [4, 5]},
        ],
        'diarization': {
            'turns': [
                {'start': 0, 'end': 1, 'speaker': 'SPEAKER_00'},
                {'start': 4, 'end': 5, 'speaker': 'SPEAKER_01'},
            ]
        },
    }
    row = build_incoming(
        item, binding, payload, batch_segment_id='unit', policy=resolve_stage_policy(binding.owner_id, 'projection')
    )
    segments = row['transcript_segments']
    assert [s['speaker'] for s in segments] == ['SPEAKER_00', 'BATCH_UNASSIGNED_part_1', 'SPEAKER_01']
    assert {s['speaker_id_scope'] for s in segments} == {'final:batch:unit'}
    assert all(not s['is_user'] and s['person_id'] is None for s in segments)
    assert segments[1]['speaker_match_source'] == 'batch_abstention'
    assert segments[1]['speaker_identity_status'] == 'ambiguous'
    # Recovery returns legacy utterance labels, never pyannote authority.
    recovered = dict(payload, recovery_version=1)
    recovered['words'] = [dict(w, speaker='SPEAKER_01') for w in payload['words']]
    assert all(
        s['speaker_id_scope'].startswith('sync:')
        for s in build_incoming(item, binding, recovered)['transcript_segments']
    )


def test_recovered_duration_counts_only_one_settlement(setup, monkeypatch):
    from database import batch_pipeline_quarantine_recovery as module

    _, _, binding, _, _, recovery = setup
    metric = Mock()
    monkeypatch.setattr(module, 'record_correctness', metric)
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    assert recovery.recover('bad', binding.owner_id) == 'held'
    metric.assert_called_once_with('recovered', seconds=5)


@pytest.mark.parametrize('enabled', [None, 'true', 'false'])
def test_recovery_tasks_ship_on_with_inline_kill_switch(monkeypatch, enabled):
    from config.batch_pipeline import recovery_tasks_enabled

    monkeypatch.delenv('BATCH_PIPELINE_RECOVERY_TASKS_ENABLED', raising=False)
    if enabled is not None:
        monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_TASKS_ENABLED', enabled)
    assert recovery_tasks_enabled() is (enabled != 'false')


@pytest.mark.parametrize('queue', [None, '', '  ', 'batch-quarantine-recovery'])
def test_request_dispatch_persists_intent_and_retries_wake_without_paid_call(setup, monkeypatch, queue):
    from utils.batch_pipeline import quarantine_recovery as module

    client, _, binding, artifacts, stt, recovery = setup
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE', 'https://synthetic.run.app')
    monkeypatch.setenv('SYNC_TASKS_QUEUE', 'sync-jobs')
    monkeypatch.delenv('BATCH_PIPELINE_RECOVERY_TASKS_QUEUE', raising=False)
    if queue is not None:
        monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_TASKS_QUEUE', queue)
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'synthetic-invoker')
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_WAKE_LEASE_SECONDS', '0')  # Legacy wake kill switch.
    enqueue = Mock()
    monkeypatch.setattr(module, 'enqueue_named_task', enqueue)
    assert recovery.dispatch('bad', binding.owner_id) == 'queued'
    intent = deepcopy(row(client)['recovery'])
    assert row(client)['recovery_state'] == 'prepared'
    assert recovery.dispatch('bad', binding.owner_id) == 'queued'
    assert enqueue.call_args_list[0] == enqueue.call_args_list[1]
    assert enqueue.call_args.args[0] == (queue.strip() if queue and queue.strip() else 'sync-jobs')
    assert enqueue.call_args.args[1] == 'https://synthetic.run.app/v2/batch-pipeline/recover-quarantine'
    assert enqueue.call_args.args[3] == {'stage': 'prod', 'segment_id': 'bad'}
    recovery.clock = lambda: 240
    assert recovery.dispatch('bad', binding.owner_id) == 'queued'
    assert enqueue.call_args_list[2].args[2] != enqueue.call_args_list[1].args[2]
    assert row(client)['recovery'] == intent  # New wake is never a new paid epoch.
    # A delayed old-queue delivery can race the replacement queue's wake.
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_TASKS_QUEUE', 'replacement-recovery')
    assert recovery.dispatch('bad', binding.owner_id) == 'queued'
    assert enqueue.call_args.args[0] == 'replacement-recovery'
    assert row(client)['recovery'] == intent
    artifacts.fetch_audio.assert_not_called()
    stt.assert_not_called()
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    assert recovery.recover('bad', binding.owner_id) == 'held'
    assert stt.call_count == 1


def test_running_dispatch_only_reconciles_and_never_reissues_provider(setup, monkeypatch):
    from utils.batch_pipeline import quarantine_recovery as module

    _, _, binding, artifacts, stt, recovery = setup
    job = recovery.protocol.prepare('bad', binding.owner_id, 100)
    assert recovery.protocol.start('bad', job['recovery']['token'], 100)
    enqueue = Mock()
    monkeypatch.setattr(module, 'enqueue_named_task', enqueue)
    assert recovery.dispatch('bad', binding.owner_id) == 'held'
    artifacts.find_recovery_result.assert_called_once()
    artifacts.fetch_audio.assert_not_called()
    stt.assert_not_called()
    enqueue.assert_not_called()


def test_sweep_batch_one_rollback_and_inline_calls_recover(setup, monkeypatch):
    from utils.batch_pipeline import quarantine_recovery as module

    _, _, binding, _, _, recovery = setup
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_DISPATCH_BATCH_SIZE', '1')
    monkeypatch.setattr(module, 'recovery_candidates', Mock(return_value=[('bad', binding.owner_id)] * 2))
    recovery.dispatch = Mock(return_value='queued')
    recovery.recover = Mock(return_value='recovered')
    assert recovery.sweep() == {'queued': 1}
    recovery.recover.assert_not_called()
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_TASKS_ENABLED', 'false')
    assert recovery.sweep() == {'recovered': 1}
    recovery.recover.assert_called_once()


@pytest.mark.parametrize(
    'audience', ['', 'http://synthetic.invalid', 'https://synthetic.invalid/foreign', 'https://synthetic.invalid?x=1']
)
def test_invalid_request_target_falls_back_inline_with_same_intent(setup, monkeypatch, audience):
    from utils.batch_pipeline import quarantine_recovery as module

    client, _, binding, artifacts, stt, recovery = setup
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE', audience)
    enqueue = Mock()
    monkeypatch.setattr(module, 'enqueue_named_task', enqueue)
    intent = recovery.protocol.prepare('bad', binding.owner_id, 100)['recovery']
    assert recovery.dispatch('bad', binding.owner_id) == 'recovered'
    assert row(client)['recovery']['token'] == intent['token']
    assert row(client)['recovery_state'] == 'recovered'
    enqueue.assert_not_called()
    stt.assert_called_once()
    artifacts.fetch_audio.assert_called_once()


@pytest.mark.parametrize('blocked', ['account', 'source', 'protection'])
def test_dispatch_keeps_privacy_cancellation_before_enqueue(setup, monkeypatch, blocked):
    from utils.batch_pipeline import quarantine_recovery as module

    client, _, binding, artifacts, stt, recovery = setup
    recovery.protocol.prepare('bad', binding.owner_id, 100)
    if blocked == 'account':
        client.rows[('account_deletions', binding.owner_id)] = {'wipe_status': 'pending'}
    elif blocked == 'source':
        row(client)['conversation_id'] = 'deleted-source'
        client.rows[('users', binding.owner_id, 'deleted_conversations', 'deleted-source')] = {'deleted': True}
    else:
        client.rows[('users', binding.owner_id)]['data_protection_level'] = 'e2ee'
    enqueue = Mock()
    monkeypatch.setattr(module, 'enqueue_named_task', enqueue)
    assert recovery.dispatch('bad', binding.owner_id) == 'cancelled'
    assert row(client)['recovery_state'] == 'cancelled'
    enqueue.assert_not_called()
    stt.assert_not_called()
    artifacts.fetch_audio.assert_not_called()


def test_asgi_recovery_delivery_spends_one_fenced_intent(setup, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import batch_pipeline as routes
    from utils.batch_pipeline.serving import Serving
    from unittest.mock import AsyncMock

    _, store, binding, _, stt, recovery = setup
    service = Serving(store, recovery=recovery)
    service.reconcile_async = AsyncMock()
    monkeypatch.setattr(routes, 'serving_for_stage', lambda stage: service)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.verify_worker] = lambda: 0
    client = TestClient(app)
    payload = {'stage': 'prod', 'segment_id': 'bad'}
    assert client.post('/v2/batch-pipeline/recover-quarantine', json=payload).json() == {'status': 'recovered'}
    assert client.post('/v2/batch-pipeline/recover-quarantine', json=payload).json() == {'status': 'held'}
    assert stt.call_count == 1
    service.reconcile_async.assert_awaited_once_with(owner_id=binding.owner_id, recovered='bad')


@pytest.mark.parametrize('delivery_wins', [False, True])
def test_enqueue_failure_falls_back_inline_without_second_paid_call(setup, monkeypatch, delivery_wins):
    from utils.batch_pipeline import quarantine_recovery as module

    client, store, binding, artifacts, stt, recovery = setup
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE', 'https://integration.run.app')
    monkeypatch.setattr(module, 'recovery_candidates', Mock(return_value=[('bad', binding.owner_id)]))
    intent = recovery.protocol.prepare('bad', binding.owner_id, 100)['recovery']

    def enqueue(*args, **kwargs):
        if delivery_wins:
            # The task was created, but the caller lost its acknowledgement.
            assert recovery.recover('bad', binding.owner_id) == 'recovered'
        raise TimeoutError('synthetic lost acknowledgement')

    monkeypatch.setattr(module, 'enqueue_named_task', enqueue)
    metric = Mock()
    monkeypatch.setattr(module, 'record_fallback', metric)
    assert recovery.sweep() == {('held' if delivery_wins else 'recovered'): 1}
    assert row(client)['recovery']['token'] == intent['token']
    assert recovery.recover('bad', binding.owner_id) == 'held'  # Later task delivery/retry.
    stt.assert_called_once()
    assert any(call.kwargs.get('reason') == 'enqueue_failed' for call in metric.call_args_list)


@pytest.mark.parametrize('disabled', ['host', 'cohort', 'missing_recovery'])
def test_asgi_disabled_recovery_is_retryable_without_spending_intent(setup, monkeypatch, disabled):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import batch_pipeline as routes
    from utils.batch_pipeline.serving import Serving

    client, store, binding, artifacts, stt, recovery = setup
    if disabled == 'host':
        monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_MODE', 'off')
    elif disabled == 'cohort':
        monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST', '')
    recovery.protocol.prepare('bad', binding.owner_id, 100)
    service = Serving(store, recovery=None if disabled == 'missing_recovery' else recovery)
    monkeypatch.setattr(routes, 'serving_for_stage', lambda stage: service)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.verify_worker] = lambda: 0
    response = TestClient(app).post(
        '/v2/batch-pipeline/recover-quarantine', json={'stage': 'prod', 'segment_id': 'bad'}
    )
    # Contract (d): retryable means 409 retry (Cloud Tasks retries any non-2xx); 503 throttles the queue.
    assert response.status_code == 409
    assert response.json() == {'status': 'retry', 'reason': 'kill_switch_off'}
    assert row(client)['recovery_state'] == 'prepared'
    stt.assert_not_called()
    artifacts.fetch_audio.assert_not_called()


@pytest.mark.asyncio
async def test_504_leaves_executor_running_and_retry_adopts_token(setup, monkeypatch):
    import asyncio
    import threading
    from starlette.requests import Request
    from routers import batch_pipeline as routes
    from utils.batch_pipeline.serving import Serving
    from utils.other.timeout import TimeoutMiddleware
    from unittest.mock import AsyncMock

    client, store, binding, artifacts, stt, recovery = setup
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    def paid_call(*args):
        entered.set()
        assert release.wait(5)
        return {'synthetic': True}

    stt.side_effect = paid_call

    def persist(*args, **kwargs):
        finished.set()
        return 'gs://synthetic/recovered'

    artifacts.persist_recovery_result.side_effect = persist
    service = Serving(store, recovery=recovery)
    service.reconcile_async = AsyncMock()
    monkeypatch.setattr(routes, 'serving_for_stage', lambda stage: service)
    body = routes.RedriveRequest(stage='prod', segment_id='bad')
    path = '/v2/batch-pipeline/recover-quarantine'
    middleware = TimeoutMiddleware(Mock(), paths_timeout={path: 0.05})
    request = Request({'type': 'http', 'path': path, 'method': 'POST', 'headers': []})

    paid_request = asyncio.create_task(routes.recover_quarantine(body, SimpleNamespace(headers={})))

    async def call_next(request):
        return await paid_request

    try:
        assert await asyncio.to_thread(entered.wait, 2)
        response = await middleware.dispatch(request, call_next)
        assert entered.is_set()
        assert response.status_code == 504
        token = row(client)['recovery']['token']
        assert row(client)['recovery_state'] == 'running'
        assert not finished.is_set()  # Cancelling the await did not stop paid work.
        assert await routes.recover_quarantine(body, SimpleNamespace(headers={})) == {'status': 'held'}
        assert row(client)['recovery']['token'] == token
        stt.assert_called_once()
    finally:
        release.set()
    assert await asyncio.to_thread(finished.wait, 2)
    # Wait for settlement after result persistence, without timing assumptions.
    for _ in range(100):
        if row(client)['recovery_state'] == 'recovered':
            break
        await asyncio.sleep(0.01)
    assert row(client)['recovery_state'] == 'recovered'
    stt.assert_called_once()


@pytest.mark.parametrize('value,expected', [(None, 16), ('1', 1), ('64', 64), ('0', 16), ('65', 16), ('bad', 16)])
def test_recovery_batch_config_is_bounded(monkeypatch, value, expected):
    from config.batch_pipeline import recovery_dispatch_batch_size

    monkeypatch.delenv('BATCH_PIPELINE_RECOVERY_DISPATCH_BATCH_SIZE', raising=False)
    if value is not None:
        monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_DISPATCH_BATCH_SIZE', value)
    assert recovery_dispatch_batch_size() == expected


def test_default_sweep_dispatches_sixteen_resumes_cursor_and_wraps_after_short_page(setup, monkeypatch):
    from utils.batch_pipeline import quarantine_recovery as module

    _, _, binding, _, _, recovery = setup
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_ALL_ADMITTED', 'true')
    candidates = [(f'bad-{i:02}', binding.owner_id) for i in range(33)]
    monkeypatch.setattr(
        module, 'load_stage_policy', lambda *args: ({}, resolve_stage_policy(binding.owner_id, 'recovery'))
    )

    def page(client, namespace, owner, limit, *, after_id):
        assert limit == 16
        return [(sid, uid) for sid, uid in candidates if after_id is None or sid > after_id][:limit]

    query = Mock(side_effect=page)
    monkeypatch.setattr(module, 'recovery_candidates', query)
    recovery.dispatch = Mock(return_value='queued')
    assert recovery.sweep() == {'queued': 16}
    assert recovery.sweep() == {'queued': 16}
    assert recovery.sweep() == {'queued': 1}
    assert recovery.dispatch.call_count == 33
    assert query.call_count == 3
    # The short page ended the scan: the next pass restarts at the first
    # candidate instead of spending a whole pass on an empty page.
    assert recovery.sweep() == {'queued': 16}
    assert query.call_args.kwargs['after_id'] is None
    assert query.call_count == 4


def test_short_page_restarts_scan_so_new_quarantines_dispatch_next_pass(setup, monkeypatch):
    from utils.batch_pipeline import quarantine_recovery as module

    _, _, binding, _, _, recovery = setup
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_ALL_ADMITTED', 'true')
    candidates = [('seg-m', binding.owner_id)]
    monkeypatch.setattr(
        module, 'load_stage_policy', lambda *args: ({}, resolve_stage_policy(binding.owner_id, 'recovery'))
    )
    monkeypatch.setattr(
        module,
        'recovery_candidates',
        lambda client, namespace, owner, limit, *, after_id: [
            (sid, uid) for sid, uid in sorted(candidates) if after_id is None or sid > after_id
        ][:limit],
    )
    recovery.dispatch = Mock(return_value='queued')
    assert recovery.sweep() == {'queued': 1}
    candidates.append(('seg-a', binding.owner_id))  # A new quarantine sorting before the last ID.
    assert recovery.sweep() == {'queued': 2}
    assert [call.args[0] for call in recovery.dispatch.call_args_list] == ['seg-m', 'seg-a', 'seg-m']


def test_overlapping_sweeps_on_one_instance_do_not_double_dispatch(setup, monkeypatch):
    from utils.batch_pipeline import quarantine_recovery as module

    _, _, binding, _, _, recovery = setup
    query = Mock(return_value=[])
    monkeypatch.setattr(module, 'recovery_candidates', query)
    assert recovery._sweeping.acquire(blocking=False)  # The serving pass is mid-scan.
    try:
        assert recovery.sweep() == {}
        query.assert_not_called()
    finally:
        recovery._sweeping.release()
    assert recovery.sweep() == {}
    query.assert_called_once()


@pytest.mark.parametrize(
    'value,expected',
    [(None, 5.0), ('off', 0.0), ('0', 0.0), ('-1', 0.0), ('2', 2.0), ('0.5', 5.0), ('61', 5.0), ('x', 5.0)],
)
def test_recovery_dispatch_interval_is_bounded(monkeypatch, value, expected):
    from config.batch_pipeline import recovery_dispatch_interval_seconds

    monkeypatch.delenv('BATCH_PIPELINE_RECOVERY_DISPATCH_INTERVAL_SECONDS', raising=False)
    if value is not None:
        monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_DISPATCH_INTERVAL_SECONDS', value)
    assert recovery_dispatch_interval_seconds() == expected


def test_sweep_bounds_held_errors_and_advances_global_cursor(setup, monkeypatch):
    from utils.batch_pipeline import quarantine_recovery as module

    _, _, binding, _, _, recovery = setup
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_DISPATCH_BATCH_SIZE', '2')
    monkeypatch.setattr(
        module, 'load_stage_policy', lambda *args: ({}, resolve_stage_policy(binding.owner_id, 'recovery'))
    )
    query = Mock(side_effect=[[("a", "first"), ("b", "first")], [("c", "second")]])
    monkeypatch.setattr(module, 'recovery_candidates', query)
    recovery.dispatch = Mock(side_effect=["held", RuntimeError("private"), "queued"])
    assert recovery.sweep() == {'held': 2}
    assert recovery.sweep() == {'queued': 1}
    assert query.call_args_list[1].kwargs['after_id'] == 'b'


def test_prepared_recovery_uses_its_owner_stamp_after_env_rollback(setup, monkeypatch):
    client, store, binding, artifacts, stt, recovery = setup
    recovery.protocol.prepare('bad', binding.owner_id, 100)
    recorded = row(client)['policy_parts']['recovery']
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_MODE', 'off')
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST', '')
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    assert row(client)['policy_parts']['recovery'] == recorded
    stt.assert_called_once()


def _wake_env(monkeypatch, lease=None):
    from utils.batch_pipeline import quarantine_recovery as module

    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE', 'https://synthetic.run.app')
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_TASKS_QUEUE', 'batch-quarantine-recovery')
    if lease is None:
        monkeypatch.delenv('BATCH_PIPELINE_RECOVERY_WAKE_LEASE_SECONDS', raising=False)
    else:
        monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_WAKE_LEASE_SECONDS', lease)
    enqueue = Mock()
    monkeypatch.setattr(module, 'enqueue_named_task', enqueue)
    # Default custody: the previous wake's task is gone (delivered or exhausted).
    monkeypatch.setattr(module, 'named_task_exists', Mock(return_value=False))
    return module, enqueue


def test_waiting_unit_gets_one_task_across_sweeps_until_the_wake_lease_expires(setup, monkeypatch):
    module, enqueue = _wake_env(monkeypatch)
    client, _, binding, artifacts, stt, recovery = setup
    monkeypatch.setattr(module, 'recovery_candidates', Mock(return_value=[('bad', binding.owner_id)]))
    clock = [100.0]
    recovery.clock = lambda: clock[0]
    outcomes = []
    # A backlog: the queued task is not delivered for ten minutes of 20s sweeps.
    while clock[0] < 100 + 600:
        outcomes.append(recovery.sweep())
        clock[0] += 20
    assert outcomes[0] == {'queued': 1}
    assert all(sweep == {'pending': 1} for sweep in outcomes[1:])
    assert enqueue.call_count == 1
    intent = deepcopy(row(client)['recovery'])
    assert enqueue.call_args.args[2].endswith(f"-{intent['token']}-w1")
    # At expiry a task still waiting in a saturated queue keeps its lease.
    module.named_task_exists.return_value = True
    clock[0] = 701.0
    assert recovery.sweep() == {'pending': 1}
    assert enqueue.call_count == 1
    assert module.named_task_exists.call_args.args == ('batch-quarantine-recovery', enqueue.call_args.args[2])
    assert row(client)['recovery_wake']['wake_until'] == 701.0 + 600
    # Only an authoritative NotFound repairs it with a new deterministic name.
    module.named_task_exists.return_value = False
    clock[0] = 1302.0
    assert recovery.sweep() == {'queued': 1}
    assert enqueue.call_count == 2
    assert enqueue.call_args.args[2].endswith(f"-{intent['token']}-w2")
    assert row(client)['recovery'] == intent
    artifacts.fetch_audio.assert_not_called()
    stt.assert_not_called()


def test_duplicate_wake_names_are_deterministic_and_deliveries_spend_once(setup, monkeypatch):
    module, enqueue = _wake_env(monkeypatch)
    client, _, binding, _, stt, recovery = setup
    assert recovery.dispatch('bad', binding.owner_id) == 'queued'
    first = enqueue.call_args.args[2]
    # A concurrent sweeper that read the same pre-claim snapshot cannot add a wake.
    token = row(client)['recovery']['token']
    assert recovery.protocol.claim_wake('bad', token, 100, 600) is None
    assert recovery.dispatch('bad', binding.owner_id) == 'pending'
    assert enqueue.call_count == 1 and enqueue.call_args.args[2] == first
    # Old-style and new-style deliveries of the same intent still spend once.
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    assert recovery.recover('bad', binding.owner_id) == 'held'
    assert stt.call_count == 1
    assert recovery.dispatch('bad', binding.owner_id) == 'held'  # Settled: no further wakes.
    assert enqueue.call_count == 1


def test_held_delivery_rearms_the_former_cadence_without_new_intent(setup, monkeypatch):
    module, enqueue = _wake_env(monkeypatch)
    client, _, binding, _, stt, recovery = setup
    clock = [100.0]
    recovery.clock = lambda: clock[0]
    assert recovery.dispatch('bad', binding.owner_id) == 'queued'
    intent = deepcopy(row(client)['recovery'])
    clock[0] = 200.0
    name = enqueue.call_args.args[2]
    recovery.delivered('bad', 'held')  # An unnamed (legacy) delivery changes nothing.
    assert row(client)['recovery_wake']['wake_until'] == 700.0
    # Delivered, but e.g. allowance refused the start: Cloud Tasks names the wake.
    recovery.delivered('bad', 'held', f'projects/p/locations/l/queues/q/tasks/{name}')
    assert row(client)['recovery_wake']['wake_until'] == 320.0
    clock[0] = 300.0
    assert recovery.dispatch('bad', binding.owner_id) == 'pending'
    clock[0] = 321.0
    assert recovery.dispatch('bad', binding.owner_id) == 'queued'
    assert enqueue.call_count == 2
    assert row(client)['recovery'] == intent
    recovery.delivered('bad', 'recovered', enqueue.call_args.args[2])  # Only held shortens.
    assert row(client)['recovery_wake']['wake_until'] == 921.0
    stt.assert_not_called()


def test_wake_kill_switch_restores_time_bucketed_wakes(setup, monkeypatch):
    module, enqueue = _wake_env(monkeypatch, lease='0')
    client, _, binding, _, _, recovery = setup
    assert recovery.dispatch('bad', binding.owner_id) == 'queued'
    assert recovery.dispatch('bad', binding.owner_id) == 'queued'
    assert enqueue.call_count == 2
    assert 'recovery_wake' not in row(client)
    recovery.delivered('bad', 'held')
    assert 'recovery_wake' not in row(client)


def test_wake_claim_keeps_the_privacy_fence(setup, monkeypatch):
    module, enqueue = _wake_env(monkeypatch)
    client, _, binding, artifacts, stt, recovery = setup
    token = recovery.protocol.prepare('bad', binding.owner_id, 100)['recovery']['token']
    client.rows[('account_deletions', binding.owner_id)] = {'wipe_status': 'pending'}
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    with pytest.raises(BatchPrivacyBlocked):
        recovery.protocol.claim_wake('bad', token, 100, 600)
    assert recovery.dispatch('bad', binding.owner_id) == 'cancelled'
    enqueue.assert_not_called()
    stt.assert_not_called()


@pytest.mark.parametrize(
    'value,expected', [(None, 600), ('0', 0), ('120', 120), ('3600', 3600), ('119', 600), ('3601', 600), ('x', 600)]
)
def test_recovery_wake_lease_config_is_bounded(monkeypatch, value, expected):
    from config.batch_pipeline import recovery_wake_lease_seconds

    monkeypatch.delenv('BATCH_PIPELINE_RECOVERY_WAKE_LEASE_SECONDS', raising=False)
    if value is not None:
        monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_WAKE_LEASE_SECONDS', value)
    assert recovery_wake_lease_seconds() == expected


def test_enqueue_failure_rearms_the_former_cadence_instead_of_the_full_lease(setup, monkeypatch):
    module, _ = _wake_env(monkeypatch)
    client, _, binding, _, stt, recovery = setup
    monkeypatch.setattr(module, 'enqueue_named_task', Mock(side_effect=RuntimeError('synthetic rejected task')))
    recovery.recover = Mock(return_value='held')  # Inline fallback could not start either.
    assert recovery.dispatch('bad', binding.owner_id) == 'held'
    assert row(client)['recovery_state'] == 'prepared'
    assert row(client)['recovery_wake']['wake_until'] == 100 + 120
    stt.assert_not_called()


def test_stack_harness_accepts_leased_and_legacy_wake_names():
    from testing.sync_cloud_tasks_stack.cloud_tasks import _RECOVERY_TASK_ID

    prefix = 'bpr-prod-' + 'a' * 64 + '-' + 'b' * 32
    assert _RECOVERY_TASK_ID.fullmatch(prefix + '-w1')
    assert _RECOVERY_TASK_ID.fullmatch(prefix + '-15000000')
    assert not _RECOVERY_TASK_ID.fullmatch(prefix + '-wx')


def test_stale_held_delivery_never_shortens_a_newer_wake(setup, monkeypatch):
    module, enqueue = _wake_env(monkeypatch)
    client, _, binding, _, stt, recovery = setup
    clock = [100.0]
    recovery.clock = lambda: clock[0]
    assert recovery.dispatch('bad', binding.owner_id) == 'queued'
    first = enqueue.call_args.args[2]
    clock[0] = 701.0  # w1 was lost before delivery; NotFound repairs with w2.
    assert recovery.dispatch('bad', binding.owner_id) == 'queued'
    assert row(client)['recovery_wake']['seq'] == 2
    clock[0] = 750.0
    recovery.delivered('bad', 'held', first)  # A late duplicate of w1 answers held.
    assert row(client)['recovery_wake']['wake_until'] == 1301.0
    module.named_task_exists.return_value = True
    clock[0] = 900.0
    assert recovery.dispatch('bad', binding.owner_id) == 'pending'  # w2 is still outstanding.
    assert enqueue.call_count == 2
    stt.assert_not_called()


def test_unknown_task_custody_extends_a_bounded_number_of_times(setup, monkeypatch):
    module, enqueue = _wake_env(monkeypatch)
    client, _, binding, _, stt, recovery = setup
    clock = [100.0]
    recovery.clock = lambda: clock[0]
    assert recovery.dispatch('bad', binding.owner_id) == 'queued'
    module.named_task_exists.side_effect = PermissionError('synthetic missing tasks.get')
    for attempt in range(1, 4):
        clock[0] += 601
        assert recovery.dispatch('bad', binding.owner_id) == 'pending'
        assert row(client)['recovery_wake']['probe_errors'] == attempt
    clock[0] += 601
    assert recovery.dispatch('bad', binding.owner_id) == 'queued'  # Never stranded.
    assert row(client)['recovery_wake']['seq'] == 2
    assert 'probe_errors' not in row(client)['recovery_wake']
    assert enqueue.call_count == 2
    stt.assert_not_called()


def test_concurrent_sweepers_cannot_both_advance_an_expired_wake(setup, monkeypatch):
    module, enqueue = _wake_env(monkeypatch)
    client, _, binding, _, _, recovery = setup
    assert recovery.dispatch('bad', binding.owner_id) == 'queued'
    token = row(client)['recovery']['token']
    assert recovery.protocol.claim_wake('bad', token, 800, 600, expected_seq=1) == 2
    # A second sweeper that inspected seq 1 loses the compare-and-set.
    assert recovery.protocol.claim_wake('bad', token, 1500, 600, expected_seq=1) is None


def test_wake_shortening_keeps_the_privacy_fence(setup, monkeypatch):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    module, enqueue = _wake_env(monkeypatch)
    client, _, binding, _, _, recovery = setup
    assert recovery.dispatch('bad', binding.owner_id) == 'queued'
    before = deepcopy(row(client)['recovery_wake'])
    client.rows[('account_deletions', binding.owner_id)] = {'wipe_status': 'pending'}
    with pytest.raises(BatchPrivacyBlocked):
        recovery.delivered('bad', 'held', enqueue.call_args.args[2])
    assert row(client)['recovery_wake'] == before


def test_asgi_held_delivery_rearms_only_its_named_wake(setup, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import batch_pipeline as routes
    from utils.batch_pipeline.serving import Serving

    module, enqueue = _wake_env(monkeypatch)
    client, store, binding, _, stt, recovery = setup
    assert recovery.dispatch('bad', binding.owner_id) == 'queued'
    monkeypatch.setattr(module, 'sync_allowed', lambda *args, **kwargs: False)  # Allowance refuses the start.
    service = Serving(store, recovery=recovery)
    monkeypatch.setattr(routes, 'serving_for_stage', lambda stage: service)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.verify_worker] = lambda: 0
    response = TestClient(app).post(
        '/v2/batch-pipeline/recover-quarantine',
        json={'stage': 'prod', 'segment_id': 'bad'},
        headers={'X-CloudTasks-TaskName': f'projects/p/locations/l/queues/q/tasks/{enqueue.call_args.args[2]}'},
    )
    assert response.json() == {'status': 'held'}
    assert row(client)['recovery_wake']['wake_until'] == 100 + 120
    stt.assert_not_called()


def test_extend_never_overrides_a_concurrent_held_rearm(setup, monkeypatch):
    module, enqueue = _wake_env(monkeypatch)
    client, _, binding, _, _, recovery = setup
    clock = [100.0]
    recovery.clock = lambda: clock[0]
    assert recovery.dispatch('bad', binding.owner_id) == 'queued'
    token = row(client)['recovery']['token']
    clock[0] = 701.0
    # The delivery answers held while the sweep's custody probe is in flight.
    recovery.delivered('bad', 'held', enqueue.call_args.args[2])
    assert row(client)['recovery_wake']['wake_until'] == 821.0
    assert recovery.protocol.extend_wake('bad', token, 1, 701.0, 600) is False
    assert row(client)['recovery_wake']['wake_until'] == 821.0


def _freeze_disabled_snapshot(monkeypatch, recovery, binding):
    """Admit the unit's recovery part while recovery is off for its owner."""
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST', '')
    assert recovery.recover('bad', binding.owner_id) == 'disabled'


def test_disabled_snapshot_with_no_paid_intent_refreshes_once_enabled(setup, monkeypatch):
    client, _, binding, _, stt, recovery = setup
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_POLICY_REFRESH_ENABLED', 'false')
    _freeze_disabled_snapshot(monkeypatch, recovery, binding)
    assert row(client)['policy_parts']['recovery']['recovery_enabled'] is False
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_ALL_ADMITTED', 'true')
    # Kill switch off: the frozen verdict stands even though recovery is now on.
    assert recovery.recover('bad', binding.owner_id) == 'disabled'
    stt.assert_not_called()
    monkeypatch.delenv('BATCH_PIPELINE_RECOVERY_POLICY_REFRESH_ENABLED')
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    assert stt.call_count == 1
    assert row(client)['policy_parts']['recovery']['recovery_enabled'] is True
    assert row(client)['policy_part_sources']['recovery'] == 'refreshed'
    assert recovery.recover('bad', binding.owner_id) == 'held'
    assert stt.call_count == 1


def test_refresh_never_adopts_a_still_disabled_setting(setup, monkeypatch):
    client, _, binding, artifacts, stt, recovery = setup
    _freeze_disabled_snapshot(monkeypatch, recovery, binding)
    recorded = dict(row(client)['policy_parts']['recovery'])
    assert recovery.recover('bad', binding.owner_id) == 'disabled'
    assert row(client)['policy_parts']['recovery'] == recorded
    assert 'policy_part_sources' not in row(client) or row(client)['policy_part_sources'].get('recovery') != 'refreshed'
    stt.assert_not_called()
    artifacts.fetch_audio.assert_not_called()


@pytest.mark.parametrize('change', ['intent', 'failed_held', 'foreign'])
def test_refresh_never_touches_spent_or_foreign_units(setup, monkeypatch, change):
    from database.batch_pipeline_policy import refresh_disabled_recovery

    client, store, binding, _, stt, recovery = setup
    _freeze_disabled_snapshot(monkeypatch, recovery, binding)
    if change == 'intent':
        row(client)['recovery'] = {'token': 'spent', 'epoch': 1, 'privacy_generation': 0}
    elif change == 'failed_held':
        row(client)['recovery_state'] = 'failed_held'
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_ALL_ADMITTED', 'true')
    owner = 'other-owner' if change == 'foreign' else binding.owner_id
    before = dict(row(client))
    assert refresh_disabled_recovery(store, 'bad', owner) is None
    assert row(client) == before
    stt.assert_not_called()


def test_dispatch_refreshes_disabled_snapshot_before_enqueue(setup, monkeypatch):
    client, _, binding, _, stt, recovery = setup
    _freeze_disabled_snapshot(monkeypatch, recovery, binding)
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST', binding.owner_id)
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE', '')
    outcome = recovery.dispatch('bad', binding.owner_id)
    assert outcome != 'disabled'
    assert row(client)['policy_parts']['recovery']['recovery_enabled'] is True


PARTIAL_ACCOUNTING = {
    'seconds': 3,
    'source': 'sync_fresh',
    'updates': {},
    'hour': 'synthetic-hour',
    'completed': False,
    'charged': 0.0,
}


def ledger_row(client, binding):
    return client.rows[('users', binding.owner_id, 'sync_content_ledger', binding.content_id)]


def test_terminally_held_upload_completes_partial_once_without_touching_held_unit(setup):
    client, store, binding, artifacts, stt, _ = setup
    row(client)['recovery_state'] = 'failed_held'
    jobs_before = deepcopy({key: value for key, value in client.rows.items() if key[0].endswith('_jobs')})
    good_before = deepcopy(row(client, 'results', 'good'))
    projection = ProjectionStore(store)
    result, step = projection.complete_partial(binding, 101, PARTIAL_ACCOUNTING)
    assert result == {
        'new_memories': [],
        'updated_memories': [],
        'failed_segments': 1,
        'held_segments': 1,
        'total_segments': 2,
        'errors': [],
        'outcome': 'partial',
    }
    ledger = ledger_row(client, binding)
    assert ledger['status'] == 'partial' and ledger['result'] == result
    assert ledger['usage_committed_seconds'] == 3 and ledger['job_id'] == binding.job_id
    assert step == ([0.0, 3], [101]) and ledger['usage_steps'] == [0.0, 3] and ledger['usage_step_times'] == [101]
    # Paid-once and ordered-head: no provider call, no job/intent/merge write,
    # the parked sibling keeps its receipt, and the held audio is not touched.
    assert {key: value for key, value in client.rows.items() if key[0].endswith('_jobs')} == jobs_before
    assert row(client, 'results', 'good') == good_before
    assert ('batch_pipeline_prod_results', 'bad') not in client.rows
    stt.assert_not_called()
    artifacts.fetch_audio.assert_not_called()
    # Idempotent: a replay reads the same partial and writes nothing.
    writes = sum(len(tx.updates) for tx in client.transactions)
    assert projection.complete_partial(binding, 102, PARTIAL_ACCOUNTING) == (result, step)
    assert sum(len(tx.updates) for tx in client.transactions) == writes
    assert ledger_row(client, binding)['updated_at'] == ledger['updated_at']


@pytest.mark.parametrize('change', ['prepared', 'running', 'enabled_held', 'operator_intent', 'not_ready', 'none'])
def test_partial_waits_while_anything_can_still_change(setup, change):
    client, store, binding, _, stt, _ = setup
    job = row(client)
    job['recovery_state'] = 'failed_held'
    if change in {'prepared', 'running'}:
        job['recovery_state'] = change
    elif change == 'enabled_held':
        job['recovery_state'] = 'held'
        job['policy_parts'] = {'recovery': resolve_stage_policy(binding.owner_id, 'recovery').to_dict()}
        assert job['policy_parts']['recovery']['recovery_enabled'] is True
    elif change == 'operator_intent':
        job['speech_redrive'] = {'state': 'prepared', 'token': 'reviewed'}
    elif change == 'not_ready':
        row(client, 'results', 'good')['projection']['state'] = 'persisted'
    else:
        job.update(state='committed', recovery_state='recovered')
    before = deepcopy(client.rows)
    assert ProjectionStore(store).complete_partial(binding, 101, PARTIAL_ACCOUNTING) is None
    assert client.rows == before
    stt.assert_not_called()


def test_partial_refuses_a_completed_or_foreign_ledger(setup):
    client, store, binding, _, _, _ = setup
    row(client)['recovery_state'] = 'failed_held'
    ledger_row(client, binding)['job_id'] = 'bp_replacement'
    with pytest.raises(ProjectionBlocked, match='ledger owner'):
        ProjectionStore(store).complete_partial(binding, 101, PARTIAL_ACCOUNTING)
    ledger_row(client, binding).update(job_id=binding.job_id, status='completed')
    before = deepcopy(client.rows)
    assert ProjectionStore(store).complete_partial(binding, 101, PARTIAL_ACCOUNTING) is None
    assert client.rows == before


def test_partial_status_answers_completed_with_held_span(setup):
    from utils.batch_pipeline.intake import durable_status

    client, store, binding, _, _, _ = setup
    row(client)['recovery_state'] = 'failed_held'
    client.rows[('batch_pipeline_prod_intakes', binding.job_id)] = {
        'owner_id': binding.owner_id,
        'content_id': binding.content_id,
        'segment_ids': list(binding.segment_ids),
        'lane': 'backfill',
        'total_files': 1,
    }
    result, _ = ProjectionStore(store).complete_partial(binding, 101, PARTIAL_ACCOUNTING)
    status = durable_status(store, binding.owner_id, binding.job_id)
    assert status['status'] == 'completed' and status['reason_code'] == 'batch_unit_held'
    assert status['failed_segments'] == 1 and status['successful_segments'] == 1
    assert status['result'] == result and status['poll_after_ms'] == 0 and status['errors'] == []


def test_recovery_disabled_unit_completes_partial_then_upgrades_after_recovery(setup, monkeypatch):
    client, store, binding, _, stt, recovery = setup
    _freeze_disabled_snapshot(monkeypatch, recovery, binding)
    projection = ProjectionStore(store)
    partial, _ = projection.complete_partial(binding, 101, PARTIAL_ACCOUNTING)
    assert partial['held_segments'] == 1 and ledger_row(client, binding)['status'] == 'partial'
    # Recovery turns on later: the partial ledger still belongs to the batch job,
    # so the one paid recovery runs and the ordinary completion upgrades it.
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_ALL_ADMITTED', 'true')
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    assert stt.call_count == 1
    result = row(client)['result']
    row(client)['state'] = 'committed'
    client.rows[('batch_pipeline_prod_results', 'bad')] = {
        'protocol_version': 1,
        'segment_id': 'bad',
        'owner_key': owner_key(binding.owner_id),
        'capture_at': 1,
        'previous_segment_id': 'good',
        'late_capture': True,
        'result': result,
        'projection_state': 'pending',
    }
    binding = projection.read('bad')[2]
    session = projection.session('bad', binding, 102)

    def assign(transaction):
        session.prepare(transaction)
        session.speech_seconds = 2
        session.persist(transaction)

    projection.run(assign)
    projection.ready('bad', binding, 103)
    stale = {**PARTIAL_ACCOUNTING, 'seconds': 5.0}
    with pytest.raises(ProjectionBlocked, match='usage accounting changed'):
        projection.complete('bad', binding, 104, stale)
    upgraded = projection.complete('bad', binding, 104, {**stale, 'charged': 3})
    ledger = ledger_row(client, binding)
    assert ledger['status'] == 'completed' and ledger['result'] == upgraded
    assert upgraded['failed_segments'] == 0 and upgraded['total_segments'] == 2
    assert ledger['usage_committed_seconds'] == 5.0 and ledger['usage_steps'] == [0.0, 3, 5.0]
    assert ledger['usage_step_times'] == [101, 104]
    # A held span already settled as partial is never re-partialed after completion.
    assert projection.complete_partial(binding, 105, PARTIAL_ACCOUNTING) is None
    assert stt.call_count == 1


def test_partial_accounting_charges_only_the_remainder(setup, monkeypatch):
    from database import hourly_usage_updates, llm_usage

    client, store, binding, _, _, _ = setup
    row(client)['recovery_state'] = 'failed_held'
    charged = []
    monkeypatch.setattr(llm_usage, 'resolve_usage_plan_id', lambda *args, **kwargs: 'synthetic-plan')
    monkeypatch.setattr(
        hourly_usage_updates,
        'prepare_hourly_usage_updates',
        lambda stamp, counts, *args, **kwargs: charged.append(counts) or {'synthetic': counts},
    )
    projection = ProjectionStore(store)
    assert projection.prepare_accounting(binding, 100) is None
    accounting = projection.prepare_accounting(binding, 100, held=True)
    assert accounting['seconds'] == 3 and accounting['charged'] == 0.0
    assert charged == [{'transcription_seconds': 3, 'speech_seconds': 3}]
    ledger_row(client, binding).update(status='partial', usage_committed_seconds=3)
    row(client, 'results', 'good')['projection']['speech_seconds'] = 8
    again = projection.prepare_accounting(binding, 100, held=True)
    assert again['charged'] == 3 and charged[-1] == {'transcription_seconds': 5, 'speech_seconds': 5}


def test_held_sweep_completes_each_upload_once_and_contains_failures(setup, monkeypatch):
    from utils import fair_use
    from utils.batch_pipeline.projection import Projector

    client, store, binding, artifacts, stt, _ = setup
    row(client)['recovery_state'] = 'failed_held'
    # The first fair-use write fails after the partial committed (Redis outage).
    monkeypatch.setattr(fair_use, 'record_speech_ms', Mock(side_effect=[RuntimeError('synthetic redis'), None]))
    projector = Projector(store, artifacts.load_result, clock=lambda: 101)
    real_accounting = projector.store.prepare_accounting

    def accounting(target, now, *, held=False):
        assert held
        if target.content_id != binding.content_id:
            return real_accounting(target, now, held=held)
        return dict(PARTIAL_ACCOUNTING)

    projector.store.prepare_accounting = accounting
    foreign = {'projection_binding': {**row(client)['projection_binding'], 'content_id': 'foreign'}}
    page = [('bad', row(client)), ('bad-sibling', deepcopy(row(client))), ('foreign', foreign), ('broken', {})]
    monkeypatch.setattr(
        'utils.batch_pipeline.projection.held_candidates', lambda client, ns, limit, after_id=None: page[:limit]
    )
    # Same upload once; a foreign ledger is never charged; a malformed row is contained.
    assert projector.sweep_held(limit=4) == {'partial': 0, 'waiting': 1, 'error': 2}
    assert ledger_row(client, binding)['status'] == 'partial'
    assert projector.held_after == 'broken'
    writes = sum(len(tx.updates) for tx in client.transactions)
    assert projector.sweep_held(limit=5) == {'partial': 1, 'waiting': 1, 'error': 1}
    # A short page wraps the cursor; the replay wrote nothing new and re-issued
    # the same durable fair-use step, so the lost charge lands exactly once.
    assert projector.held_after is None
    assert sum(len(tx.updates) for tx in client.transactions) == writes
    keys = [(call.args[1], call.kwargs['idempotency_key']) for call in fair_use.record_speech_ms.call_args_list]
    assert keys == [(3000, 'content'), (3000, 'content')]
    stt.assert_not_called()


@pytest.mark.parametrize('change', ['speech_redrive', 'recovery_enabled'])
def test_unfinished_held_unit_is_never_accounted_or_charged(setup, monkeypatch, change):
    from utils import fair_use
    from utils.batch_pipeline.projection import Projector

    client, store, binding, artifacts, _, _ = setup
    job = row(client)
    if change == 'speech_redrive':
        job.update(recovery_state='failed_held', speech_redrive={'state': 'running', 'token': 'reviewed'})
    else:
        job['policy_parts'] = {'recovery': resolve_stage_policy(binding.owner_id, 'recovery').to_dict()}
    monkeypatch.setattr(fair_use, 'record_speech_ms', Mock())
    projector = Projector(store, artifacts.load_result, clock=lambda: 101)
    before = deepcopy(client.rows)
    assert projector.store.prepare_accounting(binding, 101, held=True) is None
    assert projector.complete_held(binding) is None
    fair_use.record_speech_ms.assert_not_called()
    assert client.rows == before


def test_fair_use_charge_after_partial_uses_a_distinct_once_key(monkeypatch):
    from utils import fair_use
    from utils.batch_pipeline.projection import record_speech

    calls = []
    monkeypatch.setattr(fair_use, 'record_speech_ms', lambda *args, **kwargs: calls.append((args, kwargs)))
    binding = ProjectionBinding('synthetic-owner', 'bp_upload', 'content', ('bad', 'good'))
    record_speech(binding, {'seconds': 3, 'source': 'sync_fresh', 'completed': False}, 100)
    calls.clear()
    # After a partial at 3 s (stored steps [0, 3]) the upgrade re-issues the base
    # step under its own key, then the remainder: a base lost to a Redis failure
    # after the partial commit still lands, and one that landed is a SET NX no-op.
    record_speech(
        binding, {'seconds': 5, 'source': 'sync_fresh', 'completed': False, 'steps': [0.0, 3], 'step_times': [90]}, 100
    )
    assert [(args[1], kwargs['idempotency_key']) for args, kwargs in calls] == [
        (3000, 'content'),
        (2000, 'content:3000'),
    ]
    calls.clear()
    record_speech(
        binding, {'seconds': 5, 'source': 'sync_fresh', 'completed': True, 'steps': [0.0, 3], 'step_times': [90]}, 100
    )
    assert calls == []


def test_expired_or_unknown_age_step_is_never_readmitted(monkeypatch):
    from utils import fair_use
    from utils.batch_pipeline.projection import record_speech_steps, reissue_window_seconds

    calls = []
    monkeypatch.setattr(fair_use, 'record_speech_ms', lambda *args, **kwargs: calls.append(kwargs['idempotency_key']))
    binding = ProjectionBinding('synthetic-owner', 'bp_upload', 'content', ('bad', 'good'))
    now = 10 * 86400.0
    window = reissue_window_seconds()
    assert 0 < window < fair_use.FAIR_USE_REDIS_RETENTION_SECONDS
    # A unit held past the once-key TTL: its old step stays out, the fresh one lands.
    record_speech_steps(binding, 'sync_fresh', [0.0, 3, 5], [now - window - 1, now], now)
    assert calls == ['content:3000']
    calls.clear()
    # A legacy partial without commit times: never re-issued.
    record_speech_steps(binding, 'sync_fresh', [0.0, 3], [None], now)
    assert calls == []


def test_lost_base_charge_lands_after_a_newer_partial_step(setup, monkeypatch):
    from utils import fair_use
    from utils.batch_pipeline.projection import Projector

    client, store, binding, artifacts, _, _ = setup
    row(client)['recovery_state'] = 'failed_held'
    landed = {}

    def once(uid, ms, source, idempotency_key, raise_on_error):
        if fail[0]:
            fail[0] = False
            raise RuntimeError('synthetic redis')
        landed.setdefault(idempotency_key, ms)

    fail = [True]
    monkeypatch.setattr(fair_use, 'record_speech_ms', once)
    projector = Projector(store, artifacts.load_result, clock=lambda: 101)
    projector.store.prepare_accounting = lambda target, now, held=False: {
        **PARTIAL_ACCOUNTING,
        'charged': 0.0,
        'steps': [0.0],
    }
    with pytest.raises(RuntimeError):
        projector.complete_held(binding)
    # The partial committed (0 -> 3) but its fair-use write was lost. A newer
    # step (3 -> 5) commits next: both keys land, base included.
    assert ledger_row(client, binding)['usage_steps'] == [0.0, 3]
    # Stand in for an earlier partial over a wider held span, so this pass rewrites it.
    ledger_row(client, binding)['result'] = {**ledger_row(client, binding)['result'], 'superseded_segments': 1}
    row(client, 'results', 'good')['projection']['speech_seconds'] = 5
    projector.store.prepare_accounting = lambda target, now, held=False: {
        **PARTIAL_ACCOUNTING,
        'seconds': 5,
        'charged': 3,
        'steps': [0.0, 3],
    }
    assert projector.complete_held(binding) is not None
    assert ledger_row(client, binding)['usage_steps'] == [0.0, 3, 5]
    assert landed == {'content': 3000, 'content:3000': 2000}


@pytest.mark.parametrize('access', ['capped', 'byok', 'reviewer', 'paid', 'kill_off'])
def test_default_on_quarantine_allowance_preserves_custody_and_funding(setup, monkeypatch, access):
    from utils import stt_cap_dispatch as cap

    client, store, binding, artifacts, stt, recovery = setup
    monkeypatch.setenv('STT_CAP_OFFLINE_ENFORCEMENT', 'false' if access == 'kill_off' else 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false')
    if access == 'byok':
        row(client)['policy'] = {'provider_reason': 'byok'}
    resolver = Mock(
        return_value=SimpleNamespace(managed=access in {'reviewer', 'paid'}, reason='plan_allowance_exhausted')
    )
    monkeypatch.setattr(cap, 'funded_allowance', resolver)
    result = recovery.recover('bad', binding.owner_id)
    assert stt.call_count == (0 if access == 'capped' else 1)
    if access == 'capped':
        assert result == 'held' and row(client)['recovery_state'] == 'prepared'
    if access in {'byok', 'kill_off'}:
        resolver.assert_not_called()
