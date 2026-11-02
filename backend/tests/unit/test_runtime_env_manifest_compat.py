"""Current controls can replay the prior production manifest without a bypass."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from scripts import render_backend_runtime_env as renderer
from scripts.runtime_env_capability_contracts import validate_voice_transcription_storage
from scripts.runtime_env_compat import normalize_runtime_manifest, VOICE_STAGING_BUCKET_ENV, VOICE_STAGING_BUCKETS
from scripts.runtime_env_validation import common

FIXTURE = Path(__file__).parent / 'fixtures/runtime_env/legacy_voice_staging_8ad1d75.json'


@pytest.fixture
def legacy():
    return json.loads(FIXTURE.read_text())


def test_shared_loaders_migrate_only_missing_legacy_bucket(legacy):
    expected = deepcopy(legacy)
    for env, bucket in VOICE_STAGING_BUCKETS.items():
        expected['environments'][env]['cloud_run']['services']['backend']['env'][VOICE_STAGING_BUCKET_ENV] = {
            'value': bucket,
            'category': 'storage_retention',
        }
    assert renderer._load_yaml(FIXTURE) == common._load_yaml(FIXTURE) == expected
    assert legacy == json.loads(FIXTURE.read_text())
    assert normalize_runtime_manifest(expected) == expected


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_captured_old_release_renders_reviewed_bucket(legacy, environment):
    assert legacy['_capture']['source_sha'] == '8ad1d75cc9df4fc535093e14672d70a2deebed11'
    config = normalize_runtime_manifest(legacy)['environments'][environment]
    entries = config['cloud_run']['services']['backend']['env']
    rendered = renderer._render_env_vars(entries)
    assert f'{VOICE_STAGING_BUCKET_ENV}={VOICE_STAGING_BUCKETS[environment]}' in rendered.splitlines()
    assert not validate_voice_transcription_storage(environment, config)


@pytest.mark.parametrize('version', [1, 2])
@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_real_prebuild_entry_replays_v1_and_rejects_omitted_v2_bucket(
    legacy, version, environment, tmp_path, monkeypatch
):
    legacy['schema_version'] = version
    path = tmp_path / 'runtime_env.yaml'
    path.write_text(json.dumps(legacy))
    script = Path(__file__).resolve().parents[2] / 'scripts/preflight-cloud-run-deploy.py'
    spec = importlib.util.spec_from_file_location('preflight_manifest_compat', script)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        sys, 'argv', [str(script), '--env', environment, '--project', 'hermetic', '--manifest', str(path)]
    )
    if version == 1:
        assert module.main() == 0
    else:
        with pytest.raises(SystemExit) as error:
            module.main()
        assert error.value.code == 2


@pytest.mark.parametrize('binding', [None, {'value': ''}, {'value': 'wrong-environment'}])
def test_explicit_invalid_legacy_binding_is_never_repaired(legacy, binding):
    for env in VOICE_STAGING_BUCKETS:
        legacy['environments'][env]['cloud_run']['services']['backend']['env'][VOICE_STAGING_BUCKET_ENV] = binding
    normalized = normalize_runtime_manifest(legacy)
    for env in VOICE_STAGING_BUCKETS:
        assert validate_voice_transcription_storage(env, normalized['environments'][env])


@pytest.mark.parametrize('version', [0, 3, True, '2', None])
def test_unknown_or_invalid_manifest_version_is_rejected(legacy, version):
    legacy['schema_version'] = version
    with pytest.raises(ValueError, match='Unsupported backend runtime manifest schema_version'):
        normalize_runtime_manifest(legacy)


def test_non_manifest_yaml_is_unchanged():
    chart = {'env': [{'name': 'EXAMPLE', 'value': 'true'}], 'schema_version': 99}
    assert normalize_runtime_manifest(chart) is chart
