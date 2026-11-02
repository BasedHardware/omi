"""deploy-backend-stack service_images: empty changes nothing; an opt-in is a verified role digest."""

import pytest

from scripts import resolve_service_images as resolver
from scripts import verify_backend_release_vector as verifier

PROJECT = 'based-hardware-dev'
SHA = 'a' * 40
DIGEST = 'sha256:' + 'c' * 64
ROLES = {
    'backend': 'api',
    'backend-sync': 'workers',
    'backend-sync-backfill': 'workers',
    'backend-integration': 'workers',
    'backend-listen': 'realtime',
    'llm-gateway': 'gateway',
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


def resolve(raw, *, deploy_targets='all', deploy_gateway=True, inspect=None):
    return resolver.resolve(
        raw,
        project=PROJECT,
        short_sha='aaaaaaa',
        admitted_sha=SHA,
        deploy_targets=deploy_targets,
        deploy_gateway=deploy_gateway,
        inspect=inspect or (lambda ref: pytest.fail(f'unexpected inspect {ref}')),
    )


def test_empty_resolves_every_service_to_the_image_it_ships_today():
    outputs = resolve(' , ', deploy_targets='cloud-run-only', deploy_gateway=False)
    fat = f'gcr.io/{PROJECT}/backend:aaaaaaa'
    assert outputs == {
        'backend': fat,
        'backend_sync': fat,
        'backend_sync_backfill': fat,
        'backend_integration': fat,
        'backend_listen': fat,
        'backend_listen_repository': f'gcr.io/{PROJECT}/backend',
        'backend_listen_digest_args': '',
        'llm_gateway': f'gcr.io/{PROJECT}/llm-gateway:aaaaaaa',
        'llm_gateway_repository': '',
        'llm_gateway_digest': '',
        'release_vector_args': '',
        'opted_in': '',
    }


def test_opt_in_moves_only_the_named_services_onto_their_role_digests():
    api = f'gcr.io/{PROJECT}/backend-api@{DIGEST}'
    workers = f'gcr.io/{PROJECT}/backend-workers@{DIGEST}'
    listen = f'gcr.io/{PROJECT}/backend-realtime@{DIGEST}'
    gateway = f'gcr.io/{PROJECT}/backend-gateway@{DIGEST}'
    configs = {
        api: role_config('api'),
        workers: role_config('workers'),
        listen: role_config('realtime'),
        gateway: role_config('gateway'),
    }
    outputs = resolve(
        f'backend={api}, backend-sync={workers}\nbackend-listen={listen} llm-gateway={gateway}',
        inspect=inspector(configs),
    )
    assert outputs['backend'] == api
    assert outputs['backend_sync'] == workers
    assert outputs['backend_integration'] == f'gcr.io/{PROJECT}/backend:aaaaaaa'
    assert outputs['backend_listen_repository'] == f'gcr.io/{PROJECT}/backend-realtime'
    assert outputs['backend_listen_digest_args'] == f'--set-string image.digest={DIGEST}'
    assert outputs['llm_gateway_repository'] == f'gcr.io/{PROJECT}/backend-gateway'
    assert outputs['llm_gateway_digest'] == DIGEST
    assert outputs['opted_in'] == 'backend backend-listen backend-sync llm-gateway'
    # The gateway is checked by its own deploy step, not the Cloud Run/listen release vector.
    assert outputs['release_vector_args'] == (
        f'--service-image backend={api} --service-image backend-listen={listen} '
        f'--service-image backend-sync={workers}'
    )
    # Every arg the action appends must be one the release-vector verifier accepts.
    pairs = dict(arg.split('=', 1) for arg in outputs['release_vector_args'].split() if arg != '--service-image')
    expectation = verifier.build_expectation(
        commit_sha=SHA,
        deploy_run_id='1',
        deploy_run_attempt='1',
        project=PROJECT,
        region='us-central1',
        environment='dev',
        service_images=pairs,
    )
    assert expectation.image_for('backend') == api
    assert expectation.image_for('backend-integration') == f'gcr.io/{PROJECT}/backend:aaaaaaa'


@pytest.mark.parametrize(
    'raw, message',
    [
        ('backend', 'is not service=image'),
        ('pusher=x', "names 'pusher'"),
        (f'backend=gcr.io/{PROJECT}/backend-api@{DIGEST} backend=gcr.io/{PROJECT}/backend-api@{DIGEST}', 'twice'),
        (f'backend=gcr.io/{PROJECT}/backend-api:aaaaaaa', 'is not gcr.io'),
        (f'backend=gcr.io/{PROJECT}/backend-workers@{DIGEST}', 'is not gcr.io'),
        (f'backend=gcr.io/based-hardware/backend-api@{DIGEST}', 'is not gcr.io'),
        (f'backend=gcr.io/{PROJECT}/backend-api@sha256:abc', 'is not gcr.io'),
    ],
)
def test_malformed_or_foreign_refs_fail_before_any_inspect(raw, message):
    with pytest.raises(resolver.ServiceImageError, match=message):
        resolve(raw)


def test_revision_and_role_must_match_the_admitted_release():
    api = f'gcr.io/{PROJECT}/backend-api@{DIGEST}'
    with pytest.raises(resolver.ServiceImageError, match='labelled revision'):
        resolve(f'backend={api}', inspect=inspector({api: role_config('api', revision='b' * 40)}))
    with pytest.raises(resolver.ServiceImageError, match='OMI_ROLE=api'):
        resolve(f'backend={api}', inspect=inspector({api: role_config('workers')}))


def test_listen_and_gateway_opt_in_need_the_deploy_that_ships_them():
    listen = f'gcr.io/{PROJECT}/backend-realtime@{DIGEST}'
    gateway = f'gcr.io/{PROJECT}/backend-gateway@{DIGEST}'
    with pytest.raises(resolver.ServiceImageError, match='deploy_targets=all'):
        resolve(f'backend-listen={listen}', deploy_targets='cloud-run-only')
    with pytest.raises(resolver.ServiceImageError, match='deploy_gateway=true'):
        resolve(f'llm-gateway={gateway}', deploy_gateway=False)


def test_registry_maps_each_stack_service_to_the_role_the_resolver_checks():
    registry = resolver.json.loads(resolver.REGISTRY_PATH.read_text())
    assert set(resolver.SERVICES) == set(ROLES)
    for service, role in ROLES.items():
        assert registry['services'][service]['role'] == role


def test_cli_writes_github_outputs(tmp_path, capsys):
    output = tmp_path / 'out'
    code = resolver.main(
        [
            '--project',
            PROJECT,
            '--short-sha',
            'aaaaaaa',
            '--admitted-sha',
            SHA,
            '--deploy-targets',
            'cloud-run-only',
            '--deploy-gateway',
            'false',
            '--github-output',
            str(output),
        ]
    )
    assert code == 0
    assert f'backend=gcr.io/{PROJECT}/backend:aaaaaaa\n' in output.read_text()
    assert 'none (every service ships its current image)' in capsys.readouterr().out
    assert (
        resolver.main(
            ['--service-images', 'nope', *['--project', PROJECT, '--short-sha', 'a' * 7]]
            + ['--admitted-sha', SHA, '--deploy-targets', 'all', '--deploy-gateway', 'true']
        )
        == 1
    )
