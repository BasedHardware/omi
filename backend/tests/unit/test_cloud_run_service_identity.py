"""Backend Cloud Run services pinned to an attached runtime identity never mount a key credential."""

import runpy
from pathlib import Path

import pytest
import yaml

from scripts.runtime_env_validation.common import KEY_CREDENTIAL_ENV_NAMES, _validate_service_identity
from scripts.runtime_env_validation.workflows import _validate_workflow_service_identity

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
_RENDERER = runpy.run_path(str(BACKEND / 'scripts/render_backend_runtime_env.py'), run_name='identity_test_renderer')
RUNTIME_SA = 'backend-runtime@based-hardware.iam.gserviceaccount.com'
PINNED_PROD_SERVICES = ('backend-sync', 'backend-sync-backfill', 'backend-integration')


def test_identity_flags_pin_the_account_and_drop_key_refs_in_the_same_deploy():
    flags = _RENDERER['_render_identity_flags']('backend-sync', {'service_account': RUNTIME_SA})

    assert flags == (
        f'--service-account={RUNTIME_SA} --remove-secrets=SERVICE_ACCOUNT_JSON,GOOGLE_APPLICATION_CREDENTIALS'
    )


def test_unpinned_service_renders_no_identity_flags():
    assert _RENDERER['_render_identity_flags']('backend', {'secrets': {}}) == ''


@pytest.mark.parametrize('bad', ['backend-runtime', 'someone@gmail.com', 'a b@x.iam.gserviceaccount.com'])
def test_identity_rejects_values_that_are_not_service_account_emails(bad):
    with pytest.raises(ValueError, match='service-account email'):
        _RENDERER['_render_identity_flags']('backend-sync', {'service_account': bad})


@pytest.mark.parametrize('key_env', KEY_CREDENTIAL_ENV_NAMES)
def test_identity_rejects_a_manifest_that_also_mounts_a_key(key_env):
    config = {'service_account': RUNTIME_SA, 'secrets': {key_env: {'secret': key_env, 'version': '1'}}}

    with pytest.raises(ValueError, match='must not also mount key credential'):
        _RENDERER['_render_identity_flags']('backend-sync', config)


def test_rendered_state_carries_the_declared_identity_for_live_validation():
    env_config = {
        'cloud_run': {
            'network': {'flags': {'--vpc-egress': 'private-ranges-only'}},
            'services': {
                'backend': {'env': {}, 'secrets': {}},
                'backend-sync': {'service_account': RUNTIME_SA, 'env': {}, 'secrets': {}},
            },
        }
    }

    state = _RENDERER['_render_cloud_run_state'](env_config)

    assert state['services']['backend-sync']['service_account'] == RUNTIME_SA
    assert 'service_account' not in state['services']['backend']


def test_live_validation_rejects_wrong_identity_and_a_lingering_key():
    errors = _validate_service_identity(
        scope='cloud_run/backend-sync',
        service_config={'service_account': RUNTIME_SA},
        actual_service_account='208440318997-compute@developer.gserviceaccount.com',
        actual_env_names={'SERVICE_ACCOUNT_JSON', 'REDIS_DB_HOST'},
    )

    messages = [str(error) for error in errors]
    assert any('must run as service_account' in message for message in messages)
    assert any('SERVICE_ACCOUNT_JSON' in message for message in messages)


def test_live_validation_accepts_the_pinned_keyless_service():
    assert (
        _validate_service_identity(
            scope='cloud_run/backend-sync',
            service_config={'service_account': RUNTIME_SA},
            actual_service_account=RUNTIME_SA,
            actual_env_names={'REDIS_DB_HOST'},
        )
        == []
    )


def test_workflow_validation_requires_the_key_removal_flag():
    state = {'flags': {'--service-account': RUNTIME_SA}, 'secrets': {}}

    errors = _validate_workflow_service_identity('backend-sync', {'service_account': RUNTIME_SA}, state)

    assert [str(error) for error in errors if '--remove-secrets' in str(error)]


def test_repo_prod_manifest_pins_only_the_cut_over_services():
    manifest = yaml.safe_load((BACKEND / 'deploy/runtime_env.yaml').read_text(encoding='utf-8'))
    services = manifest['environments']['prod']['cloud_run']['services']

    for service in PINNED_PROD_SERVICES:
        assert services[service]['service_account'] == RUNTIME_SA
        assert not set(KEY_CREDENTIAL_ENV_NAMES) & set(services[service].get('secrets') or {})
    # Each further service is pinned only after its own canary; `backend` moves with listen/pusher
    # in its own reviewed cut-over (credential hygiene D4 phase 2).
    assert 'service_account' not in services['backend']


def test_backend_stack_deploys_pass_each_services_identity_flags():
    action = (REPO / '.github/actions/deploy-backend-stack/action.yml').read_text(encoding='utf-8')
    lifecycle = (REPO / '.github/actions/sync-backfill-lifecycle/action.yml').read_text(encoding='utf-8')

    for output in ('backend', 'backend_sync', 'backend_integration'):
        assert f'${{{{ steps.runtime-env.outputs.{output}_identity_flags }}}}' in action
    assert 'identity_flags: ${{ steps.runtime-env.outputs.backend_sync_backfill_identity_flags }}' in action
    assert '${{ inputs.identity_flags }}' in lifecycle
