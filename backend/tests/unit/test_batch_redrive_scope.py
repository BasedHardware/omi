"""Scoped CLI dry-run/apply/replay without a cloud client or paid provider."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from utils.batch_pipeline import redrive_scope as scope


def test_selection_excludes_old_spent_receipts_and_nonheld():
    base = dict(quarantined_at=100, state='quarantined', recovery_state='failed_held')
    assert scope.eligible(base, 100, 110)
    for patch in [
        dict(quarantined_at=99),
        dict(quarantined_at=111),
        dict(state='committed'),
        dict(recovery_state='running'),
        dict(speech_redrive={'state': 'failed_held'}),
        dict(silence_disposition={'state': 'completed'}),
    ]:
        assert not scope.eligible({**base, **patch}, 100, 110)


def test_manifest_is_private_create_only_and_binds_scope(tmp_path):
    path = tmp_path / 'private.json'
    spec = scope.scope_body('synthetic-owner', 'batch_pipeline_prod', 50, 150, True, None)
    manifest = {'scope': spec, 'units': [['a', 'f' * 64, 'speech']]}
    scope.write(path, manifest)
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        scope.write(path, manifest)
    assert scope.load(path, spec, 1) == manifest
    for change in [dict(owner_id='foreign'), dict(after=49), dict(before=151), dict(silent=False)]:
        with pytest.raises(scope.ScopeRefused, match='cohort_scope_changed'):
            scope.load(path, {**spec, **change}, 1)
        assert scope.digest({'scope': {**spec, **change}, 'units': manifest['units']}) != scope.digest(manifest)
    manifest['units'].append(manifest['units'][0])
    path.write_text(json.dumps(manifest))
    with pytest.raises(scope.ScopeRefused, match='invalid_cohort_unit'):
        scope.load(path, spec, 2)


@pytest.fixture
def cli(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2] / 'scripts'))
    spec = importlib.util.spec_from_file_location(
        'scoped_operator', Path(__file__).parents[2] / 'scripts/batch_pipeline_speech_redrive.py'
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv('GCP_AGENT_TIER', 'ro-prod')
    monkeypatch.setenv('P55_TEST_OWNER', 'synthetic-owner')
    monkeypatch.setenv('ENCRYPTION_SECRET', 'x' * 32)
    monkeypatch.setenv('BUCKET_BATCH_PIPELINE', 'synthetic')
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    rows = {
        sid: dict(
            owner_id='synthetic-owner',
            quarantined_at=100,
            state='quarantined',
            recovery_state='failed_held',
            recovery={'epoch': 1},
            duration_seconds=5,
        )
        for sid in ['a', 'b']
    }
    rows['old'] = {**rows['a'], 'quarantined_at': 40}
    rows['spent'] = {**rows['a'], 'speech_redrive': {'state': 'completed'}}

    def document(sid):
        return SimpleNamespace(id=sid, to_dict=lambda: deepcopy(rows[sid]))

    collection = SimpleNamespace(document=lambda sid: SimpleNamespace(get=lambda: document(sid)))
    client = SimpleNamespace(collection=lambda _: collection)
    monkeypatch.setattr(module.firestore, 'Client', lambda **_: client)
    monkeypatch.setattr(module.storage, 'Client', lambda **_: None)
    monkeypatch.setattr(
        module, 'FirestoreStore', lambda *a, **k: SimpleNamespace(namespace='batch_pipeline_prod', client=client)
    )
    monkeypatch.setattr(module, 'create_artifact_store', lambda *a: Mock())
    monkeypatch.setattr(module, 'configure_rollout_runtime', lambda: None)
    monkeypatch.setattr(scope, 'owner_jobs', lambda *a: (document(sid) for sid in rows))
    monkeypatch.setattr(module, 'checked_job', lambda store, sid, uid, key: deepcopy(rows[sid]))
    monkeypatch.setattr(module, 'inspect_unit', lambda *a: 'speech')
    calls = []

    def redrive(store, artifacts, sid, uid, digest, recovery, **kw):
        calls.append(sid)
        rows[sid].update(
            state='result_ready',
            recovery_state='recovered',
            speech_redrive={'plan_digest': digest, 'silent': kw['silent']},
        )
        return 'recovered'

    monkeypatch.setattr(module, 'redrive_one', redrive)
    path = tmp_path / 'cohort.json'
    args = [
        'operator',
        '--stage',
        'prod',
        '--owner-env',
        'P55_TEST_OWNER',
        '--quarantined-after',
        '1970-01-01T00:00:50Z',
        '--quarantined-before',
        '1970-01-01T00:02:30Z',
        '--cohort-file',
        str(path),
        '--silent',
        '--expect-count',
        '2',
        '--expect-speech-count',
        '2',
        '--paid-epoch',
        '2',
    ]

    def run(extra=()):
        monkeypatch.setattr(sys, 'argv', args + list(extra))
        module.main()

    return module, run, rows, calls, path


def test_cli_bootstraps_dry_run_without_spend_and_replays_same_canary_prefix(cli, monkeypatch, capsys):
    module, run, rows, calls, path = cli
    before = deepcopy(rows)
    run()
    output = json.loads(capsys.readouterr().out)
    assert rows == before and not calls
    assert output['units'] == 2 and output['paid_stt_calls'] == output['firestore_writes'] == 0
    assert len(json.loads(path.read_text())['units']) == 2
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    args = [
        '--apply',
        '--source-census-sha256',
        output['source_census_sha256'],
        '--approve-plan-sha256',
        output['plan_sha256'],
    ]
    run(args + ['--apply-limit', '1'])
    capsys.readouterr()
    assert calls == ['a']
    # A new eligible unit does not expand the frozen manifest after the canary.
    rows['new'] = {**before['b']}

    def replay(store, artifacts, sid, uid, digest, recovery, **kw):
        if sid == 'a':
            return 'already_applied'
        calls.append(sid)
        return 'recovered'

    monkeypatch.setattr(module, 'redrive_one', replay)
    run(args + ['--apply-limit', '2'])
    assert calls == ['a', 'b']
    final = json.loads(capsys.readouterr().out)
    assert final['outcomes'] == {'already_applied': 1, 'recovered': 1}
    assert final['source_census_sha256'] == output['source_census_sha256']


def test_cli_first_failure_stops_remaining_paid_units(cli, monkeypatch, capsys):
    module, run, rows, calls, _ = cli
    run()
    output = json.loads(capsys.readouterr().out)
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    paid = Mock(return_value='failed_held')
    monkeypatch.setattr(module, 'redrive_one', paid)
    with pytest.raises(SystemExit) as error:
        run(
            [
                '--apply',
                '--source-census-sha256',
                output['source_census_sha256'],
                '--approve-plan-sha256',
                output['plan_sha256'],
                '--apply-limit',
                '2',
            ]
        )
    assert error.value.code == 2 and paid.call_count == 1
    assert json.loads(capsys.readouterr().out)['stopped'] is True


def test_cli_changed_digest_never_dispatches(cli, monkeypatch, capsys):
    module, run, rows, calls, _ = cli
    run()
    output = json.loads(capsys.readouterr().out)
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    with pytest.raises(module.held.Refused, match='source_census_changed'):
        run(['--apply', '--source-census-sha256', '0' * 64, '--approve-plan-sha256', output['plan_sha256']])
    assert not calls
