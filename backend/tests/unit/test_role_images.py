"""Plan B B2 role-image build, probe, measure and publish steps, without Docker."""

import json
import subprocess

import pytest

from scripts import role_images

SHA = 'a' * 40
OTHER_SHA = 'b' * 40
DIGEST = 'sha256:' + 'c' * 64


class FakeRunner:
    """Records commands; answers from (predicate, CompletedProcess) rules, else success."""

    def __init__(self, rules=()):
        self.rules = list(rules)
        self.commands = []

    def __call__(self, command, **kwargs):
        self.commands.append(command)
        for matches, result in self.rules:
            if matches(command):
                return subprocess.CompletedProcess(command, *result) if isinstance(result, tuple) else result(command)
        return subprocess.CompletedProcess(command, 0, '', '')


def test_every_role_image_builds_from_the_role_dockerfile_plus_listen_edge():
    entries = role_images.role_image_entries(role_images.load_registry())
    by_name = {entry['name']: entry for entry in entries}
    assert list(by_name) == [
        'backend-api',
        'backend-workers',
        'backend-realtime',
        'backend-gateway',
        'backend-pusher',
        'listen-edge',
    ]
    assert {by_name[name]['target'] for name in list(by_name)[:5]} == {
        'api',
        'workers',
        'realtime',
        'gateway',
        'pusher',
    }
    assert by_name['listen-edge'] == {
        'name': 'listen-edge',
        'kind': 'native',
        'role': 'realtime',
        'dockerfile': 'backend/edge/Dockerfile',
        'target': None,
        'context': '.',
        'probe': 'http',
    }
    assert by_name['backend-workers']['entrypoints'] == ['main', 'utils.messaging.maintenance']


def test_build_stamps_the_sha_and_overrides_only_the_python_base():
    entries = {e['name']: e for e in role_images.role_image_entries(role_images.load_registry())}
    api = role_images.build_command(entries['backend-api'], 'omi-role-backend-api:x', SHA, 'python:3.11-slim')
    assert api == [
        'docker',
        'build',
        '--file',
        'backend/Dockerfile.roles',
        '--target',
        'api',
        '--build-arg',
        f'OMI_RELEASE_SHA={SHA}',
        '--build-arg',
        'PYTHON_BASE_IMAGE=python:3.11-slim',
        '--tag',
        'omi-role-backend-api:x',
        '.',
    ]
    edge = role_images.build_command(entries['listen-edge'], 'edge:x', SHA, 'python:3.11-slim')
    assert '--target' not in edge and not any('PYTHON_BASE_IMAGE' in arg for arg in edge)
    assert f'OMI_RELEASE_SHA={SHA}' in edge


def test_tags_are_registry_short_sha_or_local():
    assert role_images.image_tag('backend-api', SHA, 'gcr.io/p/') == 'gcr.io/p/backend-api:aaaaaaaaaaaa'
    assert role_images.image_tag('backend-api', SHA, None) == 'omi-role-backend-api:aaaaaaaaaaaa'


def _build(tmp_path, *argv, run=None):
    args = role_images.parse_args(['build', '--sha', SHA, '--manifest', str(tmp_path / 'm.json'), *argv])
    return role_images.build(args, run=run or FakeRunner())


def test_build_rejects_short_sha_unknown_images_and_failed_builds(tmp_path):
    with pytest.raises(role_images.RoleImageError):
        role_images.build(role_images.parse_args(['build', '--sha', 'abc', '--manifest', 'm']), run=FakeRunner())
    with pytest.raises(role_images.RoleImageError, match='unknown role images'):
        _build(tmp_path, '--images', 'backend-api,nope')
    failing = FakeRunner([(lambda c: c[:2] == ['docker', 'build'], (1, '', ''))])
    with pytest.raises(role_images.RoleImageError, match='docker build failed'):
        _build(tmp_path, run=failing)


def test_baseline_is_measured_but_never_tagged_for_the_registry(tmp_path):
    manifest = _build(tmp_path, '--registry', 'gcr.io/p', '--images', 'backend-api', '--baseline')
    assert [(e['name'], e['kind'], e['tag']) for e in manifest['images']] == [
        ('backend-api', 'python', 'gcr.io/p/backend-api:aaaaaaaaaaaa'),
        ('backend', 'baseline', 'omi-role-backend:aaaaaaaaaaaa'),
    ]


def test_verify_runs_the_target_dependency_probe(tmp_path):
    manifest = _build(tmp_path, '--images', 'backend-gateway')
    runner = FakeRunner()
    role_images.verify(manifest, run=runner)
    smoke = runner.commands[0]
    assert smoke[1].endswith('runtime_image_contracts.py')
    assert smoke[2:] == [
        'smoke',
        '--dockerfile',
        'backend/Dockerfile.roles',
        '--target',
        'gateway',
        '--image',
        'omi-role-backend-gateway:aaaaaaaaaaaa',
    ]
    assert manifest['images'][0]['probe'] == {'ok': True}
    failing = FakeRunner([(lambda c: 'smoke' in c, (3, '', ''))])
    with pytest.raises(role_images.RoleImageError, match='dependency probe failed'):
        role_images.verify(manifest, run=failing)


def _edge_runner(exit_code='0'):
    return FakeRunner(
        [
            (lambda c: c[:2] == ['docker', 'run'], (0, 'cid\n', '')),
            (lambda c: c[:2] == ['docker', 'port'], (0, '127.0.0.1:49153\n', '')),
            (lambda c: c[:2] == ['docker', 'wait'], (0, exit_code + '\n', '')),
        ]
    )


def _edge_entry():
    return {'name': 'listen-edge', 'kind': 'native', 'tag': 'edge:x'}


EDGE_SHA = '0123456789abcdef0123456789abcdef01234567'


def test_native_probe_checks_health_identity_and_clean_drain():
    seen = []

    def http_get(url):
        seen.append(url)
        if url.endswith('/metrics'):
            # The edge bounds release_sha to 12 hex chars (sanitize_release_sha).
            return 200, 'omi_edge_build_info{release_sha="0123456789ab"} 1\n'
        return 200, 'ok'

    runner = _edge_runner()
    result = role_images.probe_native(_edge_entry(), EDGE_SHA, run=runner, http_get=http_get, sleep=lambda _: None)
    assert result['ok'] is True
    assert seen[:2] == ['http://127.0.0.1:49153/healthz', 'http://127.0.0.1:49153/readyz']
    assert ['docker', 'stop', '--time', '30', 'cid'] in runner.commands
    assert runner.commands[-1] == ['docker', 'rm', '--force', 'cid']


def test_native_probe_fails_on_wrong_identity_or_unclean_drain():
    def wrong_identity(url):
        return (200, 'omi_edge_build_info{release_sha="unknown"} 1\n') if url.endswith('/metrics') else (200, '')

    with pytest.raises(role_images.RoleImageError, match='does not export'):
        role_images.probe_native(_edge_entry(), SHA, run=_edge_runner(), http_get=wrong_identity, sleep=lambda _: None)

    def full_sha_label(url):
        # A full 40-char label is not what the binary exports; do not accept it as identity.
        return (200, f'omi_edge_build_info{{release_sha="{EDGE_SHA}"}} 1\n') if url.endswith('/metrics') else (200, '')

    with pytest.raises(role_images.RoleImageError, match='does not export'):
        role_images.probe_native(
            _edge_entry(), EDGE_SHA, run=_edge_runner(), http_get=full_sha_label, sleep=lambda _: None
        )

    def healthy(url):
        return (200, f'omi_edge_build_info{{release_sha="{SHA[:12]}"}} 1') if url.endswith('/metrics') else (200, '')

    runner = _edge_runner(exit_code='137')
    with pytest.raises(role_images.RoleImageError, match='SIGTERM drain'):
        role_images.probe_native(_edge_entry(), SHA, run=runner, http_get=healthy, sleep=lambda _: None)
    assert runner.commands[-1] == ['docker', 'rm', '--force', 'cid']


def test_native_probe_times_out_when_never_ready():
    ticks = iter(range(0, 1000, 10))
    with pytest.raises(role_images.RoleImageError, match='not 200'):
        role_images.probe_native(
            _edge_entry(),
            SHA,
            run=_edge_runner(),
            http_get=lambda url: (503, ''),
            clock=lambda: next(ticks),
            sleep=lambda _: None,
        )


def test_cold_start_is_offline_with_placeholders_and_report_only():
    entry = {'name': 'backend-api', 'kind': 'python', 'tag': 'img', 'entrypoints': ['main'], 'smoke_environment': {}}
    marker = 'OMI_COLD_START ' + json.dumps({'seconds': 12.5, 'error': None})
    runner = FakeRunner([(lambda c: c[:2] == ['docker', 'run'], (0, f'noise\n{marker}\n', ''))])
    result = role_images.cold_start(entry, run=runner)
    assert result['import_seconds'] == 12.5 and result['error'] is None and result['entrypoint'] == 'main'
    command = runner.commands[0]
    assert '--network=none' in command
    assert 'ENCRYPTION_SECRET=0123456789abcdef0123456789abcdef' in command
    crashed = FakeRunner([(lambda c: c[:2] == ['docker', 'run'], (1, '', 'Traceback\nImportError: boom\n'))])
    assert role_images.cold_start(entry, run=crashed)['error'] == 'ImportError: boom'


def _published_manifest():
    return {
        'sha': SHA,
        'registry': 'gcr.io/p',
        'images': [
            {
                'name': 'backend-api',
                'kind': 'python',
                'tag': 'gcr.io/p/backend-api:aaaaaaaaaaaa',
                'probe': {'ok': True},
            },
            {'name': 'backend', 'kind': 'baseline', 'tag': 'omi-role-backend:aaaaaaaaaaaa'},
        ],
    }


def _describe(present):
    state = {'pushed': False}

    def answer(command):
        if command[:2] == ['docker', 'push']:
            state['pushed'] = True
            return subprocess.CompletedProcess(command, 0, '', '')
        ref = command[4]
        if present or state['pushed']:
            return subprocess.CompletedProcess(command, 0, DIGEST + '\n', '')
        return subprocess.CompletedProcess(command, 1, '', f'ERROR: [{ref}] is not found or is not a valid name')

    return answer


def test_publish_pushes_absent_tags_and_records_digests():
    manifest = _published_manifest()
    answer = _describe(present=False)
    runner = FakeRunner([(lambda c: c[:4] == ['gcloud', 'container', 'images', 'describe'] or c[1] == 'push', answer)])
    role_images.publish(manifest, run=runner)
    api = manifest['images'][0]
    assert api['pushed'] is True and api['digest'] == DIGEST
    assert api['ref'] == f'gcr.io/p/backend-api@{DIGEST}'
    assert ['docker', 'push', 'omi-role-backend:aaaaaaaaaaaa'] not in runner.commands


def test_publish_reuses_a_tag_of_the_same_sha_and_refuses_another():
    manifest = _published_manifest()
    runner = FakeRunner(
        [
            (lambda c: c[:4] == ['gcloud', 'container', 'images', 'describe'], _describe(present=True)),
            (lambda c: c[:3] == ['docker', 'buildx', 'imagetools'], (0, SHA + '\n', '')),
        ]
    )
    role_images.publish(manifest, run=runner)
    assert manifest['images'][0]['pushed'] is False
    assert not any(c[:2] == ['docker', 'push'] for c in runner.commands)

    manifest = _published_manifest()
    runner = FakeRunner(
        [
            (lambda c: c[:4] == ['gcloud', 'container', 'images', 'describe'], _describe(present=True)),
            (lambda c: c[:3] == ['docker', 'buildx', 'imagetools'], (0, OTHER_SHA + '\n', '')),
        ]
    )
    with pytest.raises(role_images.RoleImageError, match='already exists'):
        role_images.publish(manifest, run=runner)


def test_publish_refuses_unverified_images_and_unknown_registry_errors():
    manifest = _published_manifest()
    manifest['images'][0]['probe'] = None
    with pytest.raises(role_images.RoleImageError, match='not passed verify'):
        role_images.publish(manifest, run=FakeRunner())
    manifest = _published_manifest()
    denied = FakeRunner([(lambda c: c[0] == 'gcloud', (1, '', 'PERMISSION_DENIED'))])
    with pytest.raises(role_images.RoleImageError, match='could not determine'):
        role_images.publish(manifest, run=denied)


def test_summary_prints_the_service_images_opt_in_line():
    manifest = {
        'sha': SHA,
        'base': None,
        'images': [
            {
                'name': 'backend-api',
                'kind': 'python',
                'role': 'api',
                'size_bytes': 900_000_000,
                'cold_start': {'entrypoint': 'main', 'container_seconds': 20.1, 'import_seconds': 18.0, 'error': None},
                'probe': {'ok': True},
                'digest': DIGEST,
                'ref': f'gcr.io/p/backend-api@{DIGEST}',
            },
            {
                'name': 'backend-workers',
                'kind': 'python',
                'role': 'workers',
                'size_bytes': None,
                'probe': {'ok': True},
                'ref': f'gcr.io/p/backend-workers@{DIGEST}',
            },
            {'name': 'listen-edge', 'kind': 'native', 'role': 'realtime', 'probe': {'ok': True, 'ready_seconds': 0.4}},
        ],
    }
    text = role_images.summary(manifest)
    assert '| `backend-api` | api | 900 | 20.1 / 18.0 (`main`) | ok |' in text
    assert 'ready in 0.4 s' in text
    line = role_images.service_images_line(manifest)
    assert line == (
        f'backend=gcr.io/p/backend-api@{DIGEST} backend-sync=gcr.io/p/backend-workers@{DIGEST} '
        f'backend-sync-backfill=gcr.io/p/backend-workers@{DIGEST} backend-integration=gcr.io/p/backend-workers@{DIGEST}'
    )
    assert line in text


def test_manifest_round_trips_through_the_cli(tmp_path, monkeypatch):
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps({'sha': SHA, 'base': 'python:3.11-slim', 'images': []}))
    assert role_images.main(['summary', '--manifest', str(path)]) == 0
    assert role_images.main(['publish', '--manifest', str(path)]) == 1  # no registry: refuse
