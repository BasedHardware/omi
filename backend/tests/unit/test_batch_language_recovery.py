"""Synthetic language-guard recovery, paid-intent fencing and measured receipts."""

from copy import deepcopy
import io
import wave
from unittest.mock import Mock, AsyncMock

import pytest

from config.batch_language_recovery import allowed, below_silence_threshold
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection import ProjectionStore
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_recognizer_receipts import record_recognizer
from database.batch_pipeline_speech_redrive import SpeechRedriveStore
from tests.unit.test_batch_pipeline_quarantine_recovery import setup, legacy_dependencies, row, PARTIAL_ACCOUNTING
from tests.unit.test_batch_pipeline_speech_redrive import enabled
from tests.unit.test_batch_pipeline_empty_disposition import SERVING_ENV
from utils.batch_pipeline.recovery_recognizers import transcribe
from utils.batch_pipeline.recovery_disposition import RecoveryFailure, independent_silence_payload, result_outcome
from utils.batch_pipeline.speech_redrive import redrive_one
from utils.batch_pipeline.contracts import vad_receipt

WORDS = [{'text': 'Synthetic.', 'timestamp': [1, 2], 'speaker': '0'}]


def guarded(setup, monkeypatch, legacy_dependencies, *, speech=1, automatic=True):
    client, store, binding, artifacts, legacy, modulate, old = enabled(setup, monkeypatch, legacy_dependencies)
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED', 'true')
    monkeypatch.delenv('BATCH_PIPELINE_INDEPENDENT_RECOVERY_MAX_SECONDS', raising=False)
    job = row(client)
    job['worker_failure'] = {'stage': 'vad_windows', 'reason': 'unsupported_language'}
    job['recovery'].update(provider='modulate', failure={'stage': 'response_validation', 'reason': 'empty_asr'})
    old = deepcopy(job['recovery'])
    if automatic:
        job.pop('recovery')
        job['recovery_state'] = 'held'
    _, vad, *_ = legacy_dependencies
    monkeypatch.setattr(vad, 'offline_pcm_speech_segments', lambda _: [{'start': 0, 'end': speech}] if speech else [])
    from utils.stt import soniox_batch

    soniox = Mock(return_value=([], 'multi'))
    monkeypatch.setattr(soniox_batch, 'transcribe', soniox)
    monkeypatch.setattr(soniox_batch, 'transcribe_async', AsyncMock(side_effect=soniox))
    monkeypatch.setenv('SONIOX_API_KEY', 'synthetic-only-key')
    monkeypatch.setattr('utils.batch_pipeline.quarantine_recovery.sync_allowed', lambda *a, **kw: True)
    monkeypatch.setattr('utils.batch_pipeline.speech_redrive.sync_allowed', lambda *a, **kw: True)
    modulate.return_value = ([], 'multi')
    recovery = setup[-1]
    recovery.stt = transcribe
    return client, store, binding, artifacts, modulate, soniox, recovery, old


@pytest.mark.parametrize('speech', [0.032, 0.064, 0.320, 4.384])
def test_two_empty_recognizers_retain_measured_speech(setup, monkeypatch, legacy_dependencies, speech):
    client, _, binding, artifacts, modulate, soniox, recovery, _ = guarded(
        setup, monkeypatch, legacy_dependencies, speech=speech
    )
    assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    job = row(client)
    assert job['measured_held_vad_speech_seconds'] == speech
    assert job['recovery']['recognizers'] == {
        p: {'provider': p, 'outcome': 'empty', 'word_count': 0, 'vad_speech_seconds': speech}
        for p in ('modulate', 'soniox')
    }
    assert recovery.recover('bad', binding.owner_id) == 'held'
    artifacts.persist_recovery_result.assert_not_called()
    modulate.assert_called_once()
    soniox.assert_called_once()


@pytest.mark.parametrize('census', [0, 2])
@pytest.mark.parametrize('stored,decoded', [(61, 61), (59.96, 60.04), (60, 60.04)])
def test_hard_duration_refusal_retains_audio_without_repeating_inspection(
    setup, monkeypatch, legacy_dependencies, census, stored, decoded
):
    client, store, binding, artifacts, modulate, soniox, recovery, _ = guarded(
        setup, monkeypatch, legacy_dependencies, speech=0
    )
    job = row(client)
    job['duration_seconds'] = stored
    job['measured_held_vad_speech_seconds'] = census
    job['worker_vad_receipt'] = original = vad_receipt(job['audio_uri'], round(stored * 16000), census)
    audio = io.BytesIO()
    with wave.open(audio, 'wb') as handle:
        handle.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        handle.writeframes(b'\0' * (round(decoded * 16000) * 2))
    artifacts.fetch_audio.return_value = audio.getvalue()
    audio_uri = job['audio_uri']
    assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    held = row(client)
    assert held['recovery_state'] == 'failed_held' and held['state'] == 'quarantined'
    assert held['audio_uri'] == audio_uri and held['worker_vad_receipt'] == original
    assert held['measured_held_vad_speech_seconds'] == census
    assert held['recovery']['refusal'] == {
        'reason': 'independent_duration_limit',
        'max_audio_seconds': 60,
        'audio_seconds': decoded,
    }
    assert not set(held['recovery']) & {'provider', 'started_at', 'recognizers'}
    assert not held.get('result')
    for _ in range(3):
        assert recovery.recover('bad', binding.owner_id) == 'held'
    artifacts.fetch_audio.assert_called_once()
    artifacts.persist_recovery_result.assert_not_called()
    modulate.assert_not_called()
    soniox.assert_not_called()
    # Retaining an unspent intent must not fabricate eligibility for the paid
    # redrive tool, whose ownership proof requires a previously started epoch.
    with pytest.raises(ProjectionBlocked, match='speech redrive ownership changed'):
        SpeechRedriveStore(store, server_flags=SERVING_ENV).prepare(
            'bad', binding.owner_id, 'reviewed-plan', deepcopy(held['recovery']), 101
        )
    # The client can finish its successful sibling while the original audio
    # remains held for a reviewed redrive. No held seconds are charged.
    assert ProjectionStore(store).complete_partial(binding, 101, PARTIAL_ACCOUNTING)[0]['held_segments'] == 1
    assert row(client)['audio_uri'] == audio_uri and not row(client).get('result')


@pytest.mark.parametrize(
    'change', ['token', 'running', 'lease', 'result', 'duration', 'audio', 'not_guarded', 'privacy']
)
def test_hard_duration_hold_requires_current_prepared_privacy_fenced_intent(
    setup, monkeypatch, legacy_dependencies, change
):
    client, _, binding, artifacts, modulate, soniox, recovery, _ = guarded(
        setup, monkeypatch, legacy_dependencies, speech=0
    )
    row(client)['duration_seconds'] = 61
    prepared = recovery.protocol.prepare('bad', binding.owner_id, 100)
    token = prepared['recovery']['token']
    expected_audio_uri = prepared['audio_uri']
    job = row(client)
    if change == 'token':
        token = 'stale'
    elif change == 'running':
        assert recovery.protocol.start('bad', token, 100)
    elif change == 'lease':
        job['lease_until'] = 200
    elif change == 'result':
        job['result'] = {'outcome': 'success'}
    elif change == 'duration':
        job['duration_seconds'] = 60
    elif change == 'audio':
        job['audio_uri'] = 'gs://synthetic/different-audio'
    elif change == 'not_guarded':
        job.pop('worker_failure')
    else:
        client.rows[('users', binding.owner_id)]['migration_status'] = 'pending'
    before = deepcopy(client.rows)
    if change == 'privacy':
        with pytest.raises(BatchPrivacyBlocked):
            recovery.protocol.hold_duration_limit('bad', token, 101, audio_uri=expected_audio_uri, audio_seconds=61)
    else:
        assert not recovery.protocol.hold_duration_limit(
            'bad', token, 101, audio_uri=expected_audio_uri, audio_seconds=61
        )
    assert client.rows == before
    artifacts.fetch_audio.assert_not_called()
    modulate.assert_not_called()
    soniox.assert_not_called()


def test_independent_words_recover_without_repeating_modulate(setup, monkeypatch, legacy_dependencies):
    client, _, binding, artifacts, modulate, soniox, recovery, _ = guarded(setup, monkeypatch, legacy_dependencies)
    soniox.return_value = (WORDS, 'vi')
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    payload = artifacts.persist_recovery_result.call_args.args[1]
    assert payload['words_provider'] == 'soniox' and payload['language'] == 'vi'
    assert row(client)['recovery']['recognizers']['soniox']['word_count'] == 1
    modulate.assert_called_once()
    soniox.assert_called_once()


def test_first_provider_words_do_not_buy_another_recognizer(setup, monkeypatch, legacy_dependencies):
    client, _, binding, _, modulate, soniox, recovery, _ = guarded(setup, monkeypatch, legacy_dependencies)
    modulate.return_value = (WORDS, 'vi')
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    assert row(client)['recovery']['recognizers']['modulate']['word_count'] == 1
    soniox.assert_not_called()


def test_subframe_empty_is_silence_with_original_measurements(setup, monkeypatch, legacy_dependencies):
    client, _, binding, artifacts, _, soniox, recovery, _ = guarded(
        setup, monkeypatch, legacy_dependencies, speech=0.016
    )
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    payload = artifacts.persist_recovery_result.call_args.args[1]
    assert result_outcome(payload) == 'silence'
    assert payload['measured_vad_speech_seconds'] == 0.016
    assert payload['measured_vad_speech_spans'] == [{'start': 0, 'end': 0.016}]
    assert row(client)['measured_held_vad_speech_seconds'] == 0.016
    soniox.assert_called_once()


@pytest.mark.parametrize('change', ['missing_second', 'same_provider', 'unknown_vad', 'full_frame'])
def test_silence_requires_independent_measured_evidence(change):
    payload = independent_silence_payload(5, [{'start': 0, 'end': 0.016}])
    if change == 'missing_second':
        payload['recognizer_receipts'].pop('soniox')
    elif change == 'same_provider':
        payload['recognizer_receipts']['soniox']['provider'] = 'modulate'
    elif change == 'unknown_vad':
        payload['measured_vad_speech_seconds'] = None
    else:
        payload['measured_vad_speech_seconds'] = 0.032
    with pytest.raises(RecoveryFailure):
        result_outcome(payload)


@pytest.mark.parametrize('answer', ['empty', 'words'])
def test_primary_error_still_tries_independent_but_cannot_prove_silence(
    setup, monkeypatch, legacy_dependencies, answer
):
    client, _, binding, _, modulate, soniox, recovery, _ = guarded(
        setup, monkeypatch, legacy_dependencies, speech=0.016 if answer == 'empty' else 1
    )
    modulate.side_effect = TimeoutError('PRIVATE_SENTINEL')
    soniox.return_value = (WORDS if answer == 'words' else [], 'vi')
    assert recovery.recover('bad', binding.owner_id) == ('recovered' if answer == 'words' else 'failed_held')
    assert row(client)['recovery']['recognizers']['modulate']['outcome'] == 'error'
    soniox.assert_called_once()


@pytest.mark.parametrize('fault', [TimeoutError('PRIVATE_SENTINEL'), ([], None), ('malformed',)])
def test_independent_error_is_held_without_false_empty_evidence(setup, monkeypatch, legacy_dependencies, caplog, fault):
    client, _, binding, _, _, soniox, recovery, _ = guarded(setup, monkeypatch, legacy_dependencies, speech=0.016)
    if isinstance(fault, Exception):
        soniox.side_effect = fault
    else:
        soniox.return_value = fault
    assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    receipt = row(client)['recovery']['recognizers']['soniox']
    assert receipt['outcome'] == 'error' and receipt['word_count'] is None
    assert 'PRIVATE_SENTINEL' not in caplog.text


@pytest.mark.parametrize(
    'name,value',
    [
        ('BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED', 'false'),
        ('BATCH_PIPELINE_INDEPENDENT_RECOVERY_MAX_SECONDS', '1'),
        ('BATCH_PIPELINE_INDEPENDENT_RECOVERY_MAX_SECONDS', 'NaN'),
    ],
)
def test_default_on_spend_guards_leave_explicit_unattempted_receipt(
    setup, monkeypatch, legacy_dependencies, name, value
):
    client, _, binding, _, _, soniox, recovery, _ = guarded(setup, monkeypatch, legacy_dependencies)
    monkeypatch.setenv(name, value)
    assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    assert row(client)['recovery']['recognizers']['soniox']['outcome'] == 'refused'
    soniox.assert_not_called()


def test_hard_cost_and_sample_bounds(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_RECOVERY_MAX_SECONDS', '7200')
    assert allowed(60) and not allowed(60.001)
    assert below_silence_threshold(511 / 16000)
    assert not below_silence_threshold(0.032 - 1e-12)
    assert not below_silence_threshold(0.064)


def test_second_claim_is_cas_and_requires_current_privacy_token(setup, monkeypatch, legacy_dependencies):
    client, store, binding, _, _, _, recovery, _ = guarded(setup, monkeypatch, legacy_dependencies)
    job = recovery.protocol.prepare('bad', binding.owner_id, 100)
    token = job['recovery']['token']
    assert recovery.protocol.start('bad', token, 100, provider='modulate')
    assert record_recognizer(store, 'bad', token, 'recovery', 'soniox', 'started', None, 1, claim=True)
    assert not record_recognizer(store, 'bad', token, 'recovery', 'soniox', 'started', None, 1, claim=True)
    from database.batch_pipeline_projection_protocol import ProjectionBlocked

    with pytest.raises(ProjectionBlocked):
        record_recognizer(store, 'bad', 'foreign-token', 'recovery', 'soniox', 'empty', 0, 1)


@pytest.mark.parametrize('previous_paid', [False, True])
@pytest.mark.parametrize(
    'speech,outcome', [(0, 'recovered'), (0.016, 'recovered'), (0.064, 'failed_held'), (4.384, 'failed_held')]
)
def test_explicit_independent_redrive_preserves_both_spent_epochs(
    setup, monkeypatch, legacy_dependencies, previous_paid, speech, outcome
):
    client, store, binding, artifacts, modulate, soniox, _, old = guarded(
        setup, monkeypatch, legacy_dependencies, speech=speech, automatic=False
    )
    previous = None
    if previous_paid:
        previous = {
            'provider': 'modulate',
            'paid_epoch': 2,
            'state': 'failed_held',
            'token': 'old-paid-token',
            'plan_digest': 'old-paid-plan',
            'started_at': 3,
            'settled_at': 4,
            'privacy_generation': 0,
            'prior_recovery': deepcopy(old),
            'failure': {'stage': 'response_validation', 'reason': 'empty_asr'},
        }
        row(client)['speech_redrive'] = deepcopy(previous)
    for _ in range(2):
        result = redrive_one(
            store,
            artifacts,
            'bad',
            binding.owner_id,
            'independent-plan',
            old,
            server_flags=SERVING_ENV,
            clock=lambda: 100,
            independent_language=True,
        )
        assert result in ({'recovered', 'already_applied'} if outcome == 'recovered' else {'failed_held'})
    job = row(client)
    assert job['recovery'] == old
    assert job['speech_redrive']['provider'] == 'soniox' and job['speech_redrive']['paid_epoch'] == 3
    assert job['speech_redrive'].get('prior_speech_redrive') == previous
    assert job['speech_redrive']['recognizers']['soniox']['vad_speech_seconds'] == speech
    modulate.assert_not_called()
    soniox.assert_called_once()


def test_old_modulate_plan_cannot_implicitly_buy_soniox(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, modulate, soniox, _, old = guarded(
        setup, monkeypatch, legacy_dependencies, automatic=False
    )
    assert (
        redrive_one(store, artifacts, 'bad', binding.owner_id, 'old-plan', old, server_flags=SERVING_ENV)
        == 'independent_plan_required'
    )
    assert not row(client).get('speech_redrive')
    modulate.assert_not_called()
    soniox.assert_not_called()


def test_redrive_result_reconciles_without_repeating_paid_call(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, modulate, soniox, _, old = guarded(
        setup, monkeypatch, legacy_dependencies, automatic=False
    )
    soniox.return_value = (WORDS, 'vi')
    artifacts.persist_recovery_result.side_effect = RuntimeError('synthetic storage fault')
    args = (store, artifacts, 'bad', binding.owner_id, 'independent-plan', old)
    kwargs = dict(server_flags=SERVING_ENV, clock=lambda: 100, independent_language=True)
    with pytest.raises(RuntimeError):
        redrive_one(*args, **kwargs)
    assert redrive_one(*args, **kwargs) == 'running_held'
    artifacts.find_recovery_result.return_value = 'gs://synthetic/reconciled'
    assert redrive_one(*args, **kwargs) == 'reconciled'
    soniox.assert_called_once()
    modulate.assert_not_called()


def test_auto_independent_attempt_cannot_be_bought_again_by_operator(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, modulate, soniox, recovery, _ = guarded(setup, monkeypatch, legacy_dependencies)
    assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    old = deepcopy(row(client)['recovery'])
    from database.batch_pipeline_projection_protocol import ProjectionBlocked

    with pytest.raises(ProjectionBlocked, match='already attempted'):
        redrive_one(
            store,
            artifacts,
            'bad',
            binding.owner_id,
            'new-plan',
            old,
            server_flags=SERVING_ENV,
            independent_language=True,
        )
    soniox.assert_called_once()
    modulate.assert_called_once()


@pytest.mark.parametrize('guard', ['kill', 'cap', 'allowance'])
def test_redrive_refusal_keeps_measured_vad_without_spending_intent(setup, monkeypatch, legacy_dependencies, guard):
    client, store, binding, artifacts, modulate, soniox, _, old = guarded(
        setup, monkeypatch, legacy_dependencies, automatic=False
    )
    if guard == 'kill':
        monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED', 'false')
    elif guard == 'cap':
        monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_RECOVERY_MAX_SECONDS', '1')
    else:
        monkeypatch.setattr('utils.batch_pipeline.speech_redrive.sync_allowed', lambda *a, **kw: False)
    outcome = redrive_one(
        store, artifacts, 'bad', binding.owner_id, 'plan', old, server_flags=SERVING_ENV, independent_language=True
    )
    assert outcome in {'independent_budget_held', 'allowance_held'}
    assert row(client)['speech_redrive']['state'] == 'prepared'
    assert row(client)['measured_held_vad_speech_seconds'] == 1
    modulate.assert_not_called()
    soniox.assert_not_called()


def test_independent_plan_binds_spent_paid_token(setup, monkeypatch, legacy_dependencies):
    client, _, _, _, _, _, _, old = guarded(setup, monkeypatch, legacy_dependencies, automatic=False)
    import importlib.util
    from pathlib import Path
    import sys

    scripts = Path(__file__).parents[2] / 'scripts'
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location('independent_operator', scripts / 'batch_pipeline_speech_redrive.py')
    operator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(operator)
    job = row(client)
    marker = {'provider': 'modulate', 'token': 'first-paid-token', 'paid_epoch': 2, 'state': 'failed_held'}
    job['speech_redrive'] = marker
    before = operator.fingerprint(job, True)
    marker['token'] = 'different-paid-token'
    assert before != operator.fingerprint(job, True)
    previous = deepcopy(marker)
    job['speech_redrive'] = {'provider': 'soniox', 'prior_speech_redrive': previous, 'token': 'independent-token'}
    assert operator.fingerprint(job, True) == operator.fingerprint({**job, 'speech_redrive': previous}, True)
    assert operator.paid_digest('census', 1, 3, independent=True) != operator.paid_digest('census', 1, 3)


def test_privacy_change_after_modulate_blocks_independent_dispatch(setup, monkeypatch, legacy_dependencies):
    client, _, binding, artifacts, modulate, soniox, recovery, _ = guarded(setup, monkeypatch, legacy_dependencies)
    from database.batch_pipeline_privacy import privacy_owner_key

    def revoked(*args, **kwargs):
        client.rows[('batch_pipeline_privacy', privacy_owner_key(binding.owner_id))] = {'generation': 1}
        return [], 'multi'

    modulate.side_effect = revoked
    assert recovery.recover('bad', binding.owner_id) == 'cancelled'
    soniox.assert_not_called()
    artifacts.persist_recovery_result.assert_not_called()


def test_customer_funding_cannot_bypass_company_soniox_allowance(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, modulate, soniox, _, old = guarded(
        setup, monkeypatch, legacy_dependencies, automatic=False
    )
    row(client)['policy'] = {'provider_reason': 'byok'}
    allowance = Mock(return_value=False)
    monkeypatch.setattr('utils.batch_pipeline.speech_redrive.sync_allowed', allowance)
    assert (
        redrive_one(
            store, artifacts, 'bad', binding.owner_id, 'plan', old, server_flags=SERVING_ENV, independent_language=True
        )
        == 'allowance_held'
    )
    assert allowance.call_args.args[2] == 'soniox'
    modulate.assert_not_called()
    soniox.assert_not_called()


def test_guarded_obligation_drains_with_older_multilingual_snapshot_off(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, modulate, soniox, _, old = guarded(
        setup, monkeypatch, legacy_dependencies, automatic=False
    )
    monkeypatch.setenv('BATCH_PIPELINE_SPEECH_EMPTY_MULTILINGUAL_ENABLED', 'false')
    soniox.return_value = (WORDS, 'vi')
    assert (
        redrive_one(
            store, artifacts, 'bad', binding.owner_id, 'plan', old, server_flags=SERVING_ENV, independent_language=True
        )
        == 'recovered'
    )
    soniox.assert_called_once()
    modulate.assert_not_called()


def test_guarded_zero_vad_requires_both_empty_recognizers_before_silence(setup, monkeypatch, legacy_dependencies):
    client, _, binding, artifacts, modulate, soniox, recovery, _ = guarded(
        setup, monkeypatch, legacy_dependencies, speech=0
    )
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    payload = artifacts.persist_recovery_result.call_args.args[1]
    assert result_outcome(payload) == 'silence'
    assert payload['words_provider'] == 'independent_empty_strict_vad'
    assert payload['measured_vad_speech_seconds'] == 0
    modulate.assert_called_once()
    soniox.assert_called_once()
    assert row(client)['recovery']['recognizers']['soniox']['outcome'] == 'empty'


@pytest.mark.parametrize(
    'first,second', [('words', 'empty'), ('empty', 'words'), ('words', 'words'), ('error', 'empty')]
)
def test_zero_vad_words_or_provider_error_cannot_become_silence(setup, monkeypatch, legacy_dependencies, first, second):
    client, _, binding, artifacts, modulate, soniox, recovery, _ = guarded(
        setup, monkeypatch, legacy_dependencies, speech=0
    )
    if first == 'error':
        modulate.side_effect = TimeoutError('synthetic')
    else:
        modulate.return_value = (WORDS if first == 'words' else [], 'vi')
    soniox.return_value = (WORDS if second == 'words' else [], 'vi')
    meter = Mock()
    monkeypatch.setattr('utils.batch_pipeline.quarantine_recovery.record_accepted', meter)
    assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    receipts = row(client)['recovery']['recognizers']
    assert receipts['modulate']['outcome'] == first
    assert receipts['soniox']['outcome'] == second
    assert receipts['modulate']['word_count'] == (1 if first == 'words' else 0 if first == 'empty' else None)
    assert receipts['soniox']['word_count'] == (1 if second == 'words' else 0)
    assert row(client)['measured_held_vad_speech_seconds'] == 0
    assert [call.args[1] for call in meter.call_args_list] == (
        ['soniox'] if first == 'error' else ['modulate', 'soniox']
    )
    artifacts.persist_recovery_result.assert_not_called()
    modulate.assert_called_once()
    soniox.assert_called_once()


@pytest.mark.parametrize('guard', ['kill', 'cap', 'allowance'])
def test_zero_vad_spend_refusal_keeps_prepared_obligation(setup, monkeypatch, legacy_dependencies, guard):
    client, _, binding, _, modulate, soniox, recovery, _ = guarded(setup, monkeypatch, legacy_dependencies, speech=0)
    if guard == 'kill':
        monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED', 'false')
    elif guard == 'cap':
        monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_RECOVERY_MAX_SECONDS', '1')
    else:
        row(client)['policy'] = {'provider_reason': 'byok'}
        monkeypatch.setattr('utils.batch_pipeline.quarantine_recovery.sync_allowed', lambda *a, **kw: False)
    assert recovery.recover('bad', binding.owner_id) == 'held'
    assert row(client)['recovery_state'] == 'prepared'
    assert row(client)['measured_held_vad_speech_seconds'] == 0
    modulate.assert_not_called()
    soniox.assert_not_called()


def test_spent_epoch2_empty_is_independent_evidence_when_epoch1_failed(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, modulate, soniox, _, _ = guarded(
        setup, monkeypatch, legacy_dependencies, speech=0.016, automatic=False
    )
    row(client)['recovery']['failure'] = {'stage': 'provider', 'reason': 'provider_failed'}
    old = deepcopy(row(client)['recovery'])
    previous = {
        'provider': 'modulate',
        'paid_epoch': 2,
        'state': 'failed_held',
        'token': 'old-paid-token',
        'plan_digest': 'old-paid-plan',
        'started_at': 3,
        'settled_at': 4,
        'privacy_generation': 0,
        'prior_recovery': deepcopy(old),
        'failure': {'stage': 'response_validation', 'reason': 'empty_asr'},
    }
    row(client)['speech_redrive'] = deepcopy(previous)
    assert (
        redrive_one(
            store,
            artifacts,
            'bad',
            binding.owner_id,
            'independent-plan',
            old,
            server_flags=SERVING_ENV,
            independent_language=True,
            clock=lambda: 100,
        )
        == 'recovered'
    )
    assert row(client)['speech_redrive']['prior_speech_redrive'] == previous
    assert result_outcome(artifacts.persist_recovery_result.call_args.args[1]) == 'silence'
    modulate.assert_not_called()
    soniox.assert_called_once()


def test_recorded_provider_error_cannot_be_promoted_to_valid_empty():
    from config.batch_language_recovery import prior_modulate_empty

    job = {
        'recovery': {
            'provider': 'modulate',
            'failure': {'stage': 'response_validation', 'reason': 'empty_asr'},
            'recognizers': {'modulate': {'outcome': 'error', 'word_count': None}},
        }
    }
    assert not prior_modulate_empty(job)


def test_missing_soniox_key_does_not_burn_the_independent_attempt(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, _, soniox, recovery, _ = guarded(setup, monkeypatch, legacy_dependencies)
    from config.batch_language_recovery import independent_attempted

    monkeypatch.delenv('SONIOX_API_KEY', raising=False)
    assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    assert not independent_attempted(row(client))
    soniox.assert_not_called()
    monkeypatch.setenv('SONIOX_API_KEY', 'synthetic-only-key')
    soniox.return_value = (WORDS, 'vi')
    assert (
        redrive_one(
            store,
            artifacts,
            'bad',
            binding.owner_id,
            'new-plan',
            deepcopy(row(client)['recovery']),
            server_flags=SERVING_ENV,
            independent_language=True,
        )
        == 'recovered'
    )


@pytest.mark.parametrize('case', ['disabled', 'cap', 'allowance', 'empty', 'error', 'worker_vad_words'])
def test_cpu_zero_never_erases_positive_worker_census(setup, monkeypatch, legacy_dependencies, case):
    from utils.batch_pipeline.contracts import vad_receipt

    client, _, binding, artifacts, _, soniox, recovery, _ = guarded(setup, monkeypatch, legacy_dependencies, speech=0)
    job = row(client)
    job['measured_held_vad_speech_seconds'] = 2
    job['worker_vad_receipt'] = receipt = vad_receipt(job['audio_uri'], round(job['duration_seconds'] * 16000), 2)
    if case == 'disabled':
        monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED', 'false')
    elif case == 'cap':
        monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_RECOVERY_MAX_SECONDS', '1')
    elif case == 'allowance':
        monkeypatch.setattr('utils.batch_pipeline.quarantine_recovery.sync_allowed', lambda *a, **kw: False)
    elif case == 'error':
        soniox.side_effect = TimeoutError('synthetic')
    elif case == 'worker_vad_words':
        soniox.return_value = (WORDS, 'vi')
    expected = (
        'held'
        if case in {'disabled', 'cap', 'allowance'}
        else 'recovered' if case == 'worker_vad_words' else 'failed_held'
    )
    assert recovery.recover('bad', binding.owner_id) == expected
    final = row(client)
    assert final['measured_held_vad_speech_seconds'] == 2
    assert final['worker_vad_receipt'] == receipt
    assert artifacts.persist_recovery_result.called is (expected == 'recovered')
    if expected == 'failed_held':
        assert all(r['vad_speech_seconds'] == 0 for r in final['recovery']['recognizers'].values())


@pytest.mark.parametrize('case', ['disabled', 'empty', 'error'])
def test_operator_zero_never_erases_positive_held_census(setup, monkeypatch, legacy_dependencies, case):
    client, store, binding, artifacts, _, soniox, _, old = guarded(
        setup, monkeypatch, legacy_dependencies, speech=0, automatic=False
    )
    row(client)['measured_held_vad_speech_seconds'] = 2
    if case == 'disabled':
        monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED', 'false')
    elif case == 'error':
        soniox.side_effect = TimeoutError('synthetic')
    expected = 'independent_budget_held' if case == 'disabled' else 'failed_held'
    assert (
        redrive_one(
            store,
            artifacts,
            'bad',
            binding.owner_id,
            'new-plan',
            old,
            server_flags=SERVING_ENV,
            independent_language=True,
        )
        == expected
    )
    assert row(client)['measured_held_vad_speech_seconds'] == 2
    artifacts.persist_recovery_result.assert_not_called()
    if case != 'disabled':
        assert row(client)['speech_redrive']['recognizers']['soniox']['vad_speech_seconds'] == 0


@pytest.mark.parametrize('prior,new,expected', [(None, None, None), (None, 0, 0), (2, None, 2), (2, 0, 2), (2, 4, 4)])
def test_held_vad_census_is_monotone(prior, new, expected):
    from utils.batch_pipeline.contracts import attach_held_vad, held_vad_census

    job = {'duration_seconds': 20, 'measured_held_vad_speech_seconds': prior}
    assert held_vad_census(job, new) == expected
    attach_held_vad(job, new)
    assert job['measured_held_vad_speech_seconds'] == expected


@pytest.mark.parametrize('prior', [None, 2])
@pytest.mark.parametrize('operator', [False, True])
def test_saved_silence_cannot_discharge_unknown_or_positive_held_evidence(
    setup, monkeypatch, legacy_dependencies, prior, operator
):
    client, store, binding, _, _, _, recovery, old = guarded(
        setup, monkeypatch, legacy_dependencies, speech=0, automatic=not operator
    )
    row(client)['measured_held_vad_speech_seconds'] = prior
    if operator:
        protocol = SpeechRedriveStore(store, server_flags=SERVING_ENV)
        job = protocol.prepare('bad', binding.owner_id, 'new-plan', old, 100)
        token = job['speech_redrive']['token']
        assert protocol.start('bad', token, 'new-plan', 100)
        assert not protocol.settle('bad', token, 'new-plan', 101, 'encrypted:stale-silence', outcome='silence')
    else:
        protocol = recovery.protocol
        job = protocol.prepare('bad', binding.owner_id, 100)
        token = job['recovery']['token']
        assert protocol.start('bad', token, 100, provider='modulate')
        assert not protocol.settle('bad', token, 101, 'encrypted:stale-silence', outcome='silence')
    assert row(client)['measured_held_vad_speech_seconds'] == prior
    assert not row(client).get('result')


def worker_receipt(client, seconds):
    from utils.batch_pipeline.contracts import vad_receipt

    job = row(client)
    job['worker_vad_receipt'] = vad_receipt(job['audio_uri'], round(job['duration_seconds'] * 16000), seconds)
    job['measured_held_vad_speech_seconds'] = seconds
    return job['worker_vad_receipt']


# Acoustic worker measure placed at the [1, 2] word clock within the 5 s capture.
PLACED = {0.032: [(1.0, 1.032)], 1.5: [(1.0, 2.5)], 4.384: [(0.616, 5.0)]}


def assert_worker_vad_result(client, payload, seconds):
    """The recovered payload passes the typed contracts projection enforces, and
    every accounting input is the acoustic worker measure (lead ruling ef03d2)."""
    from dataclasses import fields

    from utils.batch_pipeline.contracts import WorkItem, WorkResult, projection_speech_spans
    from utils.batch_pipeline.projection_parts import split_result

    assert result_outcome(payload) == 'success'
    spans = projection_speech_spans(payload, 5)
    assert [(s['start'], s['end']) for s in spans] == [pytest.approx(pair) for pair in PLACED[seconds]]
    assert payload['speech_seconds'] == pytest.approx(seconds, abs=1e-9) and payload['audio_seconds'] == 5
    assert payload['speech_spans_source'] == 'worker_vad_word_clocks'
    assert payload['worker_vad_speech_seconds'] == seconds
    assert payload['language'] == 'vi' and [w['word'] for w in payload['words']] == ['Synthetic.']
    job = row(client)
    item = WorkItem(**{f.name: job[f.name] for f in fields(WorkItem) if f.name in job})
    [(_, part)] = split_result(item, payload)
    assert part['speech_seconds'] == pytest.approx(seconds, abs=1e-9)
    assert [w['word'] for w in part['words']] == ['Synthetic.']
    assert job['recovery_state'] == 'recovered' and job['state'] == 'result_ready'
    assert WorkResult(**job['result']).outcome == 'success'
    assert job['measured_held_vad_speech_seconds'] == pytest.approx(seconds, abs=1e-9)


@pytest.mark.parametrize('seconds', [0.032, 1.5, 4.384])
def test_worker_vad_locates_modulate_words_when_cpu_vad_is_empty(setup, monkeypatch, legacy_dependencies, seconds):
    client, _, binding, artifacts, modulate, soniox, recovery, _ = guarded(
        setup, monkeypatch, legacy_dependencies, speech=0
    )
    worker_receipt(client, seconds)
    modulate.return_value = (WORDS, 'vi')
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    assert_worker_vad_result(client, artifacts.persist_recovery_result.call_args.args[1], seconds)
    assert row(client)['recovery']['recognizers']['modulate'] == {
        'provider': 'modulate',
        'outcome': 'words',
        'word_count': 1,
        'vad_speech_seconds': 0,
    }
    modulate.assert_called_once()
    soniox.assert_not_called()


@pytest.mark.parametrize('mode', ['sync', 'async'])
def test_worker_vad_locates_independent_words_after_modulate_empty(setup, monkeypatch, legacy_dependencies, mode):
    import asyncio

    client, _, binding, artifacts, modulate, soniox, recovery, _ = guarded(
        setup, monkeypatch, legacy_dependencies, speech=0
    )
    worker_receipt(client, 1.5)
    soniox.return_value = (WORDS, 'vi')
    outcome = (
        recovery.recover('bad', binding.owner_id)
        if mode == 'sync'
        else asyncio.run(recovery.recover_async('bad', binding.owner_id))
    )
    assert outcome == 'recovered'
    payload = artifacts.persist_recovery_result.call_args.args[1]
    assert payload['words_provider'] == 'soniox'
    assert_worker_vad_result(client, payload, 1.5)
    modulate.assert_called_once()
    soniox.assert_called_once()


@pytest.mark.parametrize('change', ['absent', 'zero', 'subframe', 'foreign_audio', 'unmeasured', 'other_duration'])
def test_words_without_independent_worker_speech_still_fail_closed(setup, monkeypatch, legacy_dependencies, change):
    import hashlib

    client, _, binding, artifacts, modulate, soniox, recovery, _ = guarded(
        setup, monkeypatch, legacy_dependencies, speech=0
    )
    receipt = worker_receipt(client, 0.016 if change == 'subframe' else 0 if change == 'zero' else 1.5)
    if change == 'absent':
        row(client).pop('worker_vad_receipt')
    elif change == 'foreign_audio':
        receipt['input_uri_sha256'] = hashlib.sha256(b'gs://synthetic/other').hexdigest()
    elif change == 'unmeasured':
        receipt['state'] = 'unavailable'
    elif change == 'other_duration':
        receipt['captured_samples'] = 7 * 16000
    modulate.return_value = soniox.return_value = (WORDS, 'vi')
    assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    job = row(client)
    assert job['recovery']['failure'] == {'stage': 'payload_validation', 'reason': 'invalid_payload'}
    assert {p: r['outcome'] for p, r in job['recovery']['recognizers'].items()} == {
        'modulate': 'words',
        'soniox': 'words',
    }
    artifacts.persist_recovery_result.assert_not_called()


def test_independent_redrive_uses_worker_vad_for_words(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, modulate, soniox, _, old = guarded(
        setup, monkeypatch, legacy_dependencies, speech=0, automatic=False
    )
    worker_receipt(client, 1.5)
    soniox.return_value = (WORDS, 'vi')
    outcome = redrive_one(
        store,
        artifacts,
        'bad',
        binding.owner_id,
        'independent-plan',
        old,
        server_flags=SERVING_ENV,
        clock=lambda: 100,
        independent_language=True,
    )
    assert outcome == 'recovered'
    assert row(client)['speech_redrive']['recognizers']['soniox']['word_count'] == 1
    assert_worker_vad_result(client, artifacts.persist_recovery_result.call_args.args[1], 1.5)
    modulate.assert_not_called()
    soniox.assert_called_once()


def accounting(payload):
    """Every speech-accounting input a recovered result feeds: settlement evidence,
    projection usage (per-part and total) and the T2 denominator (part speech)."""
    from dataclasses import fields

    from utils.batch_pipeline.contracts import WorkItem
    from utils.batch_pipeline.projection_parts import split_result
    from utils.batch_pipeline.recovery_disposition import result_vad_evidence

    item = WorkItem(**{f.name: payload['_job'][f.name] for f in fields(WorkItem) if f.name in payload['_job']})
    body = {k: v for k, v in payload.items() if k != '_job'}
    parts = split_result(item, body)
    return {
        'settlement': result_vad_evidence(body),
        'usage_total': body['speech_seconds'],
        'usage_parts': sum(part['speech_seconds'] for _, part in parts),
    }


def test_minimal_worker_frame_never_licenses_long_asr_accounting(setup, monkeypatch, legacy_dependencies):
    """bramp3 39fb29: one 512-sample worker frame, empty CPU VAD and one word spanning
    the whole capture must not become seconds of speech in any accounting field."""
    client, _, binding, artifacts, modulate, _, recovery, _ = guarded(setup, monkeypatch, legacy_dependencies, speech=0)
    worker_receipt(client, 512 / 16000)
    modulate.return_value = ([{'text': 'Synthetic.', 'timestamp': [0, 5], 'speaker': '0'}], 'vi')
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    payload = artifacts.persist_recovery_result.call_args.args[1]
    assert payload['speech_spans'] == [{'start': 0.0, 'end': 0.032}]
    assert accounting({**payload, '_job': row(client)}) == {
        'settlement': pytest.approx(0.032),
        'usage_total': pytest.approx(0.032),
        'usage_parts': pytest.approx(0.032),
    }
    assert row(client)['measured_held_vad_speech_seconds'] == pytest.approx(0.032)
    assert [w['timestamp'] for w in payload['words']] == [[0.0, 5.0]]


@pytest.mark.parametrize('seconds', [0.032, 1.5, 4.384])
@pytest.mark.parametrize('clock', [[1, 2], [0, 5], [4.9, 5]])
def test_worker_vad_fallback_conserves_main_accounting(setup, monkeypatch, legacy_dependencies, seconds, clock):
    """Same audio and receipt: main settles the acoustic census and nothing else; the
    fix adds a transcript but every accounting input equals that same acoustic value."""
    client, _, binding, artifacts, modulate, _, recovery, _ = guarded(setup, monkeypatch, legacy_dependencies, speech=0)
    worker_receipt(client, seconds)
    modulate.return_value = ([{'text': 'Synthetic.', 'timestamp': clock, 'speaker': '0'}], 'vi')
    main_job = deepcopy(row(client))
    with monkeypatch.context() as patch:
        # main: no worker-VAD placement, so the words are rejected.
        patch.setattr('utils.batch_pipeline.quarantine_recovery.worker_vad_speech', lambda job: None)
        assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    main_census = row(client)['measured_held_vad_speech_seconds']
    assert main_census == seconds
    client.rows[('batch_pipeline_prod_jobs', 'bad')] = main_job
    assert recovery.recover('bad', binding.owner_id) == 'recovered'
    payload = artifacts.persist_recovery_result.call_args.args[1]
    assert row(client)['measured_held_vad_speech_seconds'] == pytest.approx(main_census, abs=1e-9)
    assert accounting({**payload, '_job': row(client)}) == {
        key: pytest.approx(main_census, abs=1e-9) for key in ('settlement', 'usage_total', 'usage_parts')
    }


def settled_words_without_vad(setup, monkeypatch, legacy_dependencies, *, soniox_words=False, multilingual=True):
    """The prod settlement before the WordsWithoutVad fix: worker VAD ignored, Modulate
    words rejected, then the capped Soniox call answered empty (10) or words (6)."""
    client, store, binding, artifacts, modulate, soniox, recovery, _ = guarded(
        setup, monkeypatch, legacy_dependencies, speech=0
    )
    monkeypatch.setenv('BATCH_PIPELINE_SPEECH_EMPTY_MULTILINGUAL_ENABLED', str(multilingual).lower())
    worker_receipt(client, 1.5)
    modulate.return_value = (WORDS, 'vi')
    soniox.return_value = (WORDS if soniox_words else [], 'vi')
    with monkeypatch.context() as patch:
        patch.setattr('utils.batch_pipeline.quarantine_recovery.worker_vad_speech', lambda job: None)
        assert recovery.recover('bad', binding.owner_id) == 'failed_held'
    job = row(client)
    assert job['recovery']['failure'] == {'stage': 'payload_validation', 'reason': 'invalid_payload'}
    assert job['recovery']['recognizers']['modulate']['outcome'] == 'words'
    assert job['recovery']['recognizers']['soniox']['outcome'] == ('words' if soniox_words else 'empty')
    artifacts.persist_recovery_result.assert_not_called()
    return client, store, binding, artifacts, modulate, soniox, deepcopy(job['recovery'])


@pytest.mark.parametrize('multilingual', [True, False])
@pytest.mark.parametrize('soniox_words', [False, True])
def test_words_repair_buys_one_modulate_call_for_soniox_empty_or_words_units(
    setup, monkeypatch, legacy_dependencies, multilingual, soniox_words
):
    # Lead a3af50: the 14 Soniox-empty and the 16 Soniox-words units take the same route.
    client, store, binding, artifacts, modulate, soniox, old = settled_words_without_vad(
        setup, monkeypatch, legacy_dependencies, soniox_words=soniox_words, multilingual=multilingual
    )
    args = (store, artifacts, 'bad', binding.owner_id, 'repair-plan', old)
    for expected in ('recovered', 'already_applied'):
        assert redrive_one(*args, server_flags=SERVING_ENV, clock=lambda: 100, repair=True) == expected
    marker = row(client)['speech_redrive']
    assert (marker['provider'], marker['paid_epoch'], marker['state']) == ('modulate', 4, 'completed')
    assert marker['recognizers']['modulate'] == {
        'provider': 'modulate',
        'outcome': 'words',
        'word_count': 1,
        'vad_speech_seconds': 0,
    }
    # The spent intent and both of its receipts are untouched audit facts.
    assert row(client)['recovery'] == old
    assert_worker_vad_result(client, artifacts.persist_recovery_result.call_args.args[1], 1.5)
    assert modulate.call_count == 2
    soniox.assert_called_once()


@pytest.mark.parametrize(
    'change', ['no_receipt', 'subframe_receipt', 'independent_plan', 'both_empty', 'soniox_error', 'epoch4_marker']
)
def test_words_repair_refuses_every_other_unit_without_spend(setup, monkeypatch, legacy_dependencies, change):
    from database.batch_pipeline_projection_protocol import ProjectionBlocked

    client, store, binding, artifacts, modulate, soniox, old = settled_words_without_vad(
        setup, monkeypatch, legacy_dependencies
    )
    receipts = row(client)['recovery']['recognizers']
    if change == 'both_empty':
        receipts['modulate'].update(outcome='empty', word_count=0)
    elif change == 'soniox_error':
        receipts['soniox'].update(outcome='error', word_count=None)
    old = deepcopy(row(client)['recovery'])
    if change == 'epoch4_marker':
        # Any unit already carrying an epoch-4 repair intent never buys another call.
        row(client)['speech_redrive'] = marker = {
            'provider': 'modulate',
            'paid_epoch': 4,
            'state': 'failed_held',
            'token': 'spent-repair-token',
            'plan_digest': 'earlier-repair-plan',
            'privacy_generation': 0,
            'prior_recovery': deepcopy(old),
            'silent': False,
        }
        with pytest.raises(ProjectionBlocked, match='different speech redrive intent'):
            redrive_one(
                store, artifacts, 'bad', binding.owner_id, 'repair-plan', old, server_flags=SERVING_ENV, repair=True
            )
        assert row(client)['speech_redrive'] == marker
        assert modulate.call_count == 1
        return
    if change == 'no_receipt':
        row(client).pop('worker_vad_receipt')
    elif change == 'subframe_receipt':
        worker_receipt(client, 0.016)
    outcome = redrive_one(
        store,
        artifacts,
        'bad',
        binding.owner_id,
        'repair-plan',
        old,
        server_flags=SERVING_ENV,
        repair=True,
        independent_language=change == 'independent_plan',
    )
    assert outcome == 'repair_not_eligible'
    assert not row(client).get('speech_redrive') and row(client)['recovery'] == old
    assert row(client)['recovery_state'] == 'failed_held'
    assert modulate.call_count == 1
    soniox.assert_called_once()


def test_words_repair_is_capped_at_one_call_per_unit(setup, monkeypatch, legacy_dependencies):
    from database.batch_pipeline_projection_protocol import ProjectionBlocked

    client, store, binding, artifacts, modulate, soniox, old = settled_words_without_vad(
        setup, monkeypatch, legacy_dependencies
    )
    modulate.return_value = ([], 'vi')
    args = (store, artifacts, 'bad', binding.owner_id, 'repair-plan', old)
    assert redrive_one(*args, server_flags=SERVING_ENV, clock=lambda: 100, repair=True) == 'failed_held'
    receipt = row(client)['speech_redrive']['recognizers']['modulate']
    assert (receipt['outcome'], receipt['word_count']) == ('empty', 0)
    assert redrive_one(*args, server_flags=SERVING_ENV, clock=lambda: 101, repair=True) == 'failed_held'
    with pytest.raises(ProjectionBlocked, match='different speech redrive intent'):
        redrive_one(store, artifacts, 'bad', binding.owner_id, 'new-plan', old, server_flags=SERVING_ENV, repair=True)
    assert modulate.call_count == 2
    artifacts.persist_recovery_result.assert_not_called()
    # Lead a3af50: a failed repair is ledgered failed_held with its audio retained.
    job = row(client)
    assert (job['state'], job['recovery_state'], job['speech_redrive']['state']) == (
        'quarantined',
        'failed_held',
        'failed_held',
    )
    assert job['speech_redrive']['failure'] == {'stage': 'response_validation', 'reason': 'empty_asr'}
    assert job['audio_uri'] == 'gs://synthetic/audio' and not job.get('result')
    assert not [call for call in artifacts.method_calls if 'delete' in call[0]]


def test_words_repair_leaves_shared_redrive_plans_unchanged(setup, monkeypatch, legacy_dependencies):
    from database.batch_pipeline_projection_protocol import ProjectionBlocked

    client, store, binding, artifacts, modulate, soniox, old = settled_words_without_vad(
        setup, monkeypatch, legacy_dependencies
    )
    args = (store, artifacts, 'bad', binding.owner_id, 'plan', old)
    assert redrive_one(*args, server_flags=SERVING_ENV) == 'independent_plan_required'
    with pytest.raises(ProjectionBlocked, match='already attempted'):
        redrive_one(*args, server_flags=SERVING_ENV, independent_language=True)
    assert not row(client).get('speech_redrive')
    assert modulate.call_count == 1
    soniox.assert_called_once()


def test_operator_repair_census_selects_the_modulate_words_cohort(setup, monkeypatch, legacy_dependencies):
    import importlib.util
    from pathlib import Path

    scripts = Path(__file__).parents[2] / 'scripts'
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location('repair_operator', scripts / 'batch_pipeline_speech_redrive.py')
    operator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(operator)
    client, *_ = settled_words_without_vad(setup, monkeypatch, legacy_dependencies)
    job = deepcopy(row(client))
    job['quarantined_at'] = 50
    assert operator.eligible(job, 0, 100, repair=True)
    assert not operator.eligible(job, 0, 100, independent=True)  # Soniox already spent.
    soniox_words = deepcopy(job)
    soniox_words['recovery']['recognizers']['soniox'].update(outcome='words', word_count=1)
    assert operator.eligible(soniox_words, 0, 100, repair=True)
    both_empty = deepcopy(job)
    both_empty['recovery']['recognizers']['modulate'].update(outcome='empty', word_count=0)
    assert not operator.eligible(both_empty, 0, 100, repair=True)
    assert not operator.eligible({**job, 'speech_redrive': {'paid_epoch': 4}}, 0, 100, repair=True)
    assert operator.paid_digest('census', 1, 4, repair=True) not in {
        operator.paid_digest('census', 1, 4),
        operator.paid_digest('census', 1, 4, independent=True),
    }


@pytest.mark.parametrize('fault', ['decoded_over_cap', 'missing_audio_uri'])
def test_words_repair_bounds_decoded_audio_and_fails_closed_on_malformed_jobs(
    setup, monkeypatch, legacy_dependencies, fault
):
    from config.batch_language_recovery import words_repair_eligible

    client, store, binding, artifacts, modulate, soniox, old = settled_words_without_vad(
        setup, monkeypatch, legacy_dependencies
    )
    if fault == 'missing_audio_uri':
        job = deepcopy(row(client))
        job.pop('audio_uri')
        assert not words_repair_eligible(job)
        return
    monkeypatch.setattr('utils.batch_pipeline.speech_redrive.MAX_AUDIO_SECONDS', 4.99)
    outcome = redrive_one(
        store, artifacts, 'bad', binding.owner_id, 'repair-plan', old, server_flags=SERVING_ENV, repair=True
    )
    assert outcome == 'repair_budget_held'
    assert row(client)['speech_redrive']['state'] == 'prepared'
    assert modulate.call_count == 1
