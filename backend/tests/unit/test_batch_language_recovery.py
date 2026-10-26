"""Synthetic language-guard recovery, paid-intent fencing and measured receipts."""

from copy import deepcopy
from unittest.mock import Mock, AsyncMock

import pytest

from config.batch_language_recovery import allowed, below_silence_threshold
from database.batch_pipeline_recognizer_receipts import record_recognizer
from database.batch_pipeline_speech_redrive import SpeechRedriveStore
from tests.unit.test_batch_pipeline_quarantine_recovery import setup, legacy_dependencies, row
from tests.unit.test_batch_pipeline_speech_redrive import enabled
from tests.unit.test_batch_pipeline_empty_disposition import SERVING_ENV
from utils.batch_pipeline.recovery_recognizers import transcribe
from utils.batch_pipeline.recovery_disposition import RecoveryFailure, independent_silence_payload, result_outcome
from utils.batch_pipeline.speech_redrive import redrive_one

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


@pytest.mark.parametrize('case', ['disabled', 'cap', 'allowance', 'empty', 'error', 'words_without_vad'])
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
    elif case == 'words_without_vad':
        soniox.return_value = (WORDS, 'vi')
    expected = 'held' if case in {'disabled', 'cap', 'allowance'} else 'failed_held'
    assert recovery.recover('bad', binding.owner_id) == expected
    final = row(client)
    assert final['measured_held_vad_speech_seconds'] == 2
    assert final['worker_vad_receipt'] == receipt
    artifacts.persist_recovery_result.assert_not_called()
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
