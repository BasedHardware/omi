"""Fast wire-format/recorder contracts. No emulator or product imports here."""

import asyncio
from dataclasses import replace
import json
from pathlib import Path

import pytest
import jsonschema

from testing.replay_harness.manifest import IMPLEMENTED_STAGES, JSON_SCHEMA, STAGES, load_case, validate_manifest
from testing.replay_harness.report import StageResult, item_report, record_exception, table, write_report
from testing.replay_harness.stages.base import NotImplementedStage

FIXTURES = Path(__file__).resolve().parents[2] / 'testing/replay_harness/fixtures'


@pytest.fixture
def manifest():
    return json.loads((FIXTURES / 'admission-control/manifest.json').read_text())


def test_all_seed_manifests_follow_published_schema():
    for directory in FIXTURES.iterdir():
        value = json.loads((directory / 'manifest.json').read_text())
        jsonschema.Draft202012Validator(JSON_SCHEMA, format_checker=jsonschema.FormatChecker()).validate(value)
        case = load_case(directory)
        assert case.manifest.id == directory.name
        assert case.manifest.tier == 'S'
        assert case.manifest.prod_evidence == {}


@pytest.mark.parametrize(
    'field,value',
    [
        ('schema_version', 2),
        ('schema_version', True),
        ('id', '../escape'),
        ('tier', 'prod'),
        ('scrub', ''),
        ('created', 'yesterday'),
        ('created', '2026-11-04'),
        ('seed_blob_sha256', ['abc']),
        ('prod_evidence', []),
        ('stages', {}),
        ('stages', {'unknown': {'expect': 'pass'}}),
        ('stages', {'admission': {'expect_stop_stage': 'worker', 'expect_reason': 'ValueError'}}),
        ('stages', {'admission': {'expect_stop_stage': 'admission', 'expect_reason': '['}}),
        ('stages', {'admission': {'expect': 'pass', 'extra': True}}),
    ],
)
def test_manifest_rejects_invalid_contract(manifest, field, value):
    manifest[field] = value
    with pytest.raises(ValueError):
        validate_manifest(manifest)


def test_manifest_rejects_missing_and_unknown_fields(manifest):
    del manifest['scrub']
    with pytest.raises(ValueError):
        validate_manifest(manifest)
    manifest['scrub'] = 'synthetic'
    manifest['unknown'] = True
    with pytest.raises(ValueError):
        validate_manifest(manifest)


def test_loader_checks_seed_digests_and_containment(tmp_path, manifest):
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    (tmp_path / 'corpus.json').write_text('{}')
    assert load_case(tmp_path).corpus == {}
    manifest['seed_blob_sha256'] = ['0' * 64]
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='digest'):
        load_case(tmp_path)
    manifest['seed_blob_sha256'] = []
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    (tmp_path / 'blobs').mkdir()
    (tmp_path / 'blobs/escape').symlink_to(tmp_path.parent / 'outside')
    with pytest.raises(ValueError, match='escapes'):
        load_case(tmp_path)


def test_record_and_report_never_emit_exception_message(manifest, tmp_path):
    private = 'PRIVATE-CUSTOMER-TEXT-and-cloud-uri'
    try:
        raise ValueError(private)
    except ValueError as error:
        observation = record_exception(error, 'admission')
    assert observation['exception_type'] == 'ValueError'
    assert observation['site'].endswith('test_record_and_report_never_emit_exception_message')
    value = validate_manifest(manifest)
    stage = StageResult('admission', 'stopped', duration_ms=12, **observation, observations=[observation])
    report = item_report(value, [stage])
    assert report['verdict'] == 'FAIL'
    assert report['expectation_verdict'] == 'FAIL'
    expected = replace(
        value, expect=None, stages={'admission': {'expect_stop_stage': 'admission', 'expect_reason': 'ValueError'}}
    )
    reproduced = item_report(expected, [stage])
    assert reproduced['verdict'] == 'FAIL' and reproduced['expectation_met']
    write_report([reproduced], tmp_path)
    assert json.loads((tmp_path / 'report.json').read_text())['items'] == [reproduced]
    assert json.loads((tmp_path / f'{value.id}.json').read_text()) == reproduced
    assert (tmp_path / 'report.md').read_text().strip() == table([reproduced])
    assert private not in ''.join(path.read_text() for path in tmp_path.iterdir())


def test_control_pass_and_unreproduced_expected_stop(manifest):
    value = validate_manifest(manifest)
    stages = [StageResult('admission', 'pass', duration_ms=1)]
    assert item_report(value, stages)['expectation_met']
    expected = replace(
        value, expect=None, stages={'admission': {'expect_stop_stage': 'admission', 'expect_reason': 'ValueError'}}
    )
    report = item_report(expected, stages)
    assert report['verdict'] == 'PASS' and not report['expectation_met']


@pytest.mark.parametrize('name', [name for name in STAGES if name not in IMPLEMENTED_STAGES])
def test_reserved_boundaries_cannot_pass(name, manifest):
    stage = asyncio.run(NotImplementedStage(name).run(None, None))
    assert stage.reason == 'not_implemented' and stage.status == 'not_implemented'
    value = replace(validate_manifest(manifest), stages={name: {'expect': 'pass'}})
    assert not item_report(value, [stage])['expectation_met']
    value = replace(value, expect=None, stages={name: {'expect_stop_stage': name, 'expect_reason': 'not_implemented'}})
    assert not item_report(value, [stage])['expectation_met']


@pytest.mark.parametrize('name', [name for name in STAGES if name not in IMPLEMENTED_STAGES])
@pytest.mark.parametrize('stop', [False, True])
def test_manifest_rejects_every_unimplemented_stage(name, stop, manifest):
    manifest.pop('expect', None)
    manifest['stages'] = {name: {'expect_stop_stage': name, 'expect_reason': '.*'} if stop else {'expect': 'pass'}}
    with pytest.raises(ValueError, match='not_implemented'):
        validate_manifest(manifest)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(JSON_SCHEMA).validate(manifest)


def test_not_implemented_status_never_satisfies_admission_stop(manifest):
    manifest.pop('expect', None)
    manifest['stages'] = {'admission': {'expect_stop_stage': 'admission', 'expect_reason': 'not_implemented'}}
    stage = StageResult('admission', 'not_implemented', reason='not_implemented')
    assert not item_report(validate_manifest(manifest), [stage])['expectation_met']


def test_manifest_dataclass_round_trip(manifest):
    assert validate_manifest(manifest).to_dict() == manifest
    del manifest['expect']
    assert validate_manifest(manifest).to_dict() == manifest


def test_retained_capture_static_reason_pattern():
    case = load_case(FIXTURES / 'admission-not-durable')
    result = StageResult(
        'admission',
        'stopped',
        reason='admission:ValueError:utils.batch_pipeline.live.admit_recording:retained_capture_not_durable',
    )
    assert item_report(case.manifest, [result])['expectation_met']


@pytest.mark.parametrize(
    'endpoint', ['', 'remote:8085', '10.0.0.1:8085', '127.0.0.1:0', 'localhost:65536', 'localhost:abc']
)
def test_emulator_endpoint_refuses_cloud_and_invalid_ports(monkeypatch, endpoint):
    from testing.replay_harness.env import emulator_endpoint

    monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', endpoint)
    with pytest.raises(RuntimeError, match='loopback'):
        emulator_endpoint()


def test_existing_emulator_ci_selects_and_runs_replay():
    import yaml

    root = Path(__file__).resolve().parents[3]
    workflow = yaml.load((root / '.github/workflows/backend-emulator-proofs.yml').read_text(), Loader=yaml.BaseLoader)
    for trigger in ('push', 'pull_request'):
        paths = workflow['on'][trigger]['paths']
        assert 'backend/testing/replay_harness/**' in paths
        assert 'backend/tests/integration/test_replay_harness_firestore.py' in paths
        assert 'backend/utils/batch_pipeline/**' in paths
        # Titling stage (#24610).
        assert 'backend/utils/conversations/**' in paths
        assert 'backend/services/conversation_finalization.py' in paths
        assert 'backend/routers/conversation_finalization.py' in paths
        assert 'backend/tests/integration/test_replay_harness_titling_firestore.py' in paths
    runner = (root / 'backend/scripts/run-emulator-proofs.sh').read_text()
    assert 'tests/integration/test_replay_harness_firestore.py' in runner


def test_operation_identity_does_not_confuse_contention_transactions():
    case = load_case(FIXTURES / 'admission-drain-contention')
    for operation, transaction, expected in [
        ('due', None, False),
        ('defer', 'utils.batch_pipeline.live.drain_recordings.defer', False),
        ('read_pending', 'utils.batch_pipeline.live.drain_recordings.drain_one.lambda', False),
        ('admit', 'database.batch_pipeline_policy.load_job_policy.commit', False),
        ('admit', 'database.batch_pipeline_intake.admit.commit', True),
    ]:
        error = type('FirestoreContentionExhausted', (RuntimeError,), {})('PRIVATE')
        observation = record_exception(error, 'admission', operation=operation, transaction=transaction)
        result = StageResult('admission', 'stopped', **observation, observations=[observation])
        assert item_report(case.manifest, [result])['expectation_met'] == expected
        assert 'PRIVATE' not in json.dumps(observation)


def test_observer_preserves_admission_return_errors_and_drain_boundaries():
    from types import SimpleNamespace
    from testing.replay_harness.stages.observe import AdmissionObserver

    def commit(_):
        raise ValueError('PRIVATE')

    store = SimpleNamespace(run=lambda body: body(None), due=lambda *a: (_ for _ in ()).throw(TimeoutError('PRIVATE')))

    async def admit(fail=False):
        if fail:
            return await asyncio.to_thread(store.run, commit)
        return {'unchanged': True}

    live = SimpleNamespace(admit_recording=admit)

    async def drive():
        with AdmissionObserver(live, store) as observer:
            assert await live.admit_recording() == {'unchanged': True}
            with pytest.raises(ValueError, match='PRIVATE'):
                await live.admit_recording(True)
            with pytest.raises(TimeoutError):
                store.due('record_pending')

            def defer(_):
                raise RuntimeError('PRIVATE')

            with pytest.raises(RuntimeError):
                store.run(defer)
        assert live.admit_recording is admit
        return observer.errors

    errors = asyncio.run(drive())
    assert [e['operation'] for e in errors] == ['admit', 'due', 'defer']
    assert errors[0]['transaction'].endswith('.commit')
    assert 'PRIVATE' not in json.dumps(errors)
