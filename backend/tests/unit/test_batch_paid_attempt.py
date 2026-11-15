"""Operator failures retain one bounded retry; validated answers spend it."""

from copy import deepcopy
from unittest.mock import Mock

import pytest

from tests.unit.test_batch_pipeline_quarantine_recovery import setup, legacy_dependencies, row
from tests.unit.test_batch_pipeline_speech_redrive import enabled
from tests.unit.test_batch_pipeline_empty_disposition import SERVING_ENV
from utils.batch_pipeline.speech_redrive import redrive_one
from utils.batch_pipeline.recovery_disposition import RecoveryFailure, MultilingualEmpty
from tests.unit.test_batch_pipeline_prepared_independent import prepared_setup, load_operator
from utils.batch_pipeline.speech_redrive import prepared_independent_one
from database.batch_pipeline_speech_redrive import SpeechRedriveStore


def run(store, artifacts, binding, old, stt):
    return redrive_one(
        store,
        artifacts,
        'bad',
        binding.owner_id,
        'plan',
        old,
        server_flags=SERVING_ENV,
        clock=lambda: 100,
        stt=stt,
        retry_failed=True,
    )


def test_provider_refusal_precedes_intent(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, _, _, old = enabled(setup, monkeypatch, legacy_dependencies)
    monkeypatch.setattr('utils.batch_pipeline.speech_redrive.sync_allowed', lambda *a, **k: False)
    stt = Mock()
    assert run(store, artifacts, binding, old, stt) == 'allowance_held'
    assert not row(client).get('speech_redrive')
    stt.assert_not_called()


def test_open_vendor_breaker_refuses_before_intent(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, _, _, old = enabled(setup, monkeypatch, legacy_dependencies)
    monkeypatch.setattr('utils.batch_pipeline.speech_redrive.breaker_refuses', lambda _: True)
    stt = Mock()
    assert run(store, artifacts, binding, old, stt) == 'provider_held'
    assert not row(client).get('speech_redrive')
    stt.assert_not_called()


def test_provider_error_retains_exactly_one_retry(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, _, _, old = enabled(setup, monkeypatch, legacy_dependencies)
    stt = Mock(side_effect=RecoveryFailure('provider', 'provider_failed'))
    assert run(store, artifacts, binding, old, stt) == 'failed_held'
    first = row(client)['speech_redrive'].copy()
    assert first['paid_state'] == 'attempted' and first['attempt_count'] == 1
    assert run(store, artifacts, binding, old, stt) == 'failed_held'
    second = row(client)['speech_redrive']
    assert second['token'] != first['token']
    assert second['attempt_count'] == 2 and second['paid_state'] == 'attempted'
    assert second['attempt_history'][0]['token'] == first['token']
    assert run(store, artifacts, binding, old, stt) == 'failed_held'
    assert stt.call_count == 2
    assert row(client)['state'] == 'quarantined' and not row(client).get('result')


def test_validated_empty_is_spent_and_never_retried(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, _, _, old = enabled(setup, monkeypatch, legacy_dependencies)
    stt = Mock(side_effect=MultilingualEmpty(3, [{'start': 1, 'end': 2}]))
    assert run(store, artifacts, binding, old, stt) == 'failed_held'
    assert row(client)['speech_redrive']['paid_state'] == 'spent'
    assert run(store, artifacts, binding, old, stt) == 'failed_held'
    stt.assert_called_once()


def test_takeover_error_retries_once_with_new_fence(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, _, _, soniox = prepared_setup(setup, monkeypatch, legacy_dependencies)
    module = load_operator()
    seal = module.fingerprint(row(client), prepared=True)
    soniox.side_effect = TimeoutError('synthetic')
    for _ in range(3):
        assert (
            prepared_independent_one(
                store,
                artifacts,
                'bad',
                binding.owner_id,
                190,
                server_flags=SERVING_ENV,
                clock=lambda: 100,
            )
            == 'failed_held'
        )
    marker = row(client)['recovery']
    assert marker['paid_state'] == 'attempted' and marker['attempt_count'] == 2
    assert marker['token'] != marker['original_token']
    assert module.fingerprint(row(client), prepared=True) == seal
    assert soniox.call_count == 2


def test_retry_token_fences_late_success_and_cas(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, _, _, old = enabled(setup, monkeypatch, legacy_dependencies)
    stt = Mock(side_effect=RecoveryFailure('provider', 'provider_failed'))
    run(store, artifacts, binding, old, stt)
    protocol = SpeechRedriveStore(store, server_flags=SERVING_ENV, max_attempts=2)
    first = deepcopy(row(client)['speech_redrive'])
    second = protocol.prepare('bad', binding.owner_id, 'plan', old, 101)['speech_redrive']
    assert second['token'] != first['token']
    assert protocol.start('bad', second['token'], 'plan', 102)
    assert not protocol.start('bad', second['token'], 'plan', 102)
    assert not protocol.settle('bad', first['token'], 'plan', 103, 'gs://synthetic/late')


def test_historical_failure_without_attempt_marker_never_reopens(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, _, _, old = enabled(setup, monkeypatch, legacy_dependencies)
    stt = Mock(side_effect=RecoveryFailure('provider', 'provider_failed'))
    run(store, artifacts, binding, old, stt)
    row(client)['speech_redrive'].pop('paid_state')
    assert run(store, artifacts, binding, old, stt) == 'failed_held'
    stt.assert_called_once()


def test_retry_refusal_preserves_failed_receipt(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, _, _, old = enabled(setup, monkeypatch, legacy_dependencies)
    stt = Mock(side_effect=RecoveryFailure('provider', 'provider_failed'))
    run(store, artifacts, binding, old, stt)
    marker = deepcopy(row(client)['speech_redrive'])
    monkeypatch.setattr('utils.batch_pipeline.speech_redrive.sync_allowed', lambda *a, **k: False)
    assert run(store, artifacts, binding, old, stt) == 'allowance_held'
    assert row(client)['speech_redrive'] == marker
    stt.assert_called_once()


def test_retry_cost_is_bound_into_plan_and_cap():
    module = load_operator()
    assert module.paid_digest('census', 1, 2, retry_failed=True) != module.paid_digest('census', 1, 2)
    with pytest.raises(module.held.Refused, match='spend_cap_exceeded'):
        module.prepared_budget([600], 0.02, max_attempts=2)
    with pytest.raises(module.held.Refused, match='ordinary_empty_audio_budget'):
        module.ordinary_empty_budget([24], max_attempts=2)
