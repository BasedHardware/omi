"""Long unknown-language speech gets one second multilingual call before it is held."""

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.unit.test_batch_pipeline_quarantine_recovery import setup, legacy_dependencies, row
from tests.unit.test_batch_pipeline_terminal_empty import terminal_setup
from utils.batch_pipeline import quarantine_recovery as module
from utils.batch_pipeline.recovery_recognizers import transcribe
from utils.batch_pipeline.recovery_disposition import (
    RecoveryFailure,
    TWO_PROVIDER_EMPTY_EVIDENCE,
    LANGUAGE_GUARD_EMPTY_EVIDENCE,
    result_outcome,
    terminal_empty_payload,
)

WORDS = [{'text': 'Synthetic.', 'timestamp': [1, 2], 'speaker': 'SPEAKER_00'}]


def second_setup(setup, monkeypatch, legacy_dependencies, *, soniox=None, speech=(0, 5)):
    client, _, binding, artifacts, legacy, alternate, _ = terminal_setup(setup, monkeypatch, legacy_dependencies)
    pre_recorded, vad, *_ = legacy_dependencies
    monkeypatch.setattr(vad, 'offline_pcm_speech_segments', lambda _: [{'start': speech[0], 'end': speech[1]}])
    second = soniox or Mock(return_value=([], 'en'))
    monkeypatch.setenv('SONIOX_API_KEY', 'synthetic-only-key')
    monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED', 'true')
    from utils.stt import soniox_batch

    monkeypatch.setattr(soniox_batch, 'transcribe', second)
    # Long-speech recovery stays disabled; simulate its existing hook while
    # language-guard recovery independently admits the real Soniox adapter.
    monkeypatch.setattr(module, 'SECOND_PROVIDER', 'soniox')
    job = row(client)
    job.pop('recovery')
    job['recovery_state'] = 'held'
    job['worker_empty_evidence'] = {'padded_retry': 'skipped_long_speech', 'version': 1}
    recovery = setup[-1]
    recovery.stt = transcribe
    return client, binding, artifacts, alternate, second, recovery


def test_retired_second_provider_never_dispatches(setup, monkeypatch, legacy_dependencies, caplog):
    """With HELD_RECOVERY_SECOND_PROVIDER None (Deepgram retired), no second call happens."""
    client, binding, artifacts, alternate, second, recovery = second_setup(setup, monkeypatch, legacy_dependencies)
    monkeypatch.setattr(module, 'SECOND_PROVIDER', None)
    assert module.second_provider_eligible({}, SimpleNamespace(spans=[{'start': 0, 'end': 9}], duration=9)) is False
    assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    second.assert_not_called()


def test_both_providers_empty_settles_terminal_empty_with_evidence(setup, monkeypatch, legacy_dependencies, caplog):
    caplog.set_level('INFO')
    client, binding, artifacts, alternate, second, recovery = second_setup(setup, monkeypatch, legacy_dependencies)
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    job = row(client)
    assert job['result']['outcome'] == 'no_recoverable_speech'
    assert job['recovery']['provider'] == 'modulate'
    payload = artifacts.persist_recovery_result.call_args.args[1]
    assert result_outcome(payload) == 'no_recoverable_speech'
    assert payload['recognition_evidence'] == TWO_PROVIDER_EMPTY_EVIDENCE
    assert payload['words'] == [] and payload['speech_seconds'] == 5
    assert 'event=batch_recovery_second_provider provider=soniox outcome=empty' in caplog.text
    assert 'reason=no_recoverable_speech' in caplog.text
    # One call each, no client retries, and nothing more on later sweeps.
    for _ in range(2):
        assert recovery.recover('bad', binding.owner_id) == 'held'
    alternate.assert_called_once()
    second.assert_called_once()
    assert second.call_args.args[1] == 5
    assert second.call_args.kwargs == {}


def test_second_provider_words_recover_the_unit(setup, monkeypatch, legacy_dependencies, caplog):
    caplog.set_level('INFO')
    soniox = Mock(return_value=(WORDS, 'vi'))
    client, binding, artifacts, alternate, second, recovery = second_setup(
        setup, monkeypatch, legacy_dependencies, soniox=soniox
    )
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    payload = artifacts.persist_recovery_result.call_args.args[1]
    assert result_outcome(payload) == 'success'
    assert payload['language'] == 'vi' and [w['word'] for w in payload['words']] == ['Synthetic.']
    assert row(client)['result']['outcome'] == 'success'
    assert 'provider=soniox outcome=words' in caplog.text
    alternate.assert_called_once()
    second.assert_called_once()


@pytest.mark.parametrize('error', [TimeoutError('PRIVATE_SENTINEL'), ('malformed',)])
def test_second_provider_error_stays_failed_held(setup, monkeypatch, legacy_dependencies, caplog, error):
    caplog.set_level('INFO')
    soniox = Mock(side_effect=error) if isinstance(error, Exception) else Mock(return_value=error)
    client, binding, artifacts, _, second, recovery = second_setup(
        setup, monkeypatch, legacy_dependencies, soniox=soniox
    )
    assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    job = row(client)
    assert job['recovery']['failure'] == {'stage': 'response_validation', 'reason': 'empty_asr'}
    assert not job.get('result')
    artifacts.persist_recovery_result.assert_not_called()
    assert 'provider=soniox outcome=error' in caplog.text
    assert 'PRIVATE_SENTINEL' not in caplog.text
    assert recovery.recover('bad', binding.owner_id) == 'held'
    second.assert_called_once()


@pytest.mark.parametrize('missing', ['kill_switch', 'evidence', 'speech', 'terminal_flag', 'allowance'])
def test_second_provider_requires_its_preconditions(setup, monkeypatch, legacy_dependencies, missing):
    client, binding, _, _, second, recovery = second_setup(
        setup, monkeypatch, legacy_dependencies, speech=(0, 4.9) if missing == 'speech' else (0, 5)
    )
    if missing == 'kill_switch':
        monkeypatch.setenv('BATCH_PIPELINE_SECOND_MULTILINGUAL_ENABLED', 'false')
    elif missing == 'evidence':
        row(client)['worker_empty_evidence'] = {'padded_retry': 'skipped_oversize', 'version': 1}
    elif missing == 'terminal_flag':
        monkeypatch.delenv('BATCH_PIPELINE_TERMINAL_EMPTY_DISPOSITION_ENABLED')
    elif missing == 'allowance':
        monkeypatch.setattr(module, 'sync_allowed', Mock(side_effect=[True, False]))
    assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    assert not row(client).get('result')
    if missing == 'terminal_flag':
        second.assert_called_once()  # Words could still recover it; two empties stay held.
    else:
        second.assert_not_called()


def test_padded_empty_units_never_spend_a_second_call(setup, monkeypatch, legacy_dependencies):
    client, binding, _, _, second, recovery = second_setup(setup, monkeypatch, legacy_dependencies)
    row(client)['worker_empty_evidence'] = {'padded_retry': 'empty', 'version': 1}
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    assert row(client)['result']['outcome'] == 'no_recoverable_speech'
    second.assert_not_called()


@pytest.mark.parametrize('guard_enabled', ['true', 'false'])
@pytest.mark.parametrize('answer,outcome', [([], 'failed_held'), (WORDS, 'recovered')])
def test_language_guard_uses_two_multilingual_providers_without_fabricating_parakeet_empty(
    setup, monkeypatch, legacy_dependencies, answer, outcome, guard_enabled
):
    client, binding, artifacts, alternate, second, recovery = second_setup(
        setup, monkeypatch, legacy_dependencies, soniox=Mock(return_value=(answer, 'vi')), speech=(0, 1)
    )
    job = row(client)
    job.pop('worker_empty_evidence')
    job['worker_failure'] = {'stage': 'vad_windows', 'reason': 'unsupported_language'}
    monkeypatch.setenv('STT_PRERECORDED_LANGUAGE_GUARD_ENABLED', guard_enabled)
    monkeypatch.setenv('BATCH_PIPELINE_SPEECH_EMPTY_MULTILINGUAL_ENABLED', 'false')
    assert recovery.recover('bad', binding.owner_id) == outcome
    alternate.assert_called_once()
    second.assert_called_once()
    job = row(client)
    assert job['recovery']['provider'] == 'modulate'
    receipt = job['recovery']['recognizers']['soniox']
    assert receipt['word_count'] == len(answer) and receipt['vad_speech_seconds'] == 1
    if answer:
        assert job['result']['outcome'] == 'success'
    else:
        assert not job.get('result')
        assert job['measured_held_vad_speech_seconds'] == 1


@pytest.mark.parametrize('answer,outcome', [([], 'no_recoverable_speech'), (WORDS, 'success')])
def test_both_paid_calls_are_billed(setup, monkeypatch, legacy_dependencies, answer, outcome):
    soniox = Mock(return_value=(answer, 'vi'))
    client, binding, _, _, _, recovery = second_setup(setup, monkeypatch, legacy_dependencies, soniox=soniox)
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setattr(module, 'sync_allowed', Mock(return_value=True))
    monkeypatch.setattr(module, 'funded_allowance', Mock(return_value=SimpleNamespace(managed=True, reason='funded')))
    meter = Mock()
    monkeypatch.setattr(module, 'record_audio', meter)
    before = {
        result: module.SECOND_PROVIDER_CALLS.labels('soniox', result)._value.get() for result in ('empty', 'words')
    }
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    assert row(client)['result']['outcome'] == outcome
    assert [c.args for c in meter.call_args_list] == [
        ('sync', 'accepted', 'modulate', 5, False),
        ('sync', 'accepted', 'soniox', 5, False),
    ]
    counted = 'empty' if outcome == 'no_recoverable_speech' else 'words'
    assert module.SECOND_PROVIDER_CALLS.labels('soniox', counted)._value.get() == before[counted] + 1
    # The extra call rechecks the batch allowance against its own provider.
    assert module.sync_allowed.call_args.args[:3] == (binding.owner_id, 5, 'soniox')


def test_metering_failure_never_changes_the_disposition(setup, monkeypatch, legacy_dependencies):
    client, binding, _, _, _, recovery = second_setup(setup, monkeypatch, legacy_dependencies)
    monkeypatch.setattr(module, 'record_accepted', Mock(side_effect=RuntimeError('PRIVATE_SENTINEL')))
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    assert row(client)['result']['outcome'] == 'no_recoverable_speech'


def test_success_metering_failure_keeps_the_first_transcript(setup, monkeypatch, legacy_dependencies):
    client, binding, _, alternate, second, recovery = second_setup(setup, monkeypatch, legacy_dependencies)
    alternate.return_value = (WORDS, 'vi')
    monkeypatch.setattr(module, 'record_accepted', Mock(side_effect=RuntimeError('PRIVATE_SENTINEL')))
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    assert row(client)['result']['outcome'] == 'success'
    second.assert_not_called()


# Privacy cancels the intent; anything else raised by the provider is a provider failure.
@pytest.mark.parametrize(
    'raised,result', [('privacy', 'cancelled'), ('projection', 'failed_held'), ('allowance', 'failed_held')]
)
def test_second_provider_fences_never_settle_terminal_empty(setup, monkeypatch, legacy_dependencies, raised, result):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked
    from database.batch_pipeline_projection_protocol import ProjectionBlocked

    error = {'privacy': BatchPrivacyBlocked, 'projection': ProjectionBlocked}.get(raised)
    soniox = Mock(side_effect=error('synthetic')) if error else None
    client, binding, artifacts, _, second, recovery = second_setup(
        setup, monkeypatch, legacy_dependencies, soniox=soniox
    )
    if raised == 'allowance':
        monkeypatch.setattr(module, 'sync_allowed', Mock(side_effect=[True, RuntimeError('PRIVATE_SENTINEL')]))
    assert recovery.recover('bad', binding.owner_id) == result
    assert not row(client).get('result')
    artifacts.persist_recovery_result.assert_not_called()
    if raised == 'allowance':
        second.assert_not_called()


@pytest.mark.parametrize('change', ['first_only', 'missing_second', 'second_not_empty'])
def test_two_provider_evidence_rejects_fabrication(change, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    payload = terminal_empty_payload(5, [{'start': 0, 'end': 5}], TWO_PROVIDER_EMPTY_EVIDENCE)
    assert result_outcome(payload) == 'no_recoverable_speech'
    evidence = payload['recognition_evidence']
    if change == 'first_only':
        evidence['gpu_padded_retry'] = 'skipped_oversize'
    elif change == 'missing_second':
        evidence.pop('second_multilingual_recovery')
    else:
        evidence['second_multilingual_recovery'] = 'timeout'
    with pytest.raises(RecoveryFailure):
        result_outcome(payload)
