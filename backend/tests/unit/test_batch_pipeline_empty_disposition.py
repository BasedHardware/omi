"""Dark empty-output repair: real recovery, privacy, assignment and upload completion."""

from copy import deepcopy
from dataclasses import fields, replace
import importlib.util
import io
import os
from pathlib import Path
from unittest.mock import Mock
import wave

import pytest

from tests.unit.test_batch_pipeline_quarantine_recovery import setup, legacy_dependencies, row
from utils.batch_pipeline.contracts import WorkItem, RecoveryWork
from utils.batch_pipeline.quarantine_recovery import transcribe
from utils.batch_pipeline.recovery_disposition import inspect_audio, RecoveryFailure, silence_payload
from database.batch_pipeline_quarantine_recovery import SilenceDispositionStore
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from tests.unit.test_batch_pipeline_worker import setup_worker, item
from diarizer import batch_pipeline
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.scheduler import owner_key

# Operator stores take the serving role's settings explicitly. These tests model
# them with the fixtures' synthetic env (a live mapping, so per-test edits apply).
SERVING_ENV = os.environ


@pytest.fixture(scope='module', autouse=True)
def worker_dependencies():
    # Importing the worker harness belongs to setup, outside the call CPU budget.
    from tests.unit.test_batch_pipeline_worker import setup_worker, item
    from diarizer import batch_pipeline


def wav(seconds=5):
    out = io.BytesIO()
    with wave.open(out, 'wb') as handle:
        handle.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        handle.writeframes(b'\0' * (seconds * 32000))
    return out.getvalue()


def work(client):
    job = row(client)
    return WorkItem(**{f.name: job[f.name] for f in fields(WorkItem) if f.name in job})


def enable(monkeypatch, legacy_dependencies, *, speech=False):
    pre_recorded, vad, *_ = legacy_dependencies
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'true')
    monkeypatch.setattr(vad, 'offline_pcm_speech_segments', lambda _: [{'start': 1, 'end': 2}] if speech else [])
    provider = Mock(return_value=([{'text': 'Synthetic.', 'timestamp': [1, 2], 'speaker': 'SPEAKER_00'}], 'en'))
    monkeypatch.setattr(pre_recorded, 'prerecorded_from_bytes', provider)
    return provider


def test_dark_default_rejects_no_speech_without_provider(setup, monkeypatch, legacy_dependencies):
    client, _, binding, *_ = setup
    provider = enable(monkeypatch, legacy_dependencies)
    monkeypatch.delenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED')
    with pytest.raises(RecoveryFailure) as failure:
        transcribe(work(client), binding, wav())
    assert (failure.value.stage, failure.value.reason) == ('strict_vad', 'no_speech')
    provider.assert_not_called()


def test_strict_silence_is_success_without_provider_and_releases_siblings(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, _, recovery = setup
    provider = enable(monkeypatch, legacy_dependencies)
    artifacts.fetch_audio.return_value = wav()
    recovery.stt = transcribe
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    provider.assert_not_called()
    assert row(client)['result']['outcome'] == 'silence'
    monkeypatch.setattr('database.batch_pipeline_store.first_pending', lambda *args, **kwargs: deepcopy(row(client)))
    entry = OrderedMerge(store).commit_next(binding.owner_id, 101)
    assert entry['late_capture'] and entry['result']['outcome'] == 'silence'
    from utils.batch_pipeline.projection import Projector

    *_, fair_use, llm_usage, hourly_usage_updates = legacy_dependencies
    monkeypatch.setattr(llm_usage, 'resolve_usage_plan_id', lambda *args, **kwargs: 'synthetic-plan')
    monkeypatch.setattr(hourly_usage_updates, 'prepare_hourly_usage_updates', lambda *args, **kwargs: {})
    monkeypatch.setattr(fair_use, 'record_speech_ms', Mock())
    monkeypatch.setattr('utils.batch_pipeline.retention.expire_completed_segment', lambda *args, **kwargs: True)
    publish = Mock()
    projector = Projector(store, Mock(), publish=publish, clock=lambda: 102)
    assert projector.project('bad')['outcome'] == 'expected_silence'
    assert row(client, 'results', 'good')['projection_state'] == 'completed'
    assert row(client, sid='good')['client_status'] == 'completed'
    assert row(client)['client_status'] == 'completed'
    assert publish.call_count == 1
    assert projector.project('bad')['outcome'] == 'expected_silence'
    provider.assert_not_called()


def test_speech_uses_one_fenced_attempt_then_holds(setup, monkeypatch, legacy_dependencies):
    client, _, binding, artifacts, _, recovery = setup
    provider = enable(monkeypatch, legacy_dependencies, speech=True)
    provider.return_value = ([], 'en')
    artifacts.fetch_audio.return_value = wav()
    recovery.stt = transcribe
    assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    assert row(client)['recovery']['failure'] == {'stage': 'response_validation', 'reason': 'empty_asr'}
    for _ in range(3):
        assert recovery.recover('bad', binding.owner_id) == 'held'
    assert provider.call_count == 1 and provider.call_args.kwargs['attempts'] == 2


def test_speech_second_attempt_recovers_real_words(setup, monkeypatch, legacy_dependencies):
    client, _, binding, artifacts, _, recovery = setup
    provider = enable(monkeypatch, legacy_dependencies, speech=True)
    artifacts.fetch_audio.return_value = wav()
    recovery.stt = transcribe
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    assert row(client)['result']['outcome'] == 'success'
    payload = artifacts.persist_recovery_result.call_args.args[1]
    assert payload['speech_seconds'] == 1 and payload['recovery_version'] == 1
    assert provider.call_count == 1


@pytest.mark.parametrize(
    'phase,expected',
    [
        ('audio', ('audio_validation', 'invalid_audio')),
        ('vad', ('strict_vad', 'vad_failed')),
        ('bad_vad', ('strict_vad', 'invalid_vad')),
        ('provider', ('provider', 'provider_failed')),
        ('response', ('response_validation', 'invalid_response')),
        ('empty', ('response_validation', 'empty_asr')),
    ],
)
def test_closed_failure_stage_reason_never_contains_private_error(
    setup, monkeypatch, legacy_dependencies, caplog, phase, expected
):
    client, _, binding, artifacts, _, recovery = setup
    provider = enable(monkeypatch, legacy_dependencies, speech=True)
    _, vad, *_ = legacy_dependencies
    private = 'PRIVATE_AUDIO_URI_TOKEN_TRANSCRIPT_SENTINEL'
    artifacts.fetch_audio.return_value = b'bad' if phase == 'audio' else wav()
    if phase == 'vad':
        monkeypatch.setattr(vad, 'offline_pcm_speech_segments', Mock(side_effect=RuntimeError(private)))
    if phase == 'bad_vad':
        monkeypatch.setattr(vad, 'offline_pcm_speech_segments', lambda _: [{'start': 3, 'end': 1}])
    if phase == 'provider':
        provider.side_effect = RuntimeError(private)
    if phase == 'response':
        provider.return_value = private
    if phase == 'empty':
        provider.return_value = ([], 'en')
    recovery.stt = transcribe
    assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    failure = row(client)['recovery']['failure']
    assert (failure['stage'], failure['reason']) == expected
    assert private not in caplog.text
    assert 'event=batch_recovery_failure' in caplog.text


def spent(client):
    job = row(client)
    job.update(
        recovery_state='failed_held',
        recovery={'token': 'a' * 32, 'privacy_generation': 0, 'started_at': 1, 'settled_at': 2},
    )
    return deepcopy(job['recovery'])


def test_operator_silence_preserves_paid_intent_and_replay_is_once(setup, monkeypatch, legacy_dependencies):
    client, store, binding, _, stt, _ = setup
    enable(monkeypatch, legacy_dependencies)
    old = spent(client)
    protocol = SilenceDispositionStore(store, server_flags=SERVING_ENV)
    job = protocol.prepare_silence('bad', binding.owner_id, 'plan', 100)
    token = job['silence_disposition']['token']
    assert token != old['token'] and row(client)['recovery'] == old
    assert protocol.prepare_silence('bad', binding.owner_id, 'plan', 101)['silence_disposition']['token'] == token
    assert protocol.complete_silence('bad', token, 'plan', 'gs://synthetic/silence', 102)
    assert row(client)['recovery'] == old and row(client)['result']['outcome'] == 'silence'
    revision = client.rows[
        (
            'batch_pipeline_prod_owners',
            owner_key(binding.owner_id),
        )
    ]['revision']
    assert protocol.complete_silence('bad', token, 'plan', 'gs://synthetic/silence', 103)
    assert (
        client.rows[
            (
                'batch_pipeline_prod_owners',
                owner_key(binding.owner_id),
            )
        ]['revision']
        == revision
    )
    stt.assert_not_called()


@pytest.mark.parametrize(
    'change', ['off', 'owner', 'lease', 'result', 'receipt', 'generation', 'deleted', 'other_plan']
)
def test_operator_fences_refuse_mutation(setup, monkeypatch, legacy_dependencies, change):
    client, store, binding, _, _, _ = setup
    enable(monkeypatch, legacy_dependencies)
    spent(client)
    if change == 'off':
        monkeypatch.delenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED')
    if change == 'owner':
        row(client)['owner_id'] = 'foreign'
    if change == 'lease':
        row(client)['lease_until'] = 1000
    if change == 'result':
        row(client)['result'] = {'outcome': 'success'}
    if change == 'receipt':
        client.rows[('batch_pipeline_prod_results', 'bad')] = {'projection': {'state': 'ready'}}
    if change == 'generation':
        row(client)['privacy_generation'] = 1
    if change == 'deleted':
        client.rows[('account_deletions', binding.owner_id)] = {'wipe_status': 'completed'}
    if change == 'other_plan':
        row(client)['silence_disposition'] = {'plan_digest': 'another'}
    before = deepcopy(client.rows)
    with pytest.raises((ProjectionBlocked, BatchPrivacyBlocked)):
        SilenceDispositionStore(store, server_flags=SERVING_ENV).prepare_silence('bad', binding.owner_id, 'plan', 100)
    assert client.rows == before


def test_no_owned_words_without_silence_evidence_is_not_silence(monkeypatch):

    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED', 'false')

    class OutsideCore:
        def transcribe_batch(self, samples):
            return [[{'word': 'Synthetic', 'timestamp': [1, 1.1]}] for _ in samples]

    # Restrict window ownership without making a semantic no-speech claim.
    original = batch_pipeline.speech_windows

    monkeypatch.setattr(
        batch_pipeline, 'speech_windows', lambda *args: [replace(w, core_end=0.5) for w in original(*args)]
    )
    worker, _, saved, *_ = setup_worker(words_providers={'parakeet': OutsideCore()}, recover_words=lambda *_: [])
    result = worker.process_batch([item()])
    assert result == [RecoveryWork('a', padded_retry_empty=True, reason='no_owned_words')] and not saved


def test_operator_replay_after_durable_upload_completion_does_not_need_live_run(
    setup, monkeypatch, legacy_dependencies
):
    client, store, binding, _, _, _ = setup
    enable(monkeypatch, legacy_dependencies)
    spent(client)
    protocol = SilenceDispositionStore(store, server_flags=SERVING_ENV)
    job = protocol.prepare_silence('bad', binding.owner_id, 'plan', 100)
    token = job['silence_disposition']['token']
    assert protocol.complete_silence('bad', token, 'plan', 'gs://synthetic/silence', 102)
    ledger = client.rows[('users', binding.owner_id, 'sync_content_ledger', binding.content_id)]
    ledger['status'] = 'completed'
    snapshot = deepcopy(client.rows)
    assert protocol.complete_silence('bad', token, 'plan', 'gs://synthetic/silence', 103)
    assert protocol.prepare_silence('bad', binding.owner_id, 'plan', 104)['silence_disposition']['token'] == token
    assert client.rows == snapshot


def load_operator():
    path = Path(__file__).parents[2] / 'scripts' / 'batch_pipeline_held_disposition.py'
    spec = importlib.util.spec_from_file_location('held_disposition_operator', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_operator_dry_run_uses_read_only_transactions_and_never_flushes(monkeypatch):
    from types import SimpleNamespace
    from google.cloud import firestore
    from database import batch_pipeline_store

    module = load_operator()
    client, view = Mock(), Mock()
    view.writes = {}
    monkeypatch.setattr(firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(batch_pipeline_store, 'FirestoreTransaction', Mock(return_value=view))
    assert (
        module.readonly_run(SimpleNamespace(client=client, namespace='batch_pipeline_prod'), lambda tx: 'silent')
        == 'silent'
    )
    client.transaction.assert_called_once_with(read_only=True)
    view.flush.assert_not_called()


def test_operator_digest_binds_owner_classification_and_immutable_metadata():
    module = load_operator()
    units = [('synthetic-unit', 'immutable-key', 'silent')]
    first = module.plan_digest('owner', 'batch_pipeline_prod', 100, units)
    assert first == module.plan_digest('owner', 'batch_pipeline_prod', 100, list(reversed(units)))
    assert first != module.plan_digest('foreign', 'batch_pipeline_prod', 100, units)
    assert first != module.plan_digest(
        'owner', 'batch_pipeline_prod', 100, [('synthetic-unit', 'immutable-key', 'speech')]
    )
    assert first != module.plan_digest(
        'owner', 'batch_pipeline_prod', 100, [('synthetic-unit', 'changed-key', 'silent')]
    )


def test_operator_speech_census_never_calls_provider_or_writes(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, stt, _ = setup
    provider = enable(monkeypatch, legacy_dependencies, speech=True)
    spent(client)
    artifacts.fetch_audio.return_value = wav()
    module = load_operator()
    # The strict fixture does not accept the read_only keyword; adapt only the transaction constructor.
    transaction = client.transaction
    monkeypatch.setattr(client, 'transaction', lambda **kwargs: transaction())
    snapshot = deepcopy(client.rows)
    assert module.inspect_unit(store, artifacts, 'bad', binding.owner_id, module.fingerprint(row(client))) == 'speech'
    assert client.rows == snapshot
    stt.assert_not_called()
    provider.assert_not_called()
    artifacts.persist_recovery_result.assert_not_called()


def test_silence_does_not_require_paid_allowance(setup, monkeypatch, legacy_dependencies):
    client, _, binding, artifacts, _, recovery = setup
    provider = enable(monkeypatch, legacy_dependencies)
    artifacts.fetch_audio.return_value = wav()
    recovery.stt = transcribe
    monkeypatch.setattr('utils.batch_pipeline.quarantine_recovery.sync_allowed', lambda *args, **kwargs: False)
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    provider.assert_not_called()


def test_payload_validation_has_closed_failure_stage(setup, monkeypatch, legacy_dependencies):
    client, _, binding, artifacts, _, recovery = setup
    enable(monkeypatch, legacy_dependencies, speech=True)
    artifacts.fetch_audio.return_value = wav()
    recovery.stt = transcribe
    monkeypatch.setattr(
        'utils.batch_pipeline.quarantine_recovery.projection_speech_spans',
        Mock(side_effect=ValueError('PRIVATE_SENTINEL')),
    )
    assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    assert row(client)['recovery']['failure'] == {'stage': 'payload_validation', 'reason': 'invalid_payload'}


def test_silent_artifact_lost_reply_reconciles_as_silence_without_paid_stt(setup, monkeypatch, legacy_dependencies):
    client, _, binding, artifacts, _, recovery = setup
    provider = enable(monkeypatch, legacy_dependencies)
    artifacts.fetch_audio.return_value = wav()
    recovery.stt = transcribe
    artifacts.persist_recovery_result.side_effect = TimeoutError('PRIVATE_SENTINEL')
    assert recovery.recover('bad', binding.owner_id) == 'result_held'
    artifacts.find_recovery_result.return_value = 'gs://synthetic/silence'
    artifacts.load_result.return_value = silence_payload(5)
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'false')
    assert recovery.recover('bad', binding.owner_id) == 'reconciled'
    assert row(client)['result']['outcome'] == 'silence'
    provider.assert_not_called()


def test_operator_lost_upload_reply_reconciles_without_touching_paid_intent(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, stt, _ = setup
    provider = enable(monkeypatch, legacy_dependencies)
    old = spent(client)
    artifacts.fetch_audio.return_value = wav()
    module = load_operator()
    transaction = client.transaction
    monkeypatch.setattr(client, 'transaction', lambda **kwargs: transaction())
    key = module.fingerprint(row(client))
    artifacts.persist_recovery_result.side_effect = TimeoutError('PRIVATE_SENTINEL')
    with pytest.raises(TimeoutError):
        module.apply_silent(store, artifacts, 'bad', binding.owner_id, key, 'plan', server_flags=SERVING_ENV)
    token = row(client)['silence_disposition']['token']
    assert row(client)['recovery'] == old and row(client)['state'] == 'quarantined'
    artifacts.find_recovery_result.return_value = 'gs://synthetic/silence'
    artifacts.load_result.return_value = silence_payload(5)
    assert (
        module.apply_silent(store, artifacts, 'bad', binding.owner_id, key, 'plan', server_flags=SERVING_ENV)
        == 'applied_silence'
    )
    assert row(client)['silence_disposition']['token'] == token
    assert module.fingerprint(row(client)) == key and row(client)['recovery'] == old
    assert (
        module.apply_silent(store, artifacts, 'bad', binding.owner_id, key, 'plan', server_flags=SERVING_ENV)
        == 'already_applied'
    )
    assert artifacts.persist_recovery_result.call_count == 1
    stt.assert_not_called()
    provider.assert_not_called()


def test_operator_artifact_registration_accepts_only_its_new_token(setup, monkeypatch, legacy_dependencies):
    from utils.batch_pipeline.retention import register_batch_artifact

    client, store, binding, _, _, _ = setup
    enable(monkeypatch, legacy_dependencies)
    old = spent(client)
    prepared = SilenceDispositionStore(store, server_flags=SERVING_ENV).prepare_silence(
        'bad', binding.owner_id, 'plan', 100
    )
    token = prepared['silence_disposition']['token']
    uri = f'gs://synthetic/results/bad/{token}.enc'
    register_batch_artifact(store, binding.owner_id, 'bad', uri, 'results', 0)
    with pytest.raises(BatchPrivacyBlocked):
        register_batch_artifact(
            store, binding.owner_id, 'bad', f"gs://synthetic/results/bad/{old['token']}.enc", 'results', 0
        )
    assert row(client)['recovery'] == old


def test_operator_respects_deleted_deterministic_candidate(setup, monkeypatch, legacy_dependencies):
    from utils.sync.capture import chunk_identity

    client, store, binding, _, _, _ = setup
    enable(monkeypatch, legacy_dependencies)
    spent(client)
    target = chunk_identity(
        binding.owner_id, binding.source, binding.client_device_id, binding.is_locked, row(client)['capture_at']
    )
    client.rows[('users', binding.owner_id, 'deleted_conversations', target)] = {'deleted': True}
    before = deepcopy(client.rows)
    with pytest.raises(BatchPrivacyBlocked):
        SilenceDispositionStore(store, server_flags=SERVING_ENV).prepare_silence('bad', binding.owner_id, 'plan', 100)
    assert client.rows == before
