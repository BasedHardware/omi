"""Paid redrive artifact writes cross the real retention/privacy transaction."""

from copy import deepcopy

import pytest

from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_speech_redrive import SpeechRedriveStore
from tests.unit.test_batch_language_recovery import guarded
from tests.unit.test_batch_pipeline_empty_disposition import SERVING_ENV
from tests.unit.test_batch_pipeline_quarantine_recovery import legacy_dependencies, row, setup
from utils.batch_pipeline.retention import register_batch_artifact


def running_independent(setup, monkeypatch, legacy_dependencies, *, multilingual=True):
    client, store, binding, _, _, soniox, _, old = guarded(setup, monkeypatch, legacy_dependencies, automatic=False)
    monkeypatch.setenv('BATCH_PIPELINE_SPEECH_EMPTY_MULTILINGUAL_ENABLED', str(multilingual).lower())
    protocol = SpeechRedriveStore(store, server_flags=SERVING_ENV)
    token = protocol.prepare('bad', binding.owner_id, 'independent-plan', old, 100)['speech_redrive']['token']
    assert protocol.start('bad', token, 'independent-plan', 101)
    assert row(client)['speech_redrive']['paid_epoch'] == 3
    assert row(client)['speech_redrive']['provider'] == 'soniox'
    return client, store, binding, token, soniox


@pytest.mark.parametrize('multilingual', [True, False])
def test_running_epoch3_registers_result_under_its_current_privacy_token(
    setup, monkeypatch, legacy_dependencies, multilingual
):
    client, store, binding, token, soniox = running_independent(
        setup, monkeypatch, legacy_dependencies, multilingual=multilingual
    )
    before = deepcopy(row(client))
    uri = f'gs://synthetic/results/bad/{token}.enc'
    register_batch_artifact(store, binding.owner_id, 'bad', uri, 'results', 0)
    artifacts = [value for key, value in client.rows.items() if key[0] == 'batch_pipeline_prod_artifacts']
    assert len(artifacts) == 1
    assert artifacts[0]['uri'] == uri
    assert artifacts[0]['owner_id'] == binding.owner_id
    assert artifacts[0]['privacy_generation'] == 0
    assert row(client)['recovery'] == before['recovery']
    assert row(client)['speech_redrive'] == before['speech_redrive']
    soniox.assert_not_called()


@pytest.mark.parametrize(
    'change',
    [
        'provider',
        'prior_provider',
        'future_epoch',
        'privacy',
        'token',
        'not_running',
        'not_language_guarded',
        'recovery_disabled',
    ],
)
def test_epoch3_registration_rejects_foreign_or_unsupported_intent(setup, monkeypatch, legacy_dependencies, change):
    client, store, binding, token, _ = running_independent(setup, monkeypatch, legacy_dependencies)
    job = row(client)
    if change == 'provider':
        job['speech_redrive']['provider'] = 'modulate'
    elif change == 'prior_provider':
        job['recovery']['provider'] = 'soniox'
    elif change == 'future_epoch':
        job['speech_redrive']['paid_epoch'] = 4
    elif change == 'privacy':
        job['speech_redrive']['privacy_generation'] = 1
    elif change == 'token':
        job['speech_redrive']['token'] = 'foreign-token'
    elif change == 'not_running':
        job['speech_redrive']['state'] = 'prepared'
    elif change == 'not_language_guarded':
        job['worker_failure']['reason'] = 'empty_asr'
    else:
        job['policy_parts']['recovery']['recovery_enabled'] = False
    with pytest.raises(BatchPrivacyBlocked, match='result_lease_lost'):
        register_batch_artifact(store, binding.owner_id, 'bad', f'gs://synthetic/results/bad/{token}.enc', 'results', 0)
    assert not [key for key in client.rows if key[0] == 'batch_pipeline_prod_artifacts']


@pytest.mark.parametrize('multilingual', [True, False])
@pytest.mark.parametrize('cohort', ['soniox_empty', 'soniox_words', 'both_empty'])
def test_running_words_repair_registers_only_its_eligible_result(
    setup, monkeypatch, legacy_dependencies, multilingual, cohort
):
    from tests.unit.test_batch_language_recovery import settled_words_without_vad

    client, store, binding, _, _, _, old = settled_words_without_vad(
        setup, monkeypatch, legacy_dependencies, multilingual=multilingual, soniox_words=cohort == 'soniox_words'
    )
    protocol = SpeechRedriveStore(store, server_flags=SERVING_ENV)
    token = protocol.prepare('bad', binding.owner_id, 'repair-plan', old, 100, repair=True)['speech_redrive']['token']
    assert protocol.start('bad', token, 'repair-plan', 101)
    assert (row(client)['speech_redrive']['paid_epoch'], row(client)['speech_redrive']['provider']) == (4, 'modulate')
    uri = f'gs://synthetic/results/bad/{token}.enc'
    if cohort == 'both_empty':
        row(client)['recovery']['recognizers']['modulate'].update(outcome='empty', word_count=0)
        with pytest.raises(BatchPrivacyBlocked, match='result_lease_lost'):
            register_batch_artifact(store, binding.owner_id, 'bad', uri, 'results', 0)
        return
    register_batch_artifact(store, binding.owner_id, 'bad', uri, 'results', 0)
    assert [v['uri'] for k, v in client.rows.items() if k[0] == 'batch_pipeline_prod_artifacts'] == [uri]
