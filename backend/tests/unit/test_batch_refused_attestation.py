"""A historical no-call plan needs recorded vendor evidence and cannot apply."""

from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.unit.test_batch_pipeline_quarantine_recovery import setup, legacy_dependencies, row
from tests.unit.test_batch_pipeline_prepared_independent import prepared_setup, load_operator
from utils.batch_pipeline import redrive_scope as scope
from utils.batch_pipeline.refused_attestation import checked_proof, refused_candidate


def proof_for(spec):
    return dict(
        version=1,
        vendor='soniox',
        source='vendor_usage_export',
        files_created=0,
        complete=True,
        window_start='2026-11-02T02:21:00Z',
        window_end='2026-11-02T02:38:00Z',
        recorded_at='2026-11-02T04:00:00Z',
        usage_evidence_sha256='a' * 64,
        apply_log_sha256='b' * 64,
        scope_sha256=scope.digest(spec),
    )


@pytest.mark.parametrize(
    'change', ['nonzero', 'boolean_zero', 'incomplete', 'source', 'scope', 'window', 'no_evidence']
)
def test_proof_refuses_missing_or_contradictory_evidence(change):
    proof = proof_for({})
    if change == 'nonzero':
        proof['files_created'] = 1
    if change == 'boolean_zero':
        proof['files_created'] = False
    if change == 'incomplete':
        proof['complete'] = False
    if change == 'source':
        proof['source'] = 'operator_guess'
    if change == 'scope':
        proof['scope_sha256'] = 'c' * 64
    if change == 'window':
        proof['recorded_at'] = '2026-11-02T02:00:00Z'
    if change == 'no_evidence':
        proof['usage_evidence_sha256'] = ''
    with pytest.raises(scope.ScopeRefused):
        checked_proof(proof, {})


def test_cli_attestation_apply_refuses_before_cloud_or_secret_requirements(monkeypatch):
    module = load_operator()
    cloud = Mock(side_effect=AssertionError('cloud must not be constructed'))
    monkeypatch.setattr(module.firestore, 'Client', cloud)
    monkeypatch.setattr(
        module.sys,
        'argv',
        [
            'operator',
            '--stage',
            'prod',
            '--quarantined-after',
            '2026-11-01T00:00:00Z',
            '--quarantined-before',
            '2026-11-02T00:00:00Z',
            '--cohort-file',
            'unused',
            '--unit-ids-file',
            'unused',
            '--expect-count',
            '4',
            '--expect-speech-count',
            '4',
            '--paid-epoch',
            '3',
            '--independent-language',
            '--attest-refused-before-call',
            '--apply',
        ],
    )
    with pytest.raises(module.held.Refused, match='attestation_apply_not_supported'):
        module.main()
    cloud.assert_not_called()


def test_attested_takeover_dry_run_never_writes_or_fetches_audio(
    setup, monkeypatch, legacy_dependencies, tmp_path, capsys
):
    client, store, binding, artifacts, legacy, alternate, soniox = prepared_setup(
        setup, monkeypatch, legacy_dependencies
    )
    module = load_operator()
    job = row(client)
    window = checked_proof(proof_for({}), {})
    job['recovery_state'] = 'failed_held'
    job['recovery'].update(
        provider='modulate',
        started_at=window[0] + 10,
        settled_at=window[0] + 11,
        failure={'stage': 'provider', 'reason': 'provider_failed'},
        recognizers={'soniox': {'provider': 'soniox', 'outcome': 'error', 'word_count': None}},
    )
    spec = scope.scope_body(binding.owner_id, 'batch_pipeline_prod', 50, 200, False, ['bad'])
    proof_path = tmp_path / 'proof.json'
    proof_path.write_text(json.dumps(proof_for(spec)))
    args = SimpleNamespace(
        apply=False,
        zero_vendor_files_proof=str(proof_path),
        prepared_independent=True,
        independent_language=False,
        expect_count=1,
        expect_speech_count=1,
        max_seconds=190,
        usd_cap=1,
        source_census_sha256=None,
        cohort_file=str(tmp_path / 'cohort.json'),
    )
    monkeypatch.setattr(module.firestore, 'Client', lambda **kw: client)
    monkeypatch.setattr(module, 'FirestoreStore', lambda *a, **kw: store)
    transaction = client.transaction
    monkeypatch.setattr(client, 'transaction', lambda **kw: transaction())
    before = deepcopy(client.rows)
    module.attestation_dry_run(args, binding.owner_id, 50, 200, ['bad'], spec)
    output = json.loads(capsys.readouterr().out)
    assert output['firestore_writes'] == output['paid_stt_calls'] == output['audio_downloads'] == 0
    assert output['apply_supported'] is False
    assert client.rows == before
    assert (tmp_path / 'cohort.json').stat().st_mode & 0o777 == 0o600
    artifacts.fetch_audio.assert_not_called()
    soniox.assert_not_called()
    alternate.assert_not_called()
    args.apply = True
    with pytest.raises(module.held.Refused, match='attestation_apply_not_supported'):
        module.attestation_dry_run(args, binding.owner_id, 50, 200, ['bad'], spec)


@pytest.mark.parametrize('change', ['empty', 'words', 'spent', 'outside', 'result', 'terminal'])
def test_attestation_never_overrules_paid_or_custody_evidence(setup, monkeypatch, legacy_dependencies, change):
    client, *_ = prepared_setup(setup, monkeypatch, legacy_dependencies)
    job = row(client)
    job['recovery_state'] = 'failed_held'
    job['recovery'].update(provider='modulate', started_at=100, recognizers={'soniox': {'outcome': 'error'}})
    if change in {'empty', 'words'}:
        job['recovery']['recognizers']['soniox']['outcome'] = change
    if change == 'spent':
        job['recovery']['paid_state'] = 'spent'
    if change == 'outside':
        job['recovery']['started_at'] = 300
    if change == 'result':
        job['result'] = {'outcome': 'success'}
    if change == 'terminal':
        job['terminal_disposition'] = {'state': 'completed'}
    with pytest.raises(scope.ScopeRefused):
        refused_candidate(job, prepared=True, after=50, cutoff=200, max_seconds=190, window=(90, 200))


def test_marker_refusal_attests_soniox_only_and_preserves_prior_modulate(setup, monkeypatch, legacy_dependencies):
    client, *_ = prepared_setup(setup, monkeypatch, legacy_dependencies, duration=30)
    job = row(client)
    job['recovery_state'] = 'failed_held'
    job['recovery']['provider'] = 'modulate'
    job['speech_redrive'] = {
        'paid_epoch': 3,
        'provider': 'soniox',
        'token': 'd' * 32,
        'state': 'failed_held',
        'started_at': 100,
        'prior_recovery': deepcopy(job['recovery']),
        'failure': {'stage': 'provider', 'reason': 'provider_failed'},
        'recognizers': {'modulate': {'outcome': 'empty'}, 'soniox': {'outcome': 'error'}},
    }
    before = deepcopy(job)
    assert refused_candidate(job, prepared=False, after=50, cutoff=200, max_seconds=60, window=(90, 200))
    assert job == before
    job['speech_redrive']['recognizers']['soniox']['outcome'] = 'empty'
    with pytest.raises(scope.ScopeRefused, match='attestation_has_paid_evidence'):
        refused_candidate(job, prepared=False, after=50, cutoff=200, max_seconds=60, window=(90, 200))


@pytest.mark.parametrize('renewal', ['attempt_history', 'empty_history', 'original_token'])
def test_attestation_cannot_ignore_a_renewed_intents_earlier_window(setup, monkeypatch, legacy_dependencies, renewal):
    client, *_ = prepared_setup(setup, monkeypatch, legacy_dependencies)
    job = row(client)
    job['recovery_state'] = 'failed_held'
    marker = job['recovery']
    marker.update(provider='modulate', prepared_at=100, recognizers={'soniox': {'outcome': 'error'}})
    marker.pop('started_at', None)
    if renewal == 'attempt_history':
        marker['attempt_history'] = [{'started_at': 10, 'recognizers': {'soniox': {'outcome': 'error'}}}]
    elif renewal == 'empty_history':
        marker['attempt_history'] = []
    else:
        marker['original_token'] = 'e' * 32
    # The current preparation fits the zero-file window, but the retained
    # earlier attempt does not. Its spend cannot be attested away.
    with pytest.raises(scope.ScopeRefused, match='attestation_attempt_history_forbidden'):
        refused_candidate(job, prepared=True, after=50, cutoff=200, max_seconds=190, window=(90, 200))
