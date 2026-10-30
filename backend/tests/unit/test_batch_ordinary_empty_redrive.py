"""Exact operator Soniox recovery preserves both spent Modulate intents."""

from copy import deepcopy
import json
from unittest.mock import Mock

import pytest

from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_policy import load_stage_policy
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_speech_redrive import SpeechRedriveStore, ordinary_empty_redrive
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument
from tests.unit.test_batch_language_recovery import guarded, worker_receipt, WORDS
from tests.unit.test_batch_pipeline_empty_disposition import SERVING_ENV
from tests.unit.test_batch_pipeline_quarantine_recovery import setup, legacy_dependencies, row  # noqa: F401
from tests.unit.test_batch_speech_redrive_census import operator
from utils.batch_pipeline import speech_redrive


def ordinary(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, modulate, soniox, _, original = guarded(
        setup, monkeypatch, legacy_dependencies, speech=0, automatic=False
    )
    job = row(client)
    job['worker_failure'] = {'stage': 'assemble_words', 'reason': 'empty_asr'}
    job['quarantined_at'] = 10
    worker_receipt(client, 1.5)
    previous = {
        'provider': 'modulate',
        'paid_epoch': 2,
        'state': 'failed_held',
        'token': 'synthetic-spent-epoch2',
        'plan_digest': 'synthetic-spent-plan',
        'started_at': 3,
        'settled_at': 4,
        'privacy_generation': 0,
        'silent': True,
        'prior_recovery': deepcopy(original),
        'failure': {'stage': 'response_validation', 'reason': 'empty_asr'},
    }
    job['speech_redrive'] = deepcopy(previous)
    return client, store, binding, artifacts, modulate, soniox, original, previous


def dispatch(store, artifacts, binding, original, **kwargs):
    return speech_redrive.redrive_one(
        store,
        artifacts,
        'bad',
        binding.owner_id,
        'reviewed-ordinary-empty',
        original,
        server_flags=SERVING_ENV,
        silent=True,
        ordinary_empty_independent=True,
        clock=lambda: 100,
        **kwargs,
    )


@pytest.mark.parametrize('words', [False, True])
def test_worker_positive_cpu_zero_buys_one_soniox_and_preserves_both_spent_intents(
    setup, monkeypatch, legacy_dependencies, words
):
    client, store, binding, artifacts, modulate, soniox, original, previous = ordinary(
        setup, monkeypatch, legacy_dependencies
    )
    soniox.return_value = (WORDS if words else [], 'vi')
    assert ordinary_empty_redrive(row(client))
    expected = 'recovered' if words else 'failed_held'
    assert dispatch(store, artifacts, binding, original) == expected
    job = row(client)
    marker = job['speech_redrive']
    assert job['recovery'] == original
    assert marker['prior_recovery'] == original and marker['prior_speech_redrive'] == previous
    assert marker['provider'] == 'soniox' and marker['paid_epoch'] == 3
    assert marker['ordinary_empty_independent'] is True and marker['silent'] is True
    assert marker['recognizers']['modulate']['outcome'] == 'empty'
    assert marker['recognizers']['soniox']['outcome'] == ('words' if words else 'empty')
    assert dispatch(store, artifacts, binding, original) == ('already_applied' if words else 'failed_held')
    soniox.assert_called_once()
    modulate.assert_not_called()
    if words:
        payload = artifacts.persist_recovery_result.call_args.args[1]
        assert payload['words'] and payload['speech_seconds'] == 1.5
        assert payload['speech_spans'] == [{'start': 1.0, 'end': 2.5}]
    else:
        assert job['state'] == 'quarantined' and not job.get('result')
        assert job['measured_held_vad_speech_seconds'] == 1.5
        artifacts.persist_recovery_result.assert_not_called()


@pytest.mark.parametrize(
    'change',
    [
        'guarded',
        'not_empty',
        'missing_worker',
        'foreign_worker',
        'subframe',
        'unspent_epoch2',
        'not_settled',
        'nonempty_epoch2',
        'prior_changed',
        'prior_not_silent',
        'privacy_receipt_changed',
        'already_soniox',
    ],
)
def test_ordinary_route_refuses_unproven_or_nonordinary_prior_before_soniox(
    setup, monkeypatch, legacy_dependencies, change
):
    client, store, binding, artifacts, modulate, soniox, original, _ = ordinary(setup, monkeypatch, legacy_dependencies)
    job = row(client)
    if change == 'guarded':
        job['worker_failure'] = {'stage': 'vad_windows', 'reason': 'unsupported_language'}
    elif change == 'not_empty':
        job['worker_failure']['reason'] = 'no_owned_words'
    elif change == 'missing_worker':
        job.pop('worker_vad_receipt')
    elif change == 'foreign_worker':
        job['worker_vad_receipt']['input_uri_sha256'] = '0' * 64
    elif change == 'subframe':
        worker_receipt(client, 0.016)
    elif change == 'unspent_epoch2':
        job['speech_redrive']['state'] = 'prepared'
        job['speech_redrive'].pop('started_at')
    elif change == 'not_settled':
        job['speech_redrive'].pop('settled_at')
    elif change == 'nonempty_epoch2':
        job['speech_redrive']['failure'] = {'stage': 'payload_validation', 'reason': 'invalid_payload'}
    elif change == 'prior_changed':
        job['speech_redrive']['prior_recovery']['token'] = 'foreign-original'
    elif change == 'prior_not_silent':
        job['speech_redrive']['silent'] = False
    elif change == 'privacy_receipt_changed':
        job['speech_redrive']['privacy_generation'] = 1
    else:
        job['recovery']['recognizers'] = {'soniox': {'outcome': 'empty', 'word_count': 0}}
        original = deepcopy(job['recovery'])
        job['speech_redrive']['prior_recovery'] = deepcopy(original)
    previous = deepcopy(job['speech_redrive'])
    assert not ordinary_empty_redrive(job)
    assert dispatch(store, artifacts, binding, original) == 'ordinary_empty_not_eligible'
    assert row(client)['speech_redrive'] == previous
    modulate.assert_not_called()
    soniox.assert_not_called()
    artifacts.fetch_audio.assert_not_called()


@pytest.mark.parametrize('fence', ['not_held', 'lease', 'result', 'completed_ledger', 'privacy'])
def test_ordinary_route_keeps_terminal_ownership_privacy_and_lease_fences(
    setup, monkeypatch, legacy_dependencies, fence
):
    client, store, binding, artifacts, modulate, soniox, original, previous = ordinary(
        setup, monkeypatch, legacy_dependencies
    )
    if fence == 'not_held':
        row(client)['state'] = 'ready'
    elif fence == 'lease':
        row(client)['lease_until'] = 1000
    elif fence == 'result':
        row(client)['result'] = {'outcome': 'success'}
    elif fence == 'completed_ledger':
        client.rows[('users', binding.owner_id, 'sync_content_ledger', binding.content_id)]['status'] = 'completed'
    else:
        client.rows[('users', binding.owner_id)]['migration_status'] = 'pending'
    with pytest.raises((ProjectionBlocked, BatchPrivacyBlocked)):
        dispatch(store, artifacts, binding, original)
    assert row(client)['speech_redrive'] == previous
    soniox.assert_not_called()
    modulate.assert_not_called()


def test_ordinary_route_does_not_bypass_funding(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, modulate, soniox, original, previous = ordinary(
        setup, monkeypatch, legacy_dependencies
    )
    monkeypatch.setattr(speech_redrive, 'sync_allowed', lambda *a, **kw: False)
    assert dispatch(store, artifacts, binding, original) == 'allowance_held'
    marker = row(client)['speech_redrive']
    assert marker['state'] == 'prepared' and not marker.get('started_at')
    assert marker['prior_speech_redrive'] == previous
    soniox.assert_not_called()
    modulate.assert_not_called()


def test_census_uses_bound_worker_proof_readonly_and_preserves_fingerprint_on_prepare(
    setup, monkeypatch, legacy_dependencies
):
    client, store, binding, artifacts, modulate, soniox, original, previous = ordinary(
        setup, monkeypatch, legacy_dependencies
    )
    module = operator(monkeypatch)
    transaction = client.transaction
    monkeypatch.setattr(client, 'transaction', lambda **kwargs: transaction())
    key = module.fingerprint(row(client), ordinary_empty=True)
    before = deepcopy(client.rows)
    assert module.eligible(row(client), 0, 20, ordinary_empty=True)
    assert module.inspect_unit(store, artifacts, 'bad', binding.owner_id, key, ordinary_empty=True) == 'speech'
    assert client.rows == before
    artifacts.fetch_audio.assert_not_called()
    protocol = SpeechRedriveStore(store, server_flags=SERVING_ENV)
    prepared = protocol.prepare(
        'bad',
        binding.owner_id,
        'reviewed-ordinary-empty',
        original,
        99,
        silent=True,
        ordinary_empty_independent=True,
    )
    assert prepared['speech_redrive']['prior_speech_redrive'] == previous
    assert module.fingerprint(row(client), ordinary_empty=True) == key
    # A fresh cohort cannot adopt a prepared/spent Soniox intent; only the
    # immutable original cohort may reconcile/replay that same plan.
    assert not module.eligible(row(client), 0, 20, ordinary_empty=True)
    assert module.inspect_unit(store, artifacts, 'bad', binding.owner_id, key, ordinary_empty=True) == 'speech'
    modulate.assert_not_called()
    soniox.assert_not_called()


@pytest.mark.parametrize('change', ['worker', 'worker_failure', 'paid_plan'])
def test_census_refuses_changed_valid_proof_or_paid_history(setup, monkeypatch, legacy_dependencies, change):
    client, store, binding, artifacts, modulate, soniox, _, _ = ordinary(setup, monkeypatch, legacy_dependencies)
    module = operator(monkeypatch)
    transaction = client.transaction
    monkeypatch.setattr(client, 'transaction', lambda **kwargs: transaction())
    key = module.fingerprint(row(client), ordinary_empty=True)
    if change == 'worker':
        worker_receipt(client, 2)
    elif change == 'worker_failure':
        row(client)['worker_failure']['synthetic_diagnostic'] = 1
    else:
        row(client)['speech_redrive']['plan_digest'] = 'different-spent-plan'
    assert ordinary_empty_redrive(row(client))
    with pytest.raises(module.held.Refused, match='cohort_changed'):
        module.inspect_unit(store, artifacts, 'bad', binding.owner_id, key, ordinary_empty=True)
    modulate.assert_not_called()
    soniox.assert_not_called()
    artifacts.fetch_audio.assert_not_called()


@pytest.mark.parametrize(
    'durations,reason',
    [
        ([], 'ordinary_empty_unit_budget'),
        ([1, 1, 1], 'ordinary_empty_unit_budget'),
        ([True], 'ordinary_empty_duration_invalid'),
        ([-1], 'ordinary_empty_duration_invalid'),
        ([float('nan')], 'ordinary_empty_duration_invalid'),
        ([float('inf')], 'ordinary_empty_duration_invalid'),
        ([60.01], 'ordinary_empty_duration_invalid'),
        ([24, 24], 'ordinary_empty_audio_budget'),
        ([23.8, 23.8], 'ordinary_empty_audio_budget'),
    ],
)
def test_census_refuses_overbudget_or_unmeasured_audio(monkeypatch, durations, reason):
    module = operator(monkeypatch)
    with pytest.raises(module.held.Refused, match=reason):
        module.ordinary_empty_budget(durations)


def test_actual_two_unit_budget_and_new_operation_digest(monkeypatch):
    module = operator(monkeypatch)
    assert module.ordinary_empty_budget([6.4294375, 10.66]) == pytest.approx((17.0894375, 17.2894375))
    assert module.ordinary_empty_budget([47.5]) == pytest.approx((47.5, 47.6))
    assert module.ordinary_empty_budget([23.7, 23.7]) == pytest.approx((47.4, 47.6))
    ordinary_digest = module.paid_digest('synthetic-census', 1, 3, silent=True, ordinary_empty=True)
    assert ordinary_digest != module.paid_digest('synthetic-census', 1, 3, silent=True, independent=True)
    assert ordinary_digest != module.paid_digest('different-census', 1, 3, silent=True, ordinary_empty=True)


@pytest.mark.parametrize(
    'extra,reason',
    [
        ([], 'exact_ordinary_empty_units_required'),
        (['--unit-ids-file', 'unread-synthetic.json'], 'ordinary_empty_requires_silent'),
        (
            [
                '--unit-ids-file',
                'unread-synthetic.json',
                '--silent',
                '--expect-count',
                '3',
                '--expect-speech-count',
                '3',
            ],
            'ordinary_empty_unit_budget',
        ),
        (['--independent-language'], 'conflicting_plans'),
        (['--paid-epoch', '2'], 'provider_epoch_mismatch'),
    ],
)
def test_cli_refuses_unscoped_nonsilent_or_conflicting_mode_before_runtime_io(monkeypatch, extra, reason):
    module = operator(monkeypatch)
    args = [
        'batch_pipeline_speech_redrive.py',
        '--stage',
        'prod',
        '--quarantined-after',
        '2026-01-01T00:00:00Z',
        '--quarantined-before',
        '2026-01-02T00:00:00Z',
        '--cohort-file',
        'unwritten-synthetic-cohort.json',
        '--expect-count',
        '1',
        '--expect-speech-count',
        '1',
        '--paid-epoch',
        '3',
        '--ordinary-empty-independent',
        *extra,
    ]
    monkeypatch.setattr(module.sys, 'argv', args)
    client = Mock(side_effect=AssertionError('runtime client must not be constructed'))
    monkeypatch.setattr(module.firestore, 'Client', client)
    with pytest.raises(module.held.Refused, match=reason):
        module.main()
    client.assert_not_called()


def test_ordinary_soniox_start_is_cas_and_new_digest_cannot_replace_it(setup, monkeypatch, legacy_dependencies):
    client, store, binding, _, modulate, soniox, original, previous = ordinary(setup, monkeypatch, legacy_dependencies)
    protocol = SpeechRedriveStore(store, server_flags=SERVING_ENV)
    job = protocol.prepare(
        'bad',
        binding.owner_id,
        'reviewed-ordinary-empty',
        original,
        99,
        silent=True,
        ordinary_empty_independent=True,
    )
    token = job['speech_redrive']['token']
    with pytest.raises(ProjectionBlocked, match='different speech redrive intent'):
        protocol.prepare(
            'bad',
            binding.owner_id,
            'unapproved-other-plan',
            original,
            100,
            silent=True,
            ordinary_empty_independent=True,
        )
    assert protocol.start('bad', token, 'reviewed-ordinary-empty', 100)
    assert not protocol.start('bad', token, 'reviewed-ordinary-empty', 101)
    assert row(client)['speech_redrive']['prior_speech_redrive'] == previous
    modulate.assert_not_called()
    soniox.assert_not_called()


def test_ordinary_soniox_lost_write_reconciles_only_its_own_artifact(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, modulate, soniox, original, previous = ordinary(
        setup, monkeypatch, legacy_dependencies
    )
    soniox.return_value = (WORDS, 'vi')
    artifacts.find_recovery_result.return_value = None
    artifacts.persist_recovery_result.side_effect = RuntimeError('synthetic lost write')
    with pytest.raises(RuntimeError, match='synthetic lost write'):
        dispatch(store, artifacts, binding, original)
    payload = artifacts.persist_recovery_result.call_args.args[1]
    assert dispatch(store, artifacts, binding, original) == 'running_held'
    artifacts.find_recovery_result.return_value = 'gs://synthetic/reconciled'
    artifacts.load_result.return_value = payload
    assert dispatch(store, artifacts, binding, original) == 'reconciled'
    assert row(client)['speech_redrive']['prior_speech_redrive'] == previous
    assert row(client)['result']['outcome'] == 'success'
    soniox.assert_called_once()
    modulate.assert_not_called()


def test_canonical_cli_new_mode_dryrun_apply_and_same_plan_replay(
    setup, monkeypatch, legacy_dependencies, tmp_path, capsys
):
    client, store, binding, artifacts, modulate, soniox, original, previous = ordinary(
        setup, monkeypatch, legacy_dependencies
    )
    # The historical epoch2 already consumed this serving-owned policy part.
    load_stage_policy(store, 'bad', 'recovery', server_flags=SERVING_ENV)
    module = operator(monkeypatch)
    monkeypatch.setattr(module.firestore, 'Client', lambda **kw: client)
    document_get = StrictFirestoreDocument.get

    def identified_snapshot(document, *args, **kwargs):
        snapshot = document_get(document, *args, **kwargs)
        snapshot.id = document.id
        return snapshot

    monkeypatch.setattr(StrictFirestoreDocument, 'get', identified_snapshot)
    monkeypatch.setattr(module.storage, 'Client', lambda **kw: None)
    monkeypatch.setattr(module, 'create_artifact_store', lambda *a: artifacts)
    monkeypatch.setattr(module, 'configure_rollout_runtime', lambda: None)
    transaction = client.transaction
    monkeypatch.setattr(client, 'transaction', lambda **kw: transaction())
    monkeypatch.setenv('GCP_AGENT_TIER', 'ro-prod')
    monkeypatch.setenv('SYNTHETIC_PLAN_OWNER', binding.owner_id)
    monkeypatch.setenv('ENCRYPTION_SECRET', 'synthetic-runtime-material-only-00000000')
    monkeypatch.setenv('BUCKET_BATCH_PIPELINE', 'synthetic-no-network')
    ids, cohort = tmp_path / 'ids.json', tmp_path / 'cohort.json'
    ids.write_text(json.dumps(['bad']))
    args = [
        'operator',
        '--stage',
        'prod',
        '--owner-env',
        'SYNTHETIC_PLAN_OWNER',
        '--quarantined-after',
        '1970-01-01T00:00:01Z',
        '--quarantined-before',
        '1970-01-01T00:00:20Z',
        '--cohort-file',
        str(cohort),
        '--unit-ids-file',
        str(ids),
        '--expect-count',
        '1',
        '--expect-speech-count',
        '1',
        '--paid-epoch',
        '3',
        '--silent',
        '--ordinary-empty-independent',
    ]
    monkeypatch.setattr(module.sys, 'argv', args)
    before = deepcopy(client.rows)
    module.main()
    plan = json.loads(capsys.readouterr().out)
    assert client.rows == before and cohort.stat().st_mode & 0o777 == 0o600
    assert plan['provider'] == 'soniox' and plan['operation'] == 'ordinary-empty-independent-recovery-v2'
    assert plan['strict_vad'] == {'worker_vad_speech': 1}
    assert plan['maximum_additional_paid_calls'] == 1 and plan['total_recorded_audio_seconds'] == 5
    assert plan['maximum_possible_decoded_audio_seconds'] == pytest.approx(5.1)
    assert plan['paid_stt_calls'] == plan['firestore_writes'] == 0
    artifacts.fetch_audio.assert_not_called()
    soniox.assert_not_called()
    soniox.return_value = (WORDS, 'vi')
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    apply_args = args + [
        '--apply',
        '--source-census-sha256',
        plan['source_census_sha256'],
        '--approve-plan-sha256',
        plan['plan_sha256'],
        '--apply-limit',
        '1',
    ]
    monkeypatch.setattr(module.sys, 'argv', apply_args)
    module.main()
    assert json.loads(capsys.readouterr().out)['outcomes'] == {'recovered': 1}
    assert row(client)['speech_redrive']['prior_speech_redrive'] == previous
    assert row(client)['recovery'] == original
    module.main()
    assert json.loads(capsys.readouterr().out)['outcomes'] == {'already_applied': 1}
    soniox.assert_called_once()
    modulate.assert_not_called()
