"""Standalone role-image opt-in (plan B B3): a bare digest is admitted only as the
registry's role image for that service, and the gateway/pusher workflows wire it
behind blank-by-default inputs."""

import json
from pathlib import Path

import pytest
import yaml

from scripts import admit_role_image as admission
from scripts import resolve_service_images as resolver

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PROJECT = 'based-hardware-dev'
SHA = 'a' * 40
DIGEST = 'sha256:' + 'c' * 64
# service -> (role image the registry maps it to, role whose OMI_ROLE it must carry)
ROLE_IMAGES = {
    'llm-gateway': ('backend-gateway', 'gateway'),
    'pusher': ('backend-pusher', 'realtime'),
    'messaging-maintenance': ('backend-workers', 'workers'),
}


def role_config(role, revision=SHA):
    return {
        'Labels': {'org.opencontainers.image.revision': revision},
        'Env': ['PATH=/opt/venv/bin', f'OMI_ROLE={role}', f'OMI_RELEASE_SHA={revision}'],
    }


def inspector(configs):
    def inspect(ref):
        return configs[ref]

    return inspect


def admit(service, digest=DIGEST, *, admitted_sha=SHA, inspect=None):
    return admission.admit(
        service,
        digest,
        project=PROJECT,
        admitted_sha=admitted_sha,
        inspect=inspect or (lambda ref: pytest.fail(f'unexpected inspect {ref}')),
    )


@pytest.mark.parametrize('service, image, role', [(service, *spec) for service, spec in ROLE_IMAGES.items()])
def test_admits_the_registry_role_image_for_the_service(service, image, role):
    reference = f'gcr.io/{PROJECT}/{image}@{DIGEST}'
    assert admit(service, inspect=inspector({reference: role_config(role)})) == {
        'repository': f'gcr.io/{PROJECT}/{image}',
        'digest': DIGEST,
        'reference': reference,
    }


@pytest.mark.parametrize(
    'digest',
    [
        '',
        'sha256:abc',
        'SHA256:' + 'C' * 64,
        'c' * 64,
        # The repository is never caller-supplied: a full reference is not a digest.
        f'gcr.io/{PROJECT}/backend-gateway@{DIGEST}',
        f'gcr.io/{PROJECT}/backend-gateway:aaaaaaa',
    ],
)
def test_malformed_digests_fail_before_any_inspect(digest):
    with pytest.raises(resolver.ServiceImageError, match='is not sha256:<64 lowercase hex>'):
        admit('llm-gateway', digest)


def test_an_undeclared_service_fails_before_any_inspect():
    with pytest.raises(
        resolver.ServiceImageError, match="'backend-nope' is not a service runtime_images.json declares"
    ):
        admit('backend-nope')


@pytest.mark.parametrize('incomplete', [{'role': 'gateway'}, {'image': 'backend-gateway'}, {'image': '', 'role': 'x'}])
def test_a_service_without_a_role_image_mapping_fails_before_any_inspect(incomplete):
    registry = {'services': {'llm-gateway': incomplete}}
    with pytest.raises(resolver.ServiceImageError, match='does not map the service to a role image and role'):
        admission.admit(
            'llm-gateway', DIGEST, project=PROJECT, admitted_sha=SHA, registry=registry, inspect=inspector({})
        )


def test_revision_and_role_must_match_the_admitted_release():
    reference = f'gcr.io/{PROJECT}/backend-gateway@{DIGEST}'
    with pytest.raises(resolver.ServiceImageError, match='labelled revision'):
        admit('llm-gateway', inspect=inspector({reference: role_config('gateway', revision='b' * 40)}))
    with pytest.raises(resolver.ServiceImageError, match='OMI_ROLE=gateway'):
        admit('llm-gateway', inspect=inspector({reference: role_config('workers')}))
    with pytest.raises(resolver.ServiceImageError, match='labelled revision'):
        admit('llm-gateway', inspect=inspector({reference: {}}))


def test_the_pusher_digest_names_the_realtime_role_image_not_the_fat_pusher_repository():
    """Only gcr.io/<project>/backend-pusher is inspected; the fat pusher repository never is."""
    reference = f'gcr.io/{PROJECT}/backend-pusher@{DIGEST}'
    admitted = admit('pusher', inspect=inspector({reference: role_config('realtime')}))
    assert admitted['repository'] == f'gcr.io/{PROJECT}/backend-pusher'
    with pytest.raises(resolver.ServiceImageError, match='OMI_ROLE=realtime'):
        admit('pusher', inspect=inspector({reference: role_config('pusher')}))


def test_registry_maps_the_services_the_standalone_deploys_admit():
    registry = json.loads(admission.REGISTRY_PATH.read_text(encoding='utf-8'))
    for service, (image, role) in ROLE_IMAGES.items():
        assert (registry['services'][service]['image'], registry['services'][service]['role']) == (image, role)
    # The stack resolver and this admission check the same properties of a role digest.
    assert resolver.REGISTRY_PATH == admission.REGISTRY_PATH


def test_cli_appends_prefixed_assignments_to_github_env(tmp_path, capsys, monkeypatch):
    reference = f'gcr.io/{PROJECT}/backend-pusher@{DIGEST}'
    monkeypatch.setattr(admission, 'inspect_image_config', inspector({reference: role_config('realtime')}))
    github_env = tmp_path / 'env'
    github_env.write_text('EXISTING=1\n', encoding='utf-8')
    common = ['--digest', DIGEST, '--project', PROJECT, '--admitted-sha', SHA]

    assert (
        admission.main(['--service', 'pusher', *common, '--prefix', 'PUSHER_IMAGE', '--github-env', str(github_env)])
        == 0
    )

    assert github_env.read_text(encoding='utf-8') == (
        'EXISTING=1\n'
        f'PUSHER_IMAGE_REPOSITORY=gcr.io/{PROJECT}/backend-pusher\n'
        f'PUSHER_IMAGE_DIGEST={DIGEST}\n'
        f'PUSHER_IMAGE_REFERENCE={reference}\n'
    )
    assert f'Role-image opt-in: pusher runs {reference}' in capsys.readouterr().out

    gateway = f'gcr.io/{PROJECT}/backend-gateway@{DIGEST}'
    monkeypatch.setattr(admission, 'inspect_image_config', inspector({gateway: role_config('gateway')}))
    assert admission.main(['--service', 'llm-gateway', *common]) == 0
    assert capsys.readouterr().out.startswith(f'ROLE_IMAGE_REPOSITORY=gcr.io/{PROJECT}/backend-gateway\n')

    assert (
        admission.main(['--service', 'llm-gateway', '--digest', 'nope', '--project', PROJECT, '--admitted-sha', SHA])
        == 1
    )
    assert 'is not sha256' in capsys.readouterr().err
    with pytest.raises(SystemExit):
        admission.main(['--service', 'llm-gateway', *common, '--prefix', 'bad-prefix'])


# Workflow wiring: the inputs default blank (merging changes no deploy) and the
# opt-in replaces the fat build with the admitted role digest.


def _workflow(name):
    document = yaml.safe_load((REPOSITORY_ROOT / '.github' / 'workflows' / name).read_text(encoding='utf-8'))
    # PyYAML reads the bare `on:` key as the boolean True.
    triggers = document.get('on', document.get(True))
    steps = {step['name']: step for step in document['jobs']['deploy']['steps']}
    return triggers['workflow_dispatch']['inputs'], steps


def test_gateway_workflow_admits_a_blank_by_default_role_digest():
    inputs, steps = _workflow('gcp_llm_gateway.yml')
    assert inputs['gateway_image_digest']['default'] == ''
    assert inputs['gateway_image_digest']['required'] is False

    admit_step = steps['Admit role-image digest opt-in']
    assert admit_step['if'] == "github.event.inputs.gateway_image_digest != ''"
    assert '--service llm-gateway' in admit_step['run']
    assert '--github-env "$GITHUB_ENV"' in admit_step['run']
    # The input reaches the shell through env, never by inline interpolation.
    assert admit_step['env']['ROLE_IMAGE_DIGEST_INPUT'] == '${{ github.event.inputs.gateway_image_digest }}'
    assert '--digest "$ROLE_IMAGE_DIGEST_INPUT"' in admit_step['run']
    assert '${{ github.event.inputs.gateway_image_digest }}' not in admit_step['run']

    build = steps['Build and Push Docker image']
    assert build['if'] == "github.event.inputs.gateway_image_digest == ''"
    assert '-f backend/Dockerfile' in build['run'] and 'runtime_image_contracts.py smoke' in build['run']

    deploy = steps['Deploy LLM Gateway to GKE cluster using Helm']
    assert deploy['env']['IMAGE_REPOSITORY'] == '${{ env.ROLE_IMAGE_REPOSITORY }}'
    assert deploy['env']['IMAGE_DIGEST'] == '${{ env.ROLE_IMAGE_DIGEST }}'
    assert 'containers[0].image' in deploy['run']
    for name in ('Probe LLM Gateway from the Cloud Run VPC', 'Smoke LLM Gateway'):
        assert '--image "${ROLE_IMAGE_REFERENCE:-gcr.io/' in steps[name]['run']


def test_pusher_workflow_admits_a_blank_by_default_role_digest_in_development_only():
    inputs, steps = _workflow('gcp_backend_pusher.yml')
    assert inputs['pusher_role_image_digest']['default'] == ''
    assert inputs['pusher_role_image_digest']['required'] is False
    validate_step = steps['Validate Environment Input']
    # The free-text input reaches this step through env, never inline interpolation.
    assert (
        validate_step['env']['PUSHER_ROLE_IMAGE_DIGEST_INPUT'] == '${{ github.event.inputs.pusher_role_image_digest }}'
    )
    assert '${{ github.event.inputs.pusher_role_image_digest }}' not in validate_step['run']
    assert '-n "$PUSHER_ROLE_IMAGE_DIGEST_INPUT"' in validate_step['run']

    admit_step = steps['Admit role-image digest opt-in']
    assert admit_step['if'] == (
        "env.SERVICE == 'pusher' && github.event.inputs.environment != 'prod' "
        "&& github.event.inputs.pusher_role_image_digest != ''"
    )
    assert '--service pusher' in admit_step['run'] and '--prefix PUSHER_IMAGE' in admit_step['run']
    assert admit_step['env']['ROLE_IMAGE_DIGEST_INPUT'] == '${{ github.event.inputs.pusher_role_image_digest }}'
    assert '--digest "$ROLE_IMAGE_DIGEST_INPUT"' in admit_step['run']
    assert '${{ github.event.inputs.pusher_role_image_digest }}' not in admit_step['run']

    build = steps['Build and Push Docker image']
    assert build['if'] == (
        "env.SERVICE == 'llm-gateway' || (github.event.inputs.environment != 'prod' "
        "&& github.event.inputs.pusher_role_image_digest == '')"
    )
    assert '-f backend/pusher/Dockerfile' in build['run'] and '-f backend/Dockerfile' in build['run']
    assert (
        "github.event.inputs.pusher_role_image_digest == ''"
        in steps['Resolve immutable development Pusher image']['if']
    )

    select = steps['Select development-qualified Pusher digest for production']['run']
    assert 'gcr.io/based-hardware-dev/pusher,gcr.io/based-hardware-dev/backend-pusher' in select
    # An evidence file without image_repository must fail here, not slip through the case match.
    assert 'if [[ -z "$DEV_PUSHER_REPOSITORY" ]]' in select
    assert select.index('-z "$DEV_PUSHER_REPOSITORY"') < select.index('case ",$DEV_PUSHER_REPOSITORIES,"')
    assert '--expected-repository "$DEV_PUSHER_REPOSITORIES"' in select
    promote = steps['Promote qualified Pusher digest into the production registry']['run']
    assert '${PUSHER_DEV_IMAGE_REPOSITORY##*/}' in promote
    for name in (
        'Exercise isolated production Pusher finalization semantics',
        'Verify final production Pusher matches the canary-qualified candidate',
    ):
        assert '--expected-repository "$PUSHER_DEV_IMAGE_REPOSITORIES"' in steps[name]['run']
