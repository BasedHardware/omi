"""Voice staging storage survives the actual deployment rendering boundary."""

from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from google.auth.credentials import AnonymousCredentials
from google.cloud.storage import Client

from scripts.render_backend_runtime_env import _render_env_vars
from scripts.runtime_env_capability_contracts import validate_voice_transcription_storage
from scripts.runtime_env_validation import manifest as validator


@pytest.fixture(scope='module')
def manifest():
    path = Path(__file__).resolve().parents[2] / 'deploy/runtime_env.yaml'
    return yaml.load(path.read_text(), Loader=yaml.CSafeLoader)


@pytest.mark.parametrize(('environment', 'bucket'), [('dev', 'syncing-local-development'), ('prod', 'syncing-local')])
def test_voice_bucket_reaches_deploy_renderer(manifest, environment, bucket, monkeypatch):
    config = manifest['environments'][environment]
    entries = config['cloud_run']['services']['backend']['env']
    for entry in entries.values():
        if 'env_var' in entry:
            monkeypatch.setenv(entry['env_var'], str(entry.get('default', 'test-value')))
    assert f'BUCKET_TEMPORAL_SYNC_LOCAL={bucket}' in _render_env_vars(entries).splitlines()
    assert not validate_voice_transcription_storage(environment, config)


@pytest.mark.parametrize('environment', ['dev', 'prod'])
@pytest.mark.parametrize(
    'binding', [None, {'value': ''}, {'value': 'wrong-environment'}, {'env_var': 'INHERITED_BUCKET'}]
)
def test_missing_blank_or_implicit_voice_bucket_fails_admission(manifest, environment, binding):
    config = deepcopy(manifest['environments'][environment])
    entries = config['cloud_run']['services']['backend']['env']
    if binding is None:
        entries.pop('BUCKET_TEMPORAL_SYNC_LOCAL', None)
    else:
        entries['BUCKET_TEMPORAL_SYNC_LOCAL'] = binding
    assert validate_voice_transcription_storage(environment, config)


def test_unconfigured_storage_rejects_valid_probe_before_network():
    fixture = Path(__file__).resolve().parents[2] / 'testing/release_fixtures/transcription-release-probe.wav'
    blob = Client(project='hermetic-project', credentials=AnonymousCredentials()).bucket(None).blob('probe.wav')
    with pytest.raises(ValueError, match='Cannot determine path without bucket name'):
        blob.upload_from_filename(str(fixture))


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_normal_admission_invokes_storage_guard(manifest, environment, monkeypatch):
    broken = deepcopy(manifest)
    broken['environments'][environment]['cloud_run']['services']['backend']['env'].pop('BUCKET_TEMPORAL_SYNC_LOCAL')
    path = Path('/hermetic-runtime-manifest.yaml')
    load = validator._load_yaml
    monkeypatch.setattr(validator, '_load_yaml', lambda p: broken if p == path else load(p))
    errors = validator.validate_runtime_env(env=environment, manifest_path=path)
    assert any('voice transcription requires literal BUCKET_TEMPORAL_SYNC_LOCAL' in e.message for e in errors)
