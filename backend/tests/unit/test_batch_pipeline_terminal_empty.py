"""Exhaustion completes siblings without claiming silence or repeating paid STT."""

from copy import deepcopy
from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

import importlib.util
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

from tests.unit.test_batch_pipeline_quarantine_recovery import setup, legacy_dependencies, row
from tests.unit.test_batch_pipeline_speech_redrive import enabled
from tests.unit.test_batch_pipeline_empty_disposition import wav, work, SERVING_ENV
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_quarantine_recovery import RecoveryStore
from database.batch_pipeline_terminal_empty import TerminalEmptyStore, intent_snapshot, exhausted, CANARY_OPERATION
from utils.batch_pipeline.quarantine_recovery import transcribe
from utils.batch_pipeline.recovery_disposition import terminal_empty_payload, result_outcome, RecoveryFailure
from utils.batch_pipeline.merge import OrderedMerge


def terminal_setup(setup, monkeypatch, legacy_dependencies):
    values = enabled(setup, monkeypatch, legacy_dependencies)
    client, store, binding, artifacts, legacy, alternate, old = values
    transaction = client.transaction
    monkeypatch.setattr(client, 'transaction', lambda **kwargs: transaction())
    monkeypatch.setenv('BATCH_PIPELINE_TERMINAL_EMPTY_DISPOSITION_ENABLED', 'true')
    row(client)['worker_empty_evidence'] = {'padded_retry': 'empty', 'version': 1}
    alternate.return_value = ([], 'vi')
    return values


def load_operator():
    path = Path(__file__).parents[2] / 'scripts'
    monkey = str(path)
    if monkey not in sys.path:
        sys.path.insert(0, monkey)
    spec = importlib.util.spec_from_file_location('terminal_operator', path / 'batch_pipeline_terminal_empty.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_exhaustion_is_distinct_and_paid_once(setup, monkeypatch, legacy_dependencies, caplog):
    caplog.set_level('INFO')
    client, _, binding, _, legacy, alternate, _ = terminal_setup(setup, monkeypatch, legacy_dependencies)
    row(client).pop('recovery')
    row(client)['recovery_state'] = 'held'
    recovery = setup[-1]
    recovery.stt = transcribe
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    job = row(client)
    assert job['result']['outcome'] == 'no_recoverable_speech'
    assert job['recovery']['provider'] == 'modulate'
    assert job['recovery']['settled_at'] == 100
    payload = setup[3].persist_recovery_result.call_args.args[1]
    assert result_outcome(payload) == 'no_recoverable_speech'
    assert payload['words'] == [] and payload['speech_seconds'] == 1
    assert 'reason=no_recoverable_speech' in caplog.text
    for _ in range(2):
        assert recovery.recover('bad', binding.owner_id) == 'held'
    alternate.assert_called_once()
    legacy.assert_not_called()


@pytest.mark.parametrize('missing', ['flag', 'gpu_evidence', 'multilingual', 'vad_positive', 'definite_empty'])
def test_terminal_requires_all_evidence(setup, monkeypatch, legacy_dependencies, missing):
    client, _, binding, _, legacy, alternate, _ = terminal_setup(setup, monkeypatch, legacy_dependencies)
    row(client).pop('recovery')
    row(client)['recovery_state'] = 'held'
    if missing == 'flag':
        monkeypatch.delenv('BATCH_PIPELINE_TERMINAL_EMPTY_DISPOSITION_ENABLED')
    elif missing == 'gpu_evidence':
        row(client).pop('worker_empty_evidence')
    elif missing == 'multilingual':
        monkeypatch.delenv('BATCH_PIPELINE_SPEECH_EMPTY_MULTILINGUAL_ENABLED')
        legacy.return_value = ([], 'en')
    elif missing == 'vad_positive':
        monkeypatch.setattr(legacy_dependencies[1], 'offline_pcm_speech_segments', lambda _: [])
    else:
        alternate.side_effect = TimeoutError('PRIVATE_SENTINEL')
    setup[-1].stt = transcribe
    result = setup[-1].recover('bad', binding.owner_id)
    if missing == 'vad_positive':
        assert result == 'recovered' and row(client)['result']['outcome'] == 'silence'
        alternate.assert_not_called()
    else:
        assert result == 'failed_held' and not row(client).get('result')


def test_lost_artifact_reply_reconciles_without_paid_retry_even_flag_off(setup, monkeypatch, legacy_dependencies):
    client, _, binding, artifacts, _, alternate, _ = terminal_setup(setup, monkeypatch, legacy_dependencies)
    row(client).pop('recovery')
    row(client)['recovery_state'] = 'held'
    recovery = setup[-1]
    recovery.stt = transcribe
    artifacts.persist_recovery_result.side_effect = RuntimeError('PRIVATE_SENTINEL')
    assert recovery.recover('bad', binding.owner_id) == 'result_held'
    assert row(client)['recovery_state'] == 'running'
    assert recovery.recover('bad', binding.owner_id) == 'held'
    artifacts.find_recovery_result.return_value = 'gs://synthetic/reconciled'
    artifacts.load_result.return_value = terminal_empty_payload(5, [{'start': 1, 'end': 2}])
    monkeypatch.delenv('BATCH_PIPELINE_TERMINAL_EMPTY_DISPOSITION_ENABLED')
    assert recovery.recover('bad', binding.owner_id) == 'reconciled'
    assert row(client)['result']['outcome'] == 'no_recoverable_speech'
    alternate.assert_called_once()


@pytest.mark.parametrize('change', ['words', 'spans', 'provider', 'evidence'])
def test_terminal_payload_rejects_fabrication(change):
    payload = terminal_empty_payload(5, [{'start': 1, 'end': 2}])
    if change == 'words':
        payload['words'] = [{'word': 'Synthetic'}]
    elif change == 'spans':
        payload['speech_spans'] = []
    elif change == 'provider':
        payload['words_provider'] = 'strict_local_vad'
    else:
        payload['recognition_evidence']['multilingual_recovery'] = 'timeout'
    with pytest.raises(RecoveryFailure):
        result_outcome(payload)


def historical(client, *, epoch2=False, canary=False):
    job = row(client)
    if canary:
        job['operator_redrive'] = {'operation': CANARY_OPERATION, 'cohort_key': 'synthetic'}
        job['recovery_state'] = 'held'
    elif epoch2:
        job['speech_redrive'] = {
            'state': 'failed_held',
            'paid_epoch': 2,
            'provider': 'modulate',
            'prior_recovery': deepcopy(job['recovery']),
            'settled_at': 50,
            'failure': {'stage': 'response_validation', 'reason': 'empty_asr'},
        }
    else:
        job['recovery']['failure'] = {'stage': 'response_validation', 'reason': 'empty_asr'}
    return deepcopy(job['recovery'])


@pytest.mark.parametrize('epoch2', [False, True])
def test_operator_exhausted_never_dispatches_and_replays_after_ledger_completion(
    setup, monkeypatch, legacy_dependencies, epoch2
):
    client, store, binding, artifacts, legacy, alternate, _ = terminal_setup(setup, monkeypatch, legacy_dependencies)
    old = historical(client, epoch2=epoch2)
    module = load_operator()
    key = module.fingerprint(row(client))
    assert module.inspect_unit(store, artifacts, 'bad', binding.owner_id, key, True) == 'no_recoverable_speech'
    for _ in range(2):
        assert module.apply_one(
            store,
            artifacts,
            'bad',
            binding.owner_id,
            key,
            'no_recoverable_speech',
            'plan',
            True,
            None,
            server_flags=SERVING_ENV,
        ) in {'completed', 'already_applied'}
    assert row(client)['recovery'] == old
    assert row(client)['result']['outcome'] == 'no_recoverable_speech'
    ledger = client.rows[('users', binding.owner_id, 'sync_content_ledger', binding.content_id)]
    ledger.update(status='completed')
    assert (
        module.apply_one(
            store,
            artifacts,
            'bad',
            binding.owner_id,
            key,
            'no_recoverable_speech',
            'plan',
            True,
            None,
            server_flags=SERVING_ENV,
        )
        == 'already_applied'
    )
    alternate.assert_not_called()
    legacy.assert_not_called()


@pytest.mark.parametrize('speech', [False, True])
def test_gpu_canary_vad_routes_without_resetting_spent_intent(setup, monkeypatch, legacy_dependencies, speech):
    client, store, binding, artifacts, legacy, alternate, _ = terminal_setup(setup, monkeypatch, legacy_dependencies)
    old = historical(client, canary=True)
    monkeypatch.setattr(
        legacy_dependencies[1], 'offline_pcm_speech_segments', lambda _: [{'start': 1, 'end': 2}] if speech else []
    )
    module = load_operator()
    key = module.fingerprint(row(client))
    decision = module.inspect_unit(store, artifacts, 'bad', binding.owner_id, key, True)
    assert decision == ('canary_recovery' if speech else 'silence')
    assert module.apply_one(
        store, artifacts, 'bad', binding.owner_id, key, decision, 'plan', True, 2, server_flags=SERVING_ENV
    ) in {
        'completed',
        'recovered',
    }
    assert row(client)['recovery'] == old
    assert row(client)['result']['outcome'] == ('no_recoverable_speech' if speech else 'silence')
    assert (
        module.apply_one(
            store, artifacts, 'bad', binding.owner_id, key, decision, 'plan', True, 2, server_flags=SERVING_ENV
        )
        == 'already_applied'
    )
    assert alternate.call_count == int(speech)
    legacy.assert_not_called()


def test_canary_recovery_success_keeps_real_words(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, _, alternate, _ = terminal_setup(setup, monkeypatch, legacy_dependencies)
    historical(client, canary=True)
    alternate.return_value = ([{'text': 'Synthetic.', 'timestamp': [1, 2]}], 'vi')
    module = load_operator()
    key = module.fingerprint(row(client))
    assert (
        module.apply_one(
            store, artifacts, 'bad', binding.owner_id, key, 'canary_recovery', 'plan', True, 2, server_flags=SERVING_ENV
        )
        == 'recovered'
    )
    assert row(client)['result']['outcome'] == 'success'
    assert row(client)['ready_at'] > 0  # Re-entry restarts the bounded merge head wait.
    alternate.assert_called_once()


@pytest.mark.parametrize(
    'change', ['flag', 'owner', 'privacy', 'lease', 'result', 'receipt', 'intent', 'plan', 'timeout']
)
def test_operator_fences_reject_without_provider(setup, monkeypatch, legacy_dependencies, change):
    client, store, binding, artifacts, _, alternate, _ = terminal_setup(setup, monkeypatch, legacy_dependencies)
    historical(client)
    module = load_operator()
    key = module.fingerprint(row(client))
    if change == 'flag':
        monkeypatch.delenv('BATCH_PIPELINE_TERMINAL_EMPTY_DISPOSITION_ENABLED')
    elif change == 'owner':
        monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST', 'other')
    elif change == 'privacy':
        row(client)['privacy_generation'] = 1
    elif change == 'lease':
        row(client)['lease_until'] = 1e12
    elif change == 'result':
        row(client)['result'] = {'outcome': 'success'}
    elif change == 'receipt':
        client.rows[('batch_pipeline_prod_results', 'bad')] = {'projection': {'state': 'ready'}}
    elif change == 'intent':
        row(client)['recovery']['token'] = 'changed'
    elif change == 'timeout':
        row(client)['recovery']['failure']['reason'] = 'provider_failed'
        key = module.fingerprint(row(client))
    else:
        TerminalEmptyStore(store, server_flags=SERVING_ENV).prepare(
            'bad', binding.owner_id, 'other', intent_snapshot(row(client)), 'no_recoverable_speech', True, 99
        )
    with pytest.raises((ProjectionBlocked, BatchPrivacyBlocked, module.held.Refused)):
        module.apply_one(
            store,
            artifacts,
            'bad',
            binding.owner_id,
            key,
            'no_recoverable_speech',
            'plan',
            True,
            None,
            server_flags=SERVING_ENV,
        )
    alternate.assert_not_called()


def test_terminal_empty_releases_real_sibling_transcript_and_client_completion(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, _, _, _ = terminal_setup(setup, monkeypatch, legacy_dependencies)
    historical(client)
    module = load_operator()
    key = module.fingerprint(row(client))
    module.apply_one(
        store,
        artifacts,
        'bad',
        binding.owner_id,
        key,
        'no_recoverable_speech',
        'plan',
        True,
        None,
        server_flags=SERVING_ENV,
    )
    monkeypatch.setattr('database.batch_pipeline_store.first_pending', lambda *args, **kwargs: deepcopy(row(client)))
    entry = OrderedMerge(store).commit_next(binding.owner_id, 101)
    assert entry['recovery_version'] == 1 and entry['result']['outcome'] == 'no_recoverable_speech'
    from utils.batch_pipeline.projection import Projector

    *_, fair_use, llm_usage, hourly_usage_updates = legacy_dependencies
    monkeypatch.setattr(llm_usage, 'resolve_usage_plan_id', lambda *args, **kwargs: 'synthetic-plan')
    monkeypatch.setattr(hourly_usage_updates, 'prepare_hourly_usage_updates', lambda *args, **kwargs: {})
    monkeypatch.setattr(fair_use, 'record_speech_ms', Mock())
    monkeypatch.setattr('utils.batch_pipeline.retention.expire_completed_segment', lambda *args: True)
    publish = Mock()
    payload = terminal_empty_payload(5, [{'start': 1, 'end': 2}])
    projector = Projector(store, lambda *args: payload, publish=publish, clock=lambda: 102)
    result = projector.project('bad')
    assert result['no_recoverable_speech_segments'] == 1 and result['outcome'] == 'success'
    assert row(client, 'results', 'good')['projection_state'] == 'completed'
    assert row(client, sid='good')['client_status'] == row(client)['client_status'] == 'completed'
    assert result['failed_segments'] == 0
    assert row(client, 'results', 'bad')['projection']['speech_seconds'] == 0
    publish.assert_called_once()
    assert projector.project('bad') == result


def test_digest_binds_attestation_canary_epoch_owner_and_decision():
    module = load_operator()
    units = [('synthetic', 'key', 'no_recoverable_speech')]
    digest = module.plan_digest('owner', 1, units, True, None)
    assert digest != module.plan_digest('owner', 1, units, False, None)
    assert digest != module.plan_digest('owner', 1, units, True, 2)
    assert digest != module.plan_digest('other', 1, units, True, None)
    assert digest != module.plan_digest('owner', 1, [('synthetic', 'key', 'silence')], True, None)


def test_operator_dry_run_is_read_only_and_calls_no_provider(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, legacy, alternate, _ = terminal_setup(setup, monkeypatch, legacy_dependencies)
    historical(client)
    module = load_operator()
    before = deepcopy(client.rows)
    assert (
        module.inspect_unit(store, artifacts, 'bad', binding.owner_id, module.fingerprint(row(client)), True)
        == 'no_recoverable_speech'
    )
    assert client.rows == before
    artifacts.persist_recovery_result.assert_not_called()
    legacy.assert_not_called()
    alternate.assert_not_called()


def test_canary_paid_authorization_is_required_before_any_write(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, legacy, alternate, _ = terminal_setup(setup, monkeypatch, legacy_dependencies)
    historical(client, canary=True)
    module = load_operator()
    before = deepcopy(client.rows)
    with pytest.raises(module.held.Refused):
        module.apply_one(
            store,
            artifacts,
            'bad',
            binding.owner_id,
            module.fingerprint(row(client)),
            'canary_recovery',
            'plan',
            True,
            None,
            server_flags=SERVING_ENV,
        )
    assert client.rows == before
    legacy.assert_not_called()
    alternate.assert_not_called()


def test_operator_storage_loss_reconciles_and_counts_terminal_once(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, _, alternate, _ = terminal_setup(setup, monkeypatch, legacy_dependencies)
    historical(client)
    module = load_operator()
    import database.batch_pipeline_terminal_empty as protocol

    meter = Mock()
    monkeypatch.setattr(protocol, 'record_correctness', meter)
    key = module.fingerprint(row(client))
    artifacts.persist_recovery_result.side_effect = TimeoutError('PRIVATE_SENTINEL')
    with pytest.raises(TimeoutError):
        module.apply_one(
            store,
            artifacts,
            'bad',
            binding.owner_id,
            key,
            'no_recoverable_speech',
            'plan',
            True,
            None,
            server_flags=SERVING_ENV,
        )
    assert row(client)['terminal_disposition']['state'] == 'prepared'
    artifacts.find_recovery_result.return_value = 'gs://synthetic/reconciled'
    artifacts.load_result.return_value = terminal_empty_payload(5, [{'start': 1, 'end': 2}])
    for _ in range(2):
        assert module.apply_one(
            store,
            artifacts,
            'bad',
            binding.owner_id,
            key,
            'no_recoverable_speech',
            'plan',
            True,
            None,
            server_flags=SERVING_ENV,
        ) in {'completed', 'already_applied'}
    meter.assert_called_once_with('no_recoverable_speech', seconds=5)
    alternate.assert_not_called()


def test_nonpaid_artifact_requires_current_token_and_recorded_disposition(setup, monkeypatch, legacy_dependencies):
    from utils.batch_pipeline.retention import register_batch_artifact

    client, store, binding, _, _, _, old = terminal_setup(setup, monkeypatch, legacy_dependencies)
    historical(client)
    protocol = TerminalEmptyStore(store, server_flags=SERVING_ENV)
    job = protocol.prepare(
        'bad', binding.owner_id, 'plan', intent_snapshot(row(client)), 'no_recoverable_speech', True, 100
    )
    token = job['terminal_disposition']['token']
    assert token != old['token']
    uri = f'gs://synthetic/results/bad/{token}.enc'
    register_batch_artifact(store, binding.owner_id, 'bad', uri, 'results', 0)
    with pytest.raises(BatchPrivacyBlocked):
        register_batch_artifact(
            store, binding.owner_id, 'bad', f"gs://synthetic/results/bad/{old['token']}.enc", 'results', 0
        )
    monkeypatch.delenv('BATCH_PIPELINE_TERMINAL_EMPTY_DISPOSITION_ENABLED')
    register_batch_artifact(store, binding.owner_id, 'bad', uri, 'results', 0)
    with pytest.raises(BatchPrivacyBlocked):
        register_batch_artifact(
            store, binding.owner_id, 'bad', f"gs://synthetic/results/bad/{old['token']}.enc", 'results', 0
        )


def test_worker_proof_survives_the_real_lease_cas_and_unknown_failures_do_not_gain_it():
    from tests.unit.test_batch_pipeline_scheduler import MemoryStore
    from utils.batch_pipeline.scheduler import Scheduler
    from utils.batch_pipeline.contracts import WorkItem, Priority

    store = MemoryStore()
    scheduler = Scheduler(store)
    for sid, proof in [('empty', True), ('unknown', False)]:
        scheduler.enqueue(WorkItem(sid, 'synthetic', 1, 'gs://synthetic/audio', 5, Priority.FRESH), 0)
        lease = scheduler.pull(1)[0]
        assert not scheduler.fail(sid, 'foreign', 2, quarantine=True, padded_retry_empty=True)
        assert scheduler.fail(sid, lease.token, 2, quarantine=True, padded_retry_empty=proof)
        job = store.run(lambda tx: tx.get('jobs', sid))
        assert bool(job.get('worker_empty_evidence')) == proof


@pytest.mark.parametrize(
    'duration,expected_recovery_outcome,expected_state,expected_result_outcome',
    [
        (10, 'recovered', 'result_ready', 'no_recoverable_speech'),
        (117, 'failed_held', 'quarantined', None),
    ],
)
def test_skipped_oversized_padded_retry_does_not_terminal_complete_empty_recovery(
    setup,
    monkeypatch,
    legacy_dependencies,
    duration,
    expected_recovery_outcome,
    expected_state,
    expected_result_outcome,
):
    from types import SimpleNamespace
    import numpy as np
    from diarizer.batch_pipeline_models import ParakeetWords
    from tests.unit.test_batch_pipeline_worker import setup_worker, item
    from utils.batch_pipeline.scheduler import Scheduler, owner_key

    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    client, store, binding, artifacts, legacy, alternate, _ = terminal_setup(setup, monkeypatch, legacy_dependencies)
    model = Mock()
    model.transcribe.side_effect = lambda arrays, **_: [
        SimpleNamespace(text='', timestamp={'word': []}) for _ in arrays
    ]
    provider = ParakeetWords(model)
    worker, *_ = setup_worker(
        decode=lambda work: np.ones(int(work.duration_seconds * 16000), dtype=np.float32),
        words_providers={'parakeet': provider},
        recover_words=provider.recover_empty,
    )
    worker_results = worker.process_batch([item('bad', duration)])
    assert len(worker_results) == 1
    job = row(client)
    job.pop('recovery', None)
    job.pop('worker_empty_evidence', None)
    job.update(
        duration_seconds=duration,
        owner_key=owner_key(binding.owner_id),
        attempt=1,
        state='leased',
        token='worker-lease',
        lease_until=1000.0,
        merge_pending=True,
    )
    artifacts.fetch_audio.return_value = wav(duration)
    scheduler = Scheduler(store)
    assert scheduler.fail(
        'bad',
        'worker-lease',
        10,
        quarantine=True,
        padded_retry_empty=worker_results[0].padded_retry_empty,
        padded_retry=worker_results[0].padded_retry,
    )
    recovery = setup[-1]
    recovery.stt = transcribe
    assert recovery.recover('bad', binding.owner_id) == expected_recovery_outcome
    job = row(client)
    assert job['state'] == expected_state
    assert (job.get('result') or {}).get('outcome') == expected_result_outcome
    alternate.assert_called_once()
    legacy.assert_not_called()
    if duration == 117:
        assert job['recovery_state'] == 'failed_held'
        assert job['worker_empty_evidence'] == {'padded_retry': 'skipped_oversize', 'version': 1}
        from database.batch_pipeline_speech_redrive import SpeechRedriveStore

        with pytest.raises(ProjectionBlocked):
            SpeechRedriveStore(store, server_flags=SERVING_ENV).prepare(
                'bad', binding.owner_id, 'plan', job['recovery'], 101, gpu_padded_retry_empty=True
            )
        with pytest.raises(ProjectionBlocked):
            TerminalEmptyStore(store, server_flags=SERVING_ENV).prepare(
                'bad', binding.owner_id, 'plan', intent_snapshot(job), 'no_recoverable_speech', True, 101
            )
        module = load_operator()
        with pytest.raises(module.held.Refused):
            module.inspect_unit(store, artifacts, 'bad', binding.owner_id, module.fingerprint(job), True)


def test_skipped_oversized_padded_retry_still_recovers_when_multilingual_succeeds(
    setup, monkeypatch, legacy_dependencies
):
    from types import SimpleNamespace
    import numpy as np
    from diarizer.batch_pipeline_models import ParakeetWords
    from tests.unit.test_batch_pipeline_worker import setup_worker, item
    from utils.batch_pipeline.scheduler import Scheduler, owner_key

    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    client, store, binding, artifacts, legacy, alternate, _ = terminal_setup(setup, monkeypatch, legacy_dependencies)
    alternate.return_value = ([{'text': 'Recovered.', 'timestamp': [1.0, 2.0]}], 'en')
    model = Mock()
    model.transcribe.side_effect = lambda arrays, **_: [
        SimpleNamespace(text='', timestamp={'word': []}) for _ in arrays
    ]
    provider = ParakeetWords(model)
    worker, *_ = setup_worker(
        decode=lambda work: np.ones(int(work.duration_seconds * 16000), dtype=np.float32),
        words_providers={'parakeet': provider},
        recover_words=provider.recover_empty,
    )
    worker_results = worker.process_batch([item('bad', 117)])
    job = row(client)
    job.pop('recovery', None)
    job.pop('worker_empty_evidence', None)
    job.update(
        duration_seconds=117,
        owner_key=owner_key(binding.owner_id),
        attempt=1,
        state='leased',
        token='worker-lease',
        lease_until=1000.0,
        merge_pending=True,
    )
    artifacts.fetch_audio.return_value = wav(117)
    assert Scheduler(store).fail(
        'bad',
        'worker-lease',
        10,
        quarantine=True,
        padded_retry_empty=worker_results[0].padded_retry_empty,
        padded_retry=worker_results[0].padded_retry,
    )
    recovery = setup[-1]
    recovery.stt = transcribe
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    assert row(client)['state'] == 'result_ready'
    assert row(client)['result']['outcome'] == 'success'
    assert row(client)['ready_at'] > 0  # Re-entry restarts the bounded merge head wait.
    alternate.assert_called_once()
    legacy.assert_not_called()


@pytest.mark.parametrize('empty', [True, False])
def test_paid_epoch_meters_cap_audio_only_for_recognized_speech(setup, monkeypatch, legacy_dependencies, empty):
    from types import SimpleNamespace
    from utils.batch_pipeline import speech_redrive

    client, store, binding, artifacts, _, alternate, old = terminal_setup(setup, monkeypatch, legacy_dependencies)
    if not empty:
        alternate.return_value = ([{'text': 'Synthetic.', 'timestamp': [1, 2], 'speaker': 'SPEAKER_00'}], 'vi')
    monkeypatch.setattr(speech_redrive, 'sync_allowed', lambda *args, **kwargs: True)
    monkeypatch.setattr(speech_redrive, 'cap_enabled', lambda uid, lane: True)
    monkeypatch.setattr(speech_redrive, 'funded_allowance', lambda *args, **kwargs: SimpleNamespace(reason='managed'))
    meter = Mock()
    monkeypatch.setattr(speech_redrive, 'record_audio', meter)
    assert (
        speech_redrive.redrive_one(
            store, artifacts, 'bad', binding.owner_id, 'plan', old, server_flags=SERVING_ENV, clock=lambda: 100
        )
        == 'recovered'
    )
    assert row(client)['result']['outcome'] == ('no_recoverable_speech' if empty else 'success')
    # A terminal-empty span meters zero speech, matching the automatic recovery path.
    assert meter.call_count == int(not empty)
    alternate.assert_called_once()
