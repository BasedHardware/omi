"""Ordinary worker failures retain the same acoustic evidence as language guards."""

import pytest
from copy import deepcopy
import io
import wave

from tests.unit.test_batch_pipeline_quarantine_recovery import setup, legacy_dependencies, row  # noqa: F401
from tests.unit.test_batch_language_recovery import guarded, worker_receipt, WORDS, assert_worker_vad_result
from tests.unit.test_batch_pipeline_empty_disposition import SERVING_ENV
from utils.batch_pipeline.recovery_disposition import RecoveryFailure
from utils.batch_pipeline.speech_redrive import redrive_one


def ordinary(setup, monkeypatch, legacy_dependencies, *, automatic=True):
    values = guarded(setup, monkeypatch, legacy_dependencies, speech=0, automatic=automatic)
    row(values[0])['worker_failure'] = {'stage': 'assemble_words', 'reason': 'no_owned_words'}
    return values


@pytest.mark.parametrize('route', ['automatic', 'redrive'])
@pytest.mark.parametrize('safety_net', ['true', 'false'])
def test_terminal_empty_policy_cannot_dispose_positive_worker_speech_without_cpu_spans(
    setup, monkeypatch, legacy_dependencies, route, safety_net
):
    monkeypatch.setenv('BATCH_PIPELINE_TERMINAL_EMPTY_DISPOSITION_ENABLED', 'true')
    client, store, binding, artifacts, modulate, soniox, recovery, _ = ordinary(
        setup, monkeypatch, legacy_dependencies, automatic=route == 'automatic'
    )
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', safety_net)
    worker_receipt(client, 1.5)
    job = row(client)
    job['worker_empty_evidence'] = {'padded_retry': 'empty', 'version': 1}
    prior = deepcopy(job.get('recovery'))
    modulate.return_value = ([], 'vi')

    def apply():
        if route == 'automatic':
            return recovery.recover('bad', binding.owner_id)
        return redrive_one(
            store,
            artifacts,
            'bad',
            binding.owner_id,
            'reviewed-empty-plan',
            prior,
            server_flags=SERVING_ENV,
            clock=lambda: 100,
        )

    assert apply() == 'failed_held'
    job = row(client)
    intent = job['recovery'] if route == 'automatic' else job['speech_redrive']
    assert intent['failure'] == {'stage': 'response_validation', 'reason': 'empty_asr'}
    assert job['recovery_state'] == 'failed_held'
    assert job['state'] == 'quarantined' and not job.get('result')
    assert job['measured_held_vad_speech_seconds'] == 1.5
    assert apply() == ('held' if route == 'automatic' else 'failed_held')
    if route == 'redrive':
        assert row(client)['recovery'] == prior
    artifacts.persist_recovery_result.assert_not_called()
    modulate.assert_called_once()
    if route == 'automatic':
        soniox.assert_called_once()
        assert intent['recognizers']['soniox']['outcome'] == 'empty'
    else:
        soniox.assert_not_called()


@pytest.mark.parametrize('seconds', [0.032, 1.5, 4.384])
def test_ordinary_worker_speech_survives_zero_cpu_vad(setup, monkeypatch, legacy_dependencies, seconds):
    client, _, binding, artifacts, modulate, soniox, recovery, _ = ordinary(setup, monkeypatch, legacy_dependencies)
    worker_receipt(client, seconds)
    modulate.return_value = (WORDS, 'vi')
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    assert_worker_vad_result(client, artifacts.persist_recovery_result.call_args.args[1], seconds)
    assert row(client)['recovery']['recognizers']['modulate']['outcome'] == 'words'
    modulate.assert_called_once()
    soniox.assert_not_called()


@pytest.mark.parametrize(
    'duration,speech,reason',
    [
        (20.00025, 2.008125, 'no_owned_words'),
        (6.4294375, 1.0828125, 'empty_asr'),
        (10, 1.38375, 'no_owned_words'),
        (8.1, 0.945, 'no_owned_words'),
        (10, 0.725625, 'no_owned_words'),
        (30.4655625, 2.87775, 'no_owned_words'),
        (10.66, 4.62375, 'empty_asr'),
    ],
)
def test_observed_held_geometry_recovers_without_erasing_acoustic_speech(
    setup, monkeypatch, legacy_dependencies, duration, speech, reason
):
    from utils.batch_pipeline.contracts import projection_speech_spans

    client, _, binding, artifacts, modulate, soniox, recovery, _ = ordinary(setup, monkeypatch, legacy_dependencies)
    job = row(client)
    job['duration_seconds'] = duration
    job['worker_failure']['reason'] = reason
    worker_receipt(client, speech)
    audio = io.BytesIO()
    with wave.open(audio, 'wb') as handle:
        handle.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        handle.writeframes(b'\0' * (round(duration * 16000) * 2))
    artifacts.fetch_audio.return_value = audio.getvalue()
    modulate.return_value = (WORDS, 'vi')
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    payload = artifacts.persist_recovery_result.call_args.args[1]
    assert payload['audio_seconds'] == pytest.approx(duration, abs=1 / 16000)
    assert payload['speech_seconds'] == pytest.approx(speech, abs=1 / 16000)
    assert sum(s['end'] - s['start'] for s in projection_speech_spans(payload, duration)) == pytest.approx(speech)
    assert row(client)['measured_held_vad_speech_seconds'] == pytest.approx(speech)
    modulate.assert_called_once()
    soniox.assert_not_called()
    assert recovery.recover('bad', binding.owner_id) == 'held'
    modulate.assert_called_once()


@pytest.mark.parametrize('proof', ['missing', 'wrong_input', 'subframe'])
def test_ordinary_zero_cpu_vad_needs_bound_worker_proof(setup, monkeypatch, legacy_dependencies, proof):
    client, _, binding, artifacts, modulate, soniox, recovery, _ = ordinary(setup, monkeypatch, legacy_dependencies)
    receipt = worker_receipt(client, 0.016 if proof == 'subframe' else 1.5)
    if proof == 'missing':
        row(client).pop('worker_vad_receipt')
    elif proof == 'wrong_input':
        receipt['input_uri_sha256'] = '0' * 64
    assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    assert row(client)['measured_held_vad_speech_seconds'] == (0.016 if proof == 'subframe' else 1.5)
    assert not row(client).get('result')
    artifacts.persist_recovery_result.assert_not_called()
    modulate.assert_not_called()
    soniox.assert_not_called()


def test_ordinary_bound_worker_vad_does_not_bypass_funding(setup, monkeypatch, legacy_dependencies):
    client, _, binding, artifacts, modulate, soniox, recovery, _ = ordinary(setup, monkeypatch, legacy_dependencies)
    worker_receipt(client, 1.5)
    monkeypatch.setattr('utils.batch_pipeline.quarantine_recovery.sync_allowed', lambda *a, **kw: False)
    assert recovery.recover('bad', binding.owner_id) == 'held'
    assert row(client)['measured_held_vad_speech_seconds'] == 1.5
    assert not row(client)['recovery'].get('recognizers')
    artifacts.persist_recovery_result.assert_not_called()
    modulate.assert_not_called()
    soniox.assert_not_called()


@pytest.mark.parametrize('proof', ['bound', 'missing', 'wrong_input', 'funding', 'privacy'])
def test_reviewed_ordinary_redrive_uses_worker_proof_and_preserves_paid_intent(
    setup, monkeypatch, legacy_dependencies, proof
):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    client, store, binding, artifacts, modulate, soniox, _, _ = ordinary(
        setup, monkeypatch, legacy_dependencies, automatic=False
    )
    receipt = worker_receipt(client, 1.5)
    job = row(client)
    prior = deepcopy(job['recovery'])
    if proof == 'missing':
        job.pop('worker_vad_receipt')
    elif proof == 'wrong_input':
        receipt['input_uri_sha256'] = '0' * 64
    elif proof == 'funding':
        monkeypatch.setattr('utils.batch_pipeline.speech_redrive.sync_allowed', lambda *a, **kw: False)
    elif proof == 'privacy':
        client.rows[('users', binding.owner_id)]['migration_status'] = 'pending'
    modulate.return_value = (WORDS, 'vi')

    def apply():
        return redrive_one(
            store,
            artifacts,
            'bad',
            binding.owner_id,
            'reviewed-ordinary-plan',
            prior,
            server_flags=SERVING_ENV,
            clock=lambda: 100,
        )

    if proof in {'missing', 'wrong_input'}:
        with pytest.raises(RecoveryFailure):
            apply()
    elif proof == 'privacy':
        with pytest.raises(BatchPrivacyBlocked):
            apply()
    elif proof == 'funding':
        assert apply() == 'allowance_held'
    else:
        assert apply() == 'recovered'
        payload = artifacts.persist_recovery_result.call_args.args[1]
        assert payload['speech_seconds'] == 1.5 and payload['words']
        assert payload['speech_spans_source'] == 'worker_vad_word_clocks'
        job = row(client)
        assert job['recovery'] == prior
        assert job['speech_redrive']['prior_recovery'] == prior
        assert job['speech_redrive']['paid_epoch'] == 2
        assert apply() == 'already_applied'
        modulate.assert_called_once()
    if proof != 'bound':
        modulate.assert_not_called()
        artifacts.persist_recovery_result.assert_not_called()
    soniox.assert_not_called()


def test_ordinary_empty_response_keeps_worker_speech_and_spends_each_provider_once(
    setup, monkeypatch, legacy_dependencies
):
    client, _, binding, artifacts, modulate, soniox, recovery, _ = ordinary(setup, monkeypatch, legacy_dependencies)
    worker_receipt(client, 1.5)
    modulate.return_value = ([], 'vi')
    assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    assert row(client)['recovery']['failure'] == {'stage': 'response_validation', 'reason': 'empty_asr'}
    assert row(client)['measured_held_vad_speech_seconds'] == 1.5
    assert row(client)['recovery']['recognizers']['modulate']['outcome'] == 'empty'
    assert recovery.recover('bad', binding.owner_id) == 'held'
    artifacts.persist_recovery_result.assert_not_called()
    modulate.assert_called_once()
    soniox.assert_called_once()
    assert row(client)['recovery']['recognizers']['soniox']['outcome'] == 'empty'


@pytest.mark.parametrize('outcome', ['words', 'error', 'privacy'])
def test_ordinary_serving_async_preserves_receipts_and_privacy(setup, monkeypatch, legacy_dependencies, outcome):
    import asyncio

    client, _, binding, artifacts, modulate, soniox, recovery, _ = ordinary(setup, monkeypatch, legacy_dependencies)
    worker_receipt(client, 1.5)
    if outcome == 'error':
        modulate.side_effect = RuntimeError('SYNTHETIC_PRIVATE_SENTINEL')
    elif outcome == 'privacy':
        client.rows[('users', binding.owner_id)]['migration_status'] = 'pending'
    else:
        modulate.return_value = (WORDS, 'vi')
    expected = {'words': 'recovered', 'error': 'failed_held', 'privacy': 'cancelled'}[outcome]
    assert asyncio.run(recovery.recover_async('bad', binding.owner_id)) == expected
    if outcome == 'privacy':
        modulate.assert_not_called()
    else:
        assert row(client)['recovery']['recognizers']['modulate']['outcome'] == outcome
        modulate.assert_called_once()
    if outcome != 'words':
        artifacts.persist_recovery_result.assert_not_called()
    soniox.assert_not_called()
