"""Modulate-empty held speech gets one fenced Soniox second chance."""

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
    job = row(client)
    job.pop('recovery')
    job['recovery_state'] = 'held'
    job['worker_empty_evidence'] = {'padded_retry': 'skipped_long_speech', 'version': 1}
    recovery = setup[-1]
    recovery.stt = transcribe
    return client, binding, artifacts, alternate, second, recovery


def test_unnamed_second_provider_never_dispatches(setup, monkeypatch, legacy_dependencies, caplog):
    """Removing the policy provider prevents dispatch."""
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
    assert set(payload['recognizer_receipts']) == {'modulate', 'soniox'}
    assert all(r['outcome'] == 'empty' for r in row(client)['recovery']['recognizers'].values())
    assert 'event=batch_recovery_second_provider provider=soniox outcome=empty' in caplog.text
    assert 'reason=no_recoverable_speech' in caplog.text
    # One call each, no client retries, and nothing more on later sweeps.
    for _ in range(2):
        assert recovery.recover('bad', binding.owner_id) == 'held'
    alternate.assert_called_once()
    second.assert_called_once()
    assert second.call_args.args[1] == 5
    assert second.call_args.kwargs == {'second_chance': True}


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


@pytest.mark.parametrize('status,expected', [(503, 'recovered'), (402, 'failed_held')])
def test_real_adapter_retries_before_settlement_and_keeps_credit_refusal_held(
    setup, monkeypatch, legacy_dependencies, caplog, status, expected
):
    from utils.stt import soniox_batch
    from tests.unit.test_soniox_recovery_retry import provider
    from tests.unit.test_soniox_batch import client as client_factory

    transcribe_http = soniox_batch.transcribe
    handler, calls = provider('upload', 2 if status == 503 else 100, status)
    second = Mock(
        side_effect=lambda audio, duration, **kwargs: transcribe_http(
            audio, duration, **kwargs, client_factory=client_factory(handler), sleep=lambda _: None
        )
    )
    client, binding, artifacts, _, _, recovery = second_setup(setup, monkeypatch, legacy_dependencies, soniox=second)
    assert recovery.recover('bad', binding.owner_id) == expected
    job = row(client)
    assert job['recovery']['recognizers']['soniox']['outcome'] == ('words' if status == 503 else 'error')
    if status == 402:
        assert not job.get('result')
        assert job['measured_held_vad_speech_seconds'] == 5
        artifacts.persist_recovery_result.assert_not_called()
        assert 'kind=credit_refusal http_status=402' in caplog.text
    assert calls['upload'] == (3 if status == 503 else 1)
    assert calls['create'] == (1 if status == 503 else 0)
    assert recovery.recover('bad', binding.owner_id) == 'held'
    second.assert_called_once()


@pytest.mark.parametrize('missing', ['kill_switch', 'terminal_flag', 'allowance', 'missing_key'])
def test_second_provider_requires_its_preconditions(setup, monkeypatch, legacy_dependencies, missing):
    client, binding, _, _, second, recovery = second_setup(setup, monkeypatch, legacy_dependencies)
    if missing == 'kill_switch':
        monkeypatch.setenv('BATCH_PIPELINE_SECOND_MULTILINGUAL_ENABLED', 'false')
    elif missing == 'missing_key':
        monkeypatch.delenv('SONIOX_API_KEY')
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


@pytest.mark.parametrize('evidence', [None, 'skipped_oversize'])
@pytest.mark.parametrize('words', [False, True])
def test_short_or_validation_hold_gets_second_chance_without_guard_flag(
    setup, monkeypatch, legacy_dependencies, evidence, words
):
    from utils.batch_pipeline.recovery_disposition import SECOND_CHANCE_EMPTY_EVIDENCE

    client, binding, artifacts, _, second, recovery = second_setup(
        setup,
        monkeypatch,
        legacy_dependencies,
        soniox=Mock(return_value=(WORDS if words else [], 'vi')),
        speech=(1, 2),
    )
    monkeypatch.delenv('BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED')
    monkeypatch.delenv('BATCH_PIPELINE_SECOND_MULTILINGUAL_ENABLED', raising=False)
    if evidence is None:
        row(client).pop('worker_empty_evidence')
        row(client)['worker_failure'] = {'stage': 'word_clocks', 'reason': 'word_clock'}
    else:
        row(client)['worker_empty_evidence']['padded_retry'] = evidence
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    second.assert_called_once()
    receipts = row(client)['recovery']['recognizers']
    assert receipts['modulate']['outcome'] == 'empty'
    assert receipts['soniox']['outcome'] == ('words' if words else 'empty')
    payload = artifacts.persist_recovery_result.call_args.args[1]
    if not words:
        assert payload['recognition_evidence'] == SECOND_CHANCE_EMPTY_EVIDENCE
        assert payload['recognizer_receipts'] == receipts
        payload['recognizer_receipts'].pop('modulate')
        with pytest.raises(RecoveryFailure):
            result_outcome(payload)


def test_default_safety_net_keeps_two_empty_answers_held(setup, monkeypatch, legacy_dependencies):
    client, binding, artifacts, _, second, recovery = second_setup(setup, monkeypatch, legacy_dependencies)
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    second.assert_called_once()
    assert row(client)['recovery']['recognizers']['soniox']['outcome'] == 'empty'
    artifacts.persist_recovery_result.assert_not_called()


def test_two_recognizer_close_switch_settles_two_empty_answers_under_the_safety_net(
    setup, monkeypatch, legacy_dependencies, caplog
):
    caplog.set_level('INFO')
    client, binding, artifacts, alternate, second, recovery = second_setup(setup, monkeypatch, legacy_dependencies)
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_TWO_RECOGNIZER_EMPTY_CLOSE_ENABLED', 'true')
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    job = row(client)
    assert job['result']['outcome'] == 'no_recoverable_speech'
    assert all(r['outcome'] == 'empty' for r in job['recovery']['recognizers'].values())
    payload = artifacts.persist_recovery_result.call_args.args[1]
    assert result_outcome(payload) == 'no_recoverable_speech'
    assert payload['recognition_evidence'] == TWO_PROVIDER_EMPTY_EVIDENCE
    assert payload['words'] == [] and payload['speech_seconds'] == 5
    assert set(payload['recognizer_receipts']) == {'modulate', 'soniox'}
    assert 'reason=no_recoverable_speech' in caplog.text
    # Still one paid call each, and nothing more on later sweeps.
    assert recovery.recover('bad', binding.owner_id) == 'held'
    alternate.assert_called_once()
    second.assert_called_once()


@pytest.mark.parametrize('error', [TimeoutError('synthetic'), ('malformed',)])
def test_two_recognizer_close_switch_needs_a_validated_second_empty_answer(
    setup, monkeypatch, legacy_dependencies, error
):
    soniox = Mock(side_effect=error) if isinstance(error, Exception) else Mock(return_value=error)
    client, binding, artifacts, _, second, recovery = second_setup(
        setup, monkeypatch, legacy_dependencies, soniox=soniox
    )
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_TWO_RECOGNIZER_EMPTY_CLOSE_ENABLED', 'true')
    assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    assert not row(client).get('result')
    artifacts.persist_recovery_result.assert_not_called()
    second.assert_called_once()


def test_two_recognizer_close_switch_leaves_the_language_guard_held(setup, monkeypatch, legacy_dependencies):
    client, binding, artifacts, _, second, recovery = second_setup(
        setup, monkeypatch, legacy_dependencies, soniox=Mock(return_value=([], 'vi')), speech=(0, 1)
    )
    job = row(client)
    job.pop('worker_empty_evidence')
    job['worker_failure'] = {'stage': 'vad_windows', 'reason': 'unsupported_language'}
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_TWO_RECOGNIZER_EMPTY_CLOSE_ENABLED', 'true')
    assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    second.assert_called_once()
    job = row(client)
    assert job['recovery']['recognizers']['soniox']['outcome'] == 'empty'
    assert not job.get('result')
    artifacts.persist_recovery_result.assert_not_called()


@pytest.fixture
def settlements(monkeypatch):
    from prometheus_client import CollectorRegistry, Counter
    from utils.batch_pipeline import correctness_metrics as metrics

    registry = CollectorRegistry()
    monkeypatch.setattr(
        metrics,
        'RECOGNIZER_OUTCOMES',
        Counter(
            'omi_batch_pipeline_recovery_recognizer_outcomes_total',
            '',
            ['modulate', 'soniox', 'speech', 'language_guarded', 'result'],
            registry=registry,
        ),
    )
    monkeypatch.setenv('BATCH_PIPELINE_CORRECTNESS_METRICS_ENABLED', 'true')

    def count(**labels):
        return registry.get_sample_value('omi_batch_pipeline_recovery_recognizer_outcomes_total', labels) or 0

    def total():
        return sum(
            sample.value for metric in registry.collect() for sample in metric.samples if sample.name.endswith('_total')
        )

    return count, total


@pytest.mark.parametrize('close', [False, True])
def test_settlement_counter_names_both_empty_answers_and_measured_speech(
    setup, monkeypatch, legacy_dependencies, settlements, close
):
    count, total = settlements
    client, binding, _, _, _, recovery = second_setup(setup, monkeypatch, legacy_dependencies)
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_TWO_RECOGNIZER_EMPTY_CLOSE_ENABLED', 'true' if close else 'false')
    result = 'no_recoverable_speech' if close else 'failed_held'
    assert recovery.recover('bad', binding.owner_id) == ('recovered' if close else 'failed_held')
    labels = dict(modulate='empty', soniox='empty', speech='2s_or_more', language_guarded='false', result=result)
    assert count(**labels) == 1
    # A later sweep settles nothing, so it reports nothing.
    assert recovery.recover('bad', binding.owner_id) == 'held'
    assert total() == 1


def test_settlement_counter_separates_a_second_recognizer_that_found_words(
    setup, monkeypatch, legacy_dependencies, settlements
):
    count, total = settlements
    soniox = Mock(return_value=(WORDS, 'en'))
    client, binding, _, _, _, recovery = second_setup(setup, monkeypatch, legacy_dependencies, soniox=soniox)
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    assert count(modulate='empty', soniox='words', speech='2s_or_more', language_guarded='false', result='words') == 1
    assert total() == 1


def test_settlement_counter_marks_the_language_guard_and_short_speech(
    setup, monkeypatch, legacy_dependencies, settlements
):
    count, total = settlements
    client, binding, _, _, _, recovery = second_setup(
        setup, monkeypatch, legacy_dependencies, soniox=Mock(return_value=([], 'vi')), speech=(0, 1)
    )
    job = row(client)
    job.pop('worker_empty_evidence')
    job['worker_failure'] = {'stage': 'vad_windows', 'reason': 'unsupported_language'}
    assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    labels = dict(modulate='empty', soniox='empty', speech='under_2s', language_guarded='true', result='failed_held')
    assert count(**labels) == 1
    assert total() == 1


def test_settlement_counter_is_closed_and_off_with_correctness_metrics(monkeypatch, settlements):
    from utils.batch_pipeline import correctness_metrics as metrics

    count, total = settlements
    assert [metrics.speech_bucket(v) for v in (None, True, float('nan'), -1, 0, 0.031, 0.032, 1.99, 2, 3600)] == [
        'unmeasured',
        'unmeasured',
        'unmeasured',
        'unmeasured',
        'none',
        'none',
        'under_2s',
        'under_2s',
        '2s_or_more',
        '2s_or_more',
    ]
    # Unknown receipt shapes and results fold into closed tokens and never raise.
    metrics.record_recovery_settlement({'modulate': {'outcome': 'surprise'}, 'soniox': 'bad'}, None, False, 'new')
    metrics.record_recovery_settlement(None, 3, True, 'silence')
    labels = dict(modulate='not_called', soniox='not_called', language_guarded='false', result='other')
    assert count(speech='unmeasured', **labels) == 1
    labels = dict(modulate='not_called', soniox='not_called', language_guarded='true', result='silence')
    assert count(speech='2s_or_more', **labels) == 1
    monkeypatch.setenv('BATCH_PIPELINE_CORRECTNESS_METRICS_ENABLED', 'false')
    metrics.record_recovery_settlement({}, 3, False, 'words')
    assert total() == 2


@pytest.mark.parametrize('words', [False, True])
def test_subsecond_worker_speech_hold_uses_second_chance_with_zero_cpu_vad(
    setup, monkeypatch, legacy_dependencies, words
):
    from utils.batch_pipeline.recovery_recognizers import canonical_wav
    from utils.batch_pipeline.contracts import vad_receipt

    answer = [{'text': 'Synthetic.', 'timestamp': [0.1, 0.3], 'speaker': 'SPEAKER_00'}] if words else []
    client, binding, artifacts, _, second, recovery = second_setup(
        setup,
        monkeypatch,
        legacy_dependencies,
        soniox=Mock(return_value=(answer, 'vi')),
    )
    job = row(client)
    job.pop('worker_empty_evidence')
    job.update(
        duration_seconds=0.5,
        worker_failure={'stage': 'word_clocks', 'reason': 'word_clock'},
        worker_vad_receipt=vad_receipt(job['audio_uri'], 8000, 0.1),
        measured_held_vad_speech_seconds=0.1,
    )
    artifacts.fetch_audio.return_value = canonical_wav(b'\0' * 16000)
    monkeypatch.setattr(legacy_dependencies[1], 'offline_pcm_speech_segments', lambda _: [])
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.delenv('BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED')
    assert recovery.recover('bad', binding.owner_id) == ('recovered' if words else 'failed_held')
    second.assert_called_once()
    assert row(client)['recovery']['recognizers']['soniox']['outcome'] == ('words' if words else 'empty')
    if words:
        payload = artifacts.persist_recovery_result.call_args.args[1]
        assert payload['speech_spans_source'] == 'worker_vad_word_clocks'
    else:
        artifacts.persist_recovery_result.assert_not_called()


def test_second_call_claim_precedes_spend_and_fences_privacy(setup, monkeypatch, legacy_dependencies):
    client, binding, _, _, second, recovery = second_setup(setup, monkeypatch, legacy_dependencies)

    def revoked(*args, **kwargs):
        from database.batch_pipeline_privacy import privacy_owner_key

        assert row(client)['recovery']['recognizers']['soniox']['outcome'] == 'started'
        client.rows[('batch_pipeline_privacy', privacy_owner_key(binding.owner_id))] = {'generation': 1}
        return WORDS, 'vi'

    second.side_effect = revoked
    assert recovery.recover('bad', binding.owner_id) == 'cancelled'
    assert not row(client).get('result')
    second.assert_called_once()


def test_byok_admission_still_checks_managed_soniox_allowance(setup, monkeypatch, legacy_dependencies):
    client, binding, _, _, second, recovery = second_setup(setup, monkeypatch, legacy_dependencies)
    row(client)['policy'] = {'provider_reason': 'byok'}
    allowed = Mock(return_value=False)
    monkeypatch.setattr(module, 'sync_allowed', allowed)
    assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    second.assert_not_called()
    assert allowed.call_args.args[2] == 'soniox'
