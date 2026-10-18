"""Synthetic recovery through real CAS/privacy/assignment/accounting transactions."""

from copy import deepcopy
from dataclasses import asdict, replace
from unittest.mock import Mock

import pytest

from config.batch_pipeline import recovery_owners
from database.batch_pipeline_privacy import privacy_owner_key
from database.batch_pipeline_projection import ProjectionStore
from database.batch_pipeline_projection_protocol import ProjectionReplay
from database.batch_pipeline_store import FirestoreStore
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
    row = build_incoming(item, binding, payload, batch_segment_id='unit')
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
