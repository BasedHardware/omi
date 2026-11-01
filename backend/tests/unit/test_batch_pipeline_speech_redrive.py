"""Alternate multilingual dispatch and explicit, at-most-once paid epoch 2."""

from copy import deepcopy
from dataclasses import replace
from config.policy import resolve_batch_policy
import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest

from tests.unit.test_batch_pipeline_quarantine_recovery import setup, legacy_dependencies, row
from tests.unit.test_batch_pipeline_empty_disposition import wav, work, enable, SERVING_ENV
from database.batch_pipeline_speech_redrive import SpeechRedriveStore
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from utils.batch_pipeline.recovery_recognizers import transcribe
from utils.batch_pipeline.recovery_disposition import RecoveryFailure
from utils.batch_pipeline.speech_redrive import redrive_one


def enabled(setup, monkeypatch, legacy_dependencies):
    monkeypatch.setenv('STT_CAP_OFFLINE_ENFORCEMENT', 'false')
    client, store, binding, artifacts, _, _ = setup
    legacy = enable(monkeypatch, legacy_dependencies, speech=True)
    monkeypatch.setenv('BATCH_PIPELINE_SPEECH_EMPTY_MULTILINGUAL_ENABLED', 'true')
    monkeypatch.setenv('MODULATE_API_KEY', 'synthetic-key')
    pre_recorded, *_ = legacy_dependencies
    alternate = Mock(return_value=([{'text': 'Synthetic.', 'timestamp': [1, 2], 'speaker': 'SPEAKER_00'}], 'vi'))
    monkeypatch.setattr(pre_recorded, 'modulate_prerecorded_from_bytes', alternate, raising=False)
    job = row(client)
    job.update(
        recovery_state='failed_held',
        recovery={'epoch': 1, 'token': 'a' * 32, 'privacy_generation': 0, 'started_at': 1, 'settled_at': 2},
    )
    artifacts.fetch_audio.return_value = wav()
    artifacts.load_result.return_value = {'words': [{'word': 'Synthetic.'}]}
    return client, store, binding, artifacts, legacy, alternate, deepcopy(job['recovery'])


def test_dark_flag_keeps_existing_provider(setup, monkeypatch, legacy_dependencies):
    client, _, binding, _, legacy, alternate, _ = enabled(setup, monkeypatch, legacy_dependencies)
    monkeypatch.delenv('BATCH_PIPELINE_SPEECH_EMPTY_MULTILINGUAL_ENABLED')
    transcribe(work(client), binding, wav())
    legacy.assert_called_once()
    alternate.assert_not_called()


def test_fresh_speech_uses_exactly_one_independent_provider(setup, monkeypatch, legacy_dependencies):
    client, _, binding, _, legacy, alternate, _ = enabled(setup, monkeypatch, legacy_dependencies)
    payload = transcribe(work(client), binding, wav(), multilingual=True)
    assert payload['language'] == 'vi' and payload['words']
    assert alternate.call_count == 1 and alternate.call_args.kwargs['attempts'] == 2
    legacy.assert_not_called()


def test_silence_never_calls_either_provider(setup, monkeypatch, legacy_dependencies):
    client, _, binding, _, legacy, alternate, _ = enabled(setup, monkeypatch, legacy_dependencies)
    _, vad, *_ = legacy_dependencies
    monkeypatch.setattr(vad, 'offline_pcm_speech_segments', lambda _: [])
    assert transcribe(work(client), binding, wav())['outcome'] == 'silence'
    legacy.assert_not_called()
    alternate.assert_not_called()


def test_paid_epoch_preserves_original_and_replays_without_dispatch(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, legacy, alternate, old = enabled(setup, monkeypatch, legacy_dependencies)
    assert (
        redrive_one(store, artifacts, 'bad', binding.owner_id, 'plan', old, server_flags=SERVING_ENV, clock=lambda: 100)
        == 'recovered'
    )
    job = row(client)
    assert job['recovery'] == old and job['speech_redrive']['prior_recovery'] == old
    assert job['speech_redrive']['paid_epoch'] == 2
    assert job['speech_redrive']['token'] != old['token']
    assert job['result']['outcome'] == 'success' and job['merge_pending']
    assert (
        redrive_one(store, artifacts, 'bad', binding.owner_id, 'plan', old, server_flags=SERVING_ENV, clock=lambda: 101)
        == 'already_applied'
    )
    alternate.assert_called_once()
    legacy.assert_not_called()


def test_empty_alternate_is_terminal_without_a_third_call(setup, monkeypatch, legacy_dependencies, caplog):
    client, store, binding, artifacts, legacy, alternate, old = enabled(setup, monkeypatch, legacy_dependencies)
    alternate.return_value = ([], 'vi')
    for _ in range(3):
        assert (
            redrive_one(
                store, artifacts, 'bad', binding.owner_id, 'plan', old, server_flags=SERVING_ENV, clock=lambda: 100
            )
            == 'failed_held'
        )
    assert row(client)['speech_redrive']['failure'] == {'stage': 'response_validation', 'reason': 'empty_asr'}
    assert row(client)['recovery'] == old
    alternate.assert_called_once()
    legacy.assert_not_called()


def test_uncertain_call_stays_held_and_reconciles_only_artifact(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, _, alternate, old = enabled(setup, monkeypatch, legacy_dependencies)
    artifacts.persist_recovery_result.side_effect = RuntimeError('PRIVATE_SENTINEL')
    with pytest.raises(RuntimeError):
        redrive_one(store, artifacts, 'bad', binding.owner_id, 'plan', old, server_flags=SERVING_ENV, clock=lambda: 100)
    assert row(client)['speech_redrive']['state'] == 'running'
    assert (
        redrive_one(store, artifacts, 'bad', binding.owner_id, 'plan', old, server_flags=SERVING_ENV, clock=lambda: 101)
        == 'running_held'
    )
    artifacts.find_recovery_result.return_value = 'gs://synthetic/reconciled'
    assert (
        redrive_one(store, artifacts, 'bad', binding.owner_id, 'plan', old, server_flags=SERVING_ENV, clock=lambda: 102)
        == 'reconciled'
    )
    alternate.assert_called_once()


def test_concurrent_start_is_cas_and_prepared_replay_reuses_token(setup, monkeypatch, legacy_dependencies):
    client, store, binding, _, _, alternate, old = enabled(setup, monkeypatch, legacy_dependencies)
    protocol = SpeechRedriveStore(store, server_flags=SERVING_ENV)
    token = protocol.prepare('bad', binding.owner_id, 'plan', old, 100)['speech_redrive']['token']
    assert protocol.prepare('bad', binding.owner_id, 'plan', old, 101)['speech_redrive']['token'] == token
    assert protocol.start('bad', token, 'plan', 102)
    assert not protocol.start('bad', token, 'plan', 102)
    alternate.assert_not_called()


@pytest.mark.parametrize(
    'change', ['flag', 'owner', 'lease', 'result', 'receipt', 'privacy', 'silent', 'different_plan', 'old_intent']
)
def test_operator_fences_before_paid_call(setup, monkeypatch, legacy_dependencies, change):
    client, store, binding, artifacts, legacy, alternate, old = enabled(setup, monkeypatch, legacy_dependencies)
    protocol = SpeechRedriveStore(store, server_flags=SERVING_ENV)
    if change == 'flag':
        monkeypatch.delenv('BATCH_PIPELINE_SPEECH_EMPTY_MULTILINGUAL_ENABLED')
    elif change == 'owner':
        monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST', 'other-owner')
    elif change == 'lease':
        row(client)['lease_until'] = 1000
    elif change == 'result':
        row(client)['result'] = {'outcome': 'success'}
    elif change == 'receipt':
        client.rows[('batch_pipeline_prod_results', 'bad')] = {'projection_state': 'ready'}
    elif change == 'privacy':
        row(client)['privacy_generation'] = 1
    elif change == 'silent':
        row(client)['silence_disposition'] = {'state': 'prepared'}
    elif change == 'different_plan':
        protocol.prepare('bad', binding.owner_id, 'other-plan', old, 99)
    elif change == 'old_intent':
        row(client)['recovery']['token'] = 'b' * 32
    try:
        result = redrive_one(
            store, artifacts, 'bad', binding.owner_id, 'plan', old, server_flags=SERVING_ENV, clock=lambda: 100
        )
        assert result == 'disabled'
    except (ProjectionBlocked, BatchPrivacyBlocked):
        pass
    legacy.assert_not_called()
    alternate.assert_not_called()


def test_digest_binds_paid_epoch_provider_operation_and_census():
    spec = importlib.util.spec_from_file_location(
        'operator', Path(__file__).parents[2] / 'scripts/batch_pipeline_speech_redrive.py'
    )
    module = importlib.util.module_from_spec(spec)
    # Script imports its adjacent permanent census module, as on the CLI.
    import sys

    sys.path.insert(0, str(Path(__file__).parents[2] / 'scripts'))
    spec.loader.exec_module(module)
    digest = module.paid_digest('original-census', 67, 2)
    assert digest == module.paid_digest('original-census', 67, 2)
    assert digest != module.paid_digest('changed-census', 67, 2)
    assert digest != module.paid_digest('original-census', 66, 2)
    assert digest != module.paid_digest('original-census', 67, 3)


def test_dry_run_reports_closed_epoch1_failures_of_payable_units():
    spec = importlib.util.spec_from_file_location(
        'operator', Path(__file__).parents[2] / 'scripts/batch_pipeline_speech_redrive.py'
    )
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.path.insert(0, str(Path(__file__).parents[2] / 'scripts'))
    spec.loader.exec_module(module)
    failure = lambda stage, reason: {'recovery': {'failure': {'stage': stage, 'reason': reason}}}
    assert module.epoch1_failure(failure('response_validation', 'empty_asr')) == 'response_validation/empty_asr'
    # Non-empty failures are payable too; the approver must be able to see them.
    assert module.epoch1_failure(failure('provider', 'abandoned_running')) == 'provider/abandoned_running'
    # Pre-telemetry rows and anything outside the closed vocabulary never echo raw text.
    assert module.epoch1_failure({'recovery': {}}) == 'unrecorded'
    assert module.epoch1_failure({}) == 'unrecorded'
    assert module.epoch1_failure(failure('provider', 'raw provider body')) == 'unrecorded'


def test_artifact_write_requires_running_epoch2_token(setup, monkeypatch, legacy_dependencies):
    from utils.batch_pipeline.retention import register_batch_artifact

    client, store, binding, _, _, _, old = enabled(setup, monkeypatch, legacy_dependencies)
    protocol = SpeechRedriveStore(store, server_flags=SERVING_ENV)
    token = protocol.prepare('bad', binding.owner_id, 'plan', old, 100)['speech_redrive']['token']
    uri = f'gs://synthetic/results/bad/{token}.enc'
    with pytest.raises(BatchPrivacyBlocked):
        register_batch_artifact(store, binding.owner_id, 'bad', uri, 'results', 0)
    assert protocol.start('bad', token, 'plan', 101)
    register_batch_artifact(store, binding.owner_id, 'bad', uri, 'results', 0)
    with pytest.raises(BatchPrivacyBlocked):
        register_batch_artifact(
            store, binding.owner_id, 'bad', f"gs://synthetic/results/bad/{old['token']}.enc", 'results', 0
        )


def test_completed_upload_replay_uses_receipt_without_live_ledger_run(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, _, alternate, old = enabled(setup, monkeypatch, legacy_dependencies)
    assert (
        redrive_one(store, artifacts, 'bad', binding.owner_id, 'plan', old, server_flags=SERVING_ENV, clock=lambda: 100)
        == 'recovered'
    )
    ledger = client.rows[('users', binding.owner_id, 'sync_content_ledger', binding.content_id)]
    ledger['status'] = 'completed'
    snapshot = deepcopy(client.rows)
    assert (
        redrive_one(store, artifacts, 'bad', binding.owner_id, 'plan', old, server_flags=SERVING_ENV, clock=lambda: 101)
        == 'already_applied'
    )
    assert client.rows == snapshot
    alternate.assert_called_once()


def test_partial_upload_keeps_the_reviewed_paid_redrive(setup, monkeypatch, legacy_dependencies):
    import sys

    from database.batch_pipeline_projection import ProjectionStore

    client, store, binding, artifacts, legacy, alternate, old = enabled(setup, monkeypatch, legacy_dependencies)
    accounting = {'seconds': 3, 'source': 'sync_fresh', 'updates': {}, 'hour': 'h', 'completed': False}
    assert ProjectionStore(store).complete_partial(binding, 99, accounting)[0]['held_segments'] == 1
    ledger = client.rows[('users', binding.owner_id, 'sync_content_ledger', binding.content_id)]
    assert ledger['status'] == 'partial' and ledger['usage_committed_at'] is not None
    sys.path.insert(0, str(Path(__file__).parents[2] / 'scripts'))
    spec = importlib.util.spec_from_file_location(
        'speech_operator_partial', Path(__file__).parents[2] / 'scripts/batch_pipeline_speech_redrive.py'
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    key = module.held.fingerprint(row(client))
    transaction = client.transaction
    monkeypatch.setattr(client, 'transaction', lambda **kwargs: transaction())
    # The census still admits the held unit: the partial charged only its siblings.
    assert module.inspect_unit(store, artifacts, 'bad', binding.owner_id, key) == 'speech'
    # A completed upload still refuses it (the ownership fence answers first).
    ledger['status'] = 'completed'
    with pytest.raises((module.held.Refused, ProjectionBlocked)):
        module.inspect_unit(store, artifacts, 'bad', binding.owner_id, key)
    ledger['status'] = 'partial'
    assert (
        redrive_one(store, artifacts, 'bad', binding.owner_id, 'plan', old, server_flags=SERVING_ENV, clock=lambda: 100)
        == 'recovered'
    )
    assert row(client)['result']['outcome'] == 'success' and row(client)['merge_pending']
    alternate.assert_called_once()
    legacy.assert_not_called()


def test_positive_vad_with_empty_local_hypothesis_reproduces_fast_closed_failure(
    setup, monkeypatch, legacy_dependencies
):
    import time

    client, _, binding, _, legacy, alternate, _ = enabled(setup, monkeypatch, legacy_dependencies)
    monkeypatch.delenv('BATCH_PIPELINE_SPEECH_EMPTY_MULTILINGUAL_ENABLED')
    legacy.return_value = ([], 'en')
    started = time.monotonic()
    with pytest.raises(RecoveryFailure) as error:
        transcribe(work(client), binding, wav())
    assert (error.value.stage, error.value.reason) == ('response_validation', 'empty_asr')
    assert time.monotonic() - started < 2
    alternate.assert_not_called()


def test_operator_readonly_census_preserves_all_state(setup, monkeypatch, legacy_dependencies):
    import sys

    client, store, binding, artifacts, legacy, alternate, _ = enabled(setup, monkeypatch, legacy_dependencies)
    sys.path.insert(0, str(Path(__file__).parents[2] / 'scripts'))
    spec = importlib.util.spec_from_file_location(
        'speech_operator', Path(__file__).parents[2] / 'scripts/batch_pipeline_speech_redrive.py'
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    transaction = client.transaction
    seen = []

    def readonly(**kwargs):
        seen.append(kwargs)
        return transaction()

    monkeypatch.setattr(client, 'transaction', readonly)
    before = deepcopy(client.rows)
    key = module.held.fingerprint(row(client))
    assert module.inspect_unit(store, artifacts, 'bad', binding.owner_id, key) == 'speech'
    assert seen and all(item == {'read_only': True} for item in seen)
    assert client.rows == before
    artifacts.persist_recovery_result.assert_not_called()
    legacy.assert_not_called()
    alternate.assert_not_called()


def test_allowance_and_deleted_target_fence_epoch2(setup, monkeypatch, legacy_dependencies):
    from utils.sync.capture import chunk_identity

    client, store, binding, artifacts, _, alternate, old = enabled(setup, monkeypatch, legacy_dependencies)
    monkeypatch.setattr('utils.batch_pipeline.speech_redrive.sync_allowed', lambda *args, **kwargs: False)
    assert (
        redrive_one(store, artifacts, 'bad', binding.owner_id, 'plan', old, server_flags=SERVING_ENV, clock=lambda: 100)
        == 'allowance_held'
    )
    assert row(client)['speech_redrive']['state'] == 'prepared'
    target = chunk_identity(
        binding.owner_id, binding.source, binding.client_device_id, binding.is_locked, row(client)['capture_at']
    )
    client.rows[('users', binding.owner_id, 'deleted_conversations', target)] = {'deleted': True}
    monkeypatch.setattr('utils.batch_pipeline.speech_redrive.sync_allowed', lambda *args, **kwargs: True)
    with pytest.raises(BatchPrivacyBlocked):
        redrive_one(store, artifacts, 'bad', binding.owner_id, 'plan', old, server_flags=SERVING_ENV, clock=lambda: 100)
    alternate.assert_not_called()


def test_paid_epoch_attributes_provider_audio_to_modulate(setup, monkeypatch, legacy_dependencies):
    from types import SimpleNamespace
    from utils.batch_pipeline import speech_redrive

    _, store, binding, artifacts, _, alternate, old = enabled(setup, monkeypatch, legacy_dependencies)
    monkeypatch.setattr(speech_redrive, 'sync_allowed', lambda *args, **kwargs: True)
    monkeypatch.setattr(speech_redrive, 'cap_enabled', lambda uid, lane: True)
    monkeypatch.setattr(speech_redrive, 'funded_allowance', lambda *args, **kwargs: SimpleNamespace(reason='managed'))
    meter = Mock()
    monkeypatch.setattr(speech_redrive, 'record_audio', meter)
    assert (
        redrive_one(store, artifacts, 'bad', binding.owner_id, 'plan', old, server_flags=SERVING_ENV, clock=lambda: 100)
        == 'recovered'
    )
    meter.assert_called_once_with('sync', 'accepted', 'modulate', 5, False)
    alternate.assert_called_once()


@pytest.mark.parametrize('access', ['capped', 'byok', 'reviewer', 'paid', 'kill_off'])
def test_default_on_speech_redrive_does_not_buy_unfunded_recovery(setup, monkeypatch, legacy_dependencies, access):
    from types import SimpleNamespace
    from utils import stt_cap_dispatch as cap

    client, store, binding, artifacts, legacy, alternate, old = enabled(setup, monkeypatch, legacy_dependencies)
    monkeypatch.setenv('STT_CAP_OFFLINE_ENFORCEMENT', 'false' if access == 'kill_off' else 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false')
    if access == 'byok':
        row(client)['policy'] = {'provider_reason': 'byok'}
    resolver = Mock(
        return_value=SimpleNamespace(managed=access in {'reviewer', 'paid'}, reason='plan_allowance_exhausted')
    )
    monkeypatch.setattr(cap, 'funded_allowance', resolver)
    result = redrive_one(
        store, artifacts, 'bad', binding.owner_id, 'plan', old, server_flags=SERVING_ENV, clock=lambda: 100
    )
    assert alternate.call_count == (0 if access == 'capped' else 1)
    legacy.assert_not_called()
    if access == 'capped':
        assert result == 'allowance_held' and row(client)['speech_redrive']['state'] == 'prepared'
    if access in {'byok', 'kill_off'}:
        resolver.assert_not_called()
