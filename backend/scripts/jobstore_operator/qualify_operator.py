"""Proposed native CI qualification of the fixed image, without cloud/network in containers."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import tarfile
import tempfile
import image_smoke
from operator_ingress import sha
from validate_saved_oci import validate


def native_host():
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'amd64'):
        raise ValueError('NATIVE_LINUX_AMD64_HOST_REQUIRED')
    endpoint = json.loads(
        subprocess.check_output(
            ['docker', 'context', 'inspect', '--format', '{{json .Endpoints.docker.Host}}'], text=True, timeout=10
        )
    )
    if not endpoint.startswith('unix://'):
        raise ValueError('LOCAL_DOCKER_REQUIRED')
    info = json.loads(subprocess.check_output(['docker', 'info', '--format', '{{json .}}'], text=True, timeout=10))
    if (
        info['OSType'] != 'linux'
        or info['Architecture'] not in ('x86_64', 'amd64')
        or info['KernelVersion'] != platform.release()
    ):
        raise ValueError('NATIVE_HOST_DOCKER_BINDING_REQUIRED')
    driver_type = dict(info.get('DriverStatus') or []).get('driver-type')
    if driver_type == 'io.containerd.snapshotter.v1':
        image_store = 'containerd'
    elif driver_type is None and info.get('Driver') == 'overlay2':
        image_store = 'classic-overlay2'
    else:
        raise ValueError('DOCKER_IMAGE_STORE_IDENTITY_UNKNOWN')
    return {
        'system': platform.system(),
        'machine': platform.machine(),
        'kernel': platform.release(),
        'docker_architecture': info['Architecture'],
        'docker_version': info['ServerVersion'],
        'image_store': image_store,
    }


def runtime_config(config):
    if not isinstance(config, dict):
        raise ValueError('LOADED_RUNTIME_CONFIG_REQUIRED')
    # Docker exposes additional Go zero-value/default fields. Compare every
    # non-default runtime field, including fields absent in the saved config.
    return {key: value for key, value in config.items() if value not in (None, '', False, [], {}, 0)}


def bind_loaded_image(actual, checked, host):
    image_id = actual.get('Id')
    descriptor = actual.get('Descriptor')
    if host['image_store'] == 'classic-overlay2':
        if image_id != checked['config_digest']:
            raise ValueError('LOADED_CONFIG_DIGEST_CHANGED')
        if descriptor is not None:
            raise ValueError('CLASSIC_IMAGE_STORE_DESCRIPTOR_UNEXPECTED')
        binding = 'classic-config-digest'
    elif host['image_store'] == 'containerd':
        if (
            image_id != checked['manifest_digest']
            or not isinstance(descriptor, dict)
            or descriptor.get('digest') != checked['manifest_digest']
            or descriptor.get('mediaType') != 'application/vnd.oci.image.manifest.v1+json'
        ):
            raise ValueError('LOADED_MANIFEST_IDENTITY_CHANGED')
        binding = 'containerd-manifest-descriptor'
    else:
        raise ValueError('DOCKER_IMAGE_STORE_IDENTITY_UNKNOWN')
    if actual.get('Os') != 'linux' or actual.get('Architecture') != 'amd64' or actual.get('Variant') not in (None, ''):
        raise ValueError('LOADED_LINUX_AMD64_REQUIRED')
    if actual.get('RootFS') != {
        'Type': 'layers',
        'Layers': [row['diff_id'] for row in checked['layers']],
    } or runtime_config(actual.get('Config')) != runtime_config(checked['config']['config']):
        raise ValueError('LOADED_IMAGE_CONFIGURATION_CHANGED')
    return image_id, binding


def inspect_tag(tag):
    result = subprocess.run(['docker', 'image', 'inspect', tag], capture_output=True, text=True, timeout=10)
    if result.returncode == 0:
        images = json.loads(result.stdout)
        if len(images) != 1:
            raise ValueError('ONE_LOADED_IMAGE_REQUIRED')
        return images[0]
    if 'No such image' in result.stderr:
        return None
    raise ValueError('DOCKER_IMAGE_INVENTORY_UNKNOWN')


@contextmanager
def owned_loaded_image(archive, tag, checked, host, cleanup_output):
    # Ownership is established BEFORE load: even a failed/timed-out client can
    # leave a daemon-created tag. Never touch a tag that existed on entry.
    if inspect_tag(tag) is not None:
        raise ValueError('PREEXISTING_TAG_REFUSED_NO_SHARED_IMAGE_REMOVAL')
    load_returned = False
    try:
        subprocess.run(['docker', 'load', '-i', str(archive)], check=True, stdout=subprocess.DEVNULL, timeout=600)
        load_returned = True
        actual = inspect_tag(tag)
        if actual is None:
            raise ValueError('LOADED_TAG_MISSING')
        yield bind_loaded_image(actual, checked, host)
    finally:
        cleanup = {
            'tag': tag,
            'load_returned_successfully': load_returned,
            'result': 'CLEANUP_OUTCOME_UNKNOWN',
            'removed': False,
        }
        try:
            if inspect_tag(tag) is not None:
                # Exact owned tag only: no force, image-ID deletion or prune.
                subprocess.run(['docker', 'image', 'rm', tag], stdout=subprocess.DEVNULL, check=True, timeout=60)
                cleanup['removed'] = True
                if inspect_tag(tag) is not None:
                    raise ValueError('OWNED_TAG_REMOVAL_NOT_CONFIRMED')
            cleanup['result'] = 'OWNED_TAG_ABSENT' if load_returned else 'TAG_ABSENT_AT_CHECK_LOAD_OUTCOME_UNCERTAIN'
        finally:
            cleanup_output.write_text(json.dumps(cleanup, indent=2) + '\n')


def fixture_files(archive_path, target):
    with tarfile.open(archive_path, 'r:gz') as archive:
        members = archive.getmembers()
        if len(members) > 64 or len({m.name for m in members}) != len(members):
            raise ValueError('FIXTURE_MEMBER_SET_REFUSED')
        for member in members:
            name = Path(member.name)
            if not member.isfile() or name.is_absolute() or '..' in name.parts or member.size > 1024 * 1024:
                raise ValueError('FIXTURE_PATH_OR_TYPE_REFUSED')
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, path.open('xb') as output:
                output.write(source.read())
            path.chmod(0o644)
    for path in target.rglob('*'):
        if path.is_dir():
            path.chmod(0o755)
    manifest = json.loads((target / 'artifact-manifest.json').read_text())
    if set(m.name for m in members) != {r['path'] for r in manifest['files']} | {'artifact-manifest.json'}:
        raise ValueError('FIXTURE_MANIFEST_SET_CHANGED')
    for row in manifest['files']:
        path = target / row['path']
        if path.stat().st_size != row['bytes'] or sha(path) != row['sha256']:
            raise ValueError('FIXTURE_MANIFEST_BYTES_CHANGED')
    return manifest


def qualify(contract, archive, fixtures, output):
    source_program = image_smoke.source_refusal_program(contract.get('readiness_sha256'))
    host = native_host()
    if (
        archive.stat().st_size != contract['archive_bytes']
        or sha(archive) != contract['archive_sha256']
        or fixtures.stat().st_size != contract['fixture']['bytes']
        or sha(fixtures) != contract['fixture']['sha256']
    ):
        raise ValueError('EXACT_ARCHIVE_AND_FIXTURES_REQUIRED')
    checked = validate(archive, contract['source_sha'], contract['build_inputs_sha256'], contract['supervisor_sha256'])
    if checked['manifest_digest'] != contract['oci_manifest_digest']:
        raise ValueError('EXACT_MANIFEST_REQUIRED')
    tag = contract['loaded_tag']
    # This proposal intentionally requires an isolated existing CI runner.
    with owned_loaded_image(archive, tag, checked, host, output.with_suffix('.cleanup.json')) as (image_id, binding):
        source_refusal = json.loads(
            image_smoke.run_container(
                [
                    '--entrypoint=/opt/operator-venv/bin/python',
                    image_id,
                    '-c',
                    source_program,
                ],
                readiness=True,
            )
        )
        image_smoke.validate_source_refusal(source_refusal, contract['readiness_sha256'])
        smoke = image_smoke.run_container(
            ['--entrypoint=/opt/operator-venv/bin/python', image_id, '-c', image_smoke.PROGRAM]
        )
        with tempfile.TemporaryDirectory(prefix='operator-native-fixtures-', dir=output.parent) as temporary:
            target = Path(temporary)
            target.chmod(0o755)
            manifest = fixture_files(fixtures, target)
            if manifest['source_sha'] != contract['source_sha']:
                raise ValueError('FIXTURE_SOURCE_CHANGED')
            tests = image_smoke.run_container(
                [
                    '--mount',
                    f'type=bind,src={target},dst=/checks,readonly',
                    '--workdir=/checks',
                    '--entrypoint=/opt/operator-venv/bin/python',
                    image_id,
                    '-m',
                    'unittest',
                    'discover',
                    '-s',
                    'tests',
                    '-v',
                ]
            )
            count = re.search(r'^Ran (\d+) tests? in ', tests, re.MULTILINE)
            if not count or int(count.group(1)) != 58 or tests.strip().splitlines()[-1] != 'OK':
                raise ValueError('ALL_58_NATIVE_CASES_WITHOUT_SKIPS_REQUIRED')
        smoke += image_smoke.run_container([image_id], hold=True)
        receipt = {
            'result': 'NATIVE_AMD64_QUALIFIED_OFFLINE_ONLY',
            'native_host': host,
            'source_sha': contract['source_sha'],
            'source_tree': contract['source_tree'],
            'archive_sha256': contract['archive_sha256'],
            'oci_manifest_digest': contract['oci_manifest_digest'],
            'build_inputs_sha256': contract['build_inputs_sha256'],
            'supervisor_sha256': contract['supervisor_sha256'],
            'loaded_image_id': image_id,
            'loaded_identity_binding': binding,
            'config_digest': checked['config_digest'],
            'tests_run': 58,
            'resource_bound_source_refusal': source_refusal,
            'tests_skipped': 0,
            'uid': 1000,
            'container_network': 'none',
            'real_state_accessed': False,
            'production_calls': False,
            'workflow_sha': os.environ['GITHUB_WORKFLOW_SHA'],
            'run_id': os.environ['GITHUB_RUN_ID'],
            'finished_at': datetime.now(timezone.utc).isoformat(),
        }
    # Emit qualification only after exact-tag cleanup also completed.
    output.write_text(json.dumps(receipt, indent=2) + '\n')
    output.with_suffix('.log').write_text(smoke + '\n' + tests)
    return receipt


if __name__ == '__main__':

    def deadline(*_):
        raise TimeoutError('NATIVE_QUALIFICATION_DEADLINE')

    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(1200)
    p = argparse.ArgumentParser()
    p.add_argument('--contract', type=Path, required=True)
    p.add_argument('--directory', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    try:
        c = json.loads(a.contract.read_text())
        qualify(c, a.directory / 'operator.oci.tar', a.directory / c['fixture']['name'], a.output)
    except Exception as error:
        a.output.with_suffix('.failure.json').write_text(
            json.dumps(
                {'result': 'HOLD', 'failure_class': type(error).__name__, 'native_amd64_qualified': False}, indent=2
            )
            + '\n'
        )
        if isinstance(error, RuntimeError):
            a.output.with_suffix('.failure.log').write_text(str(error)[:24000])
        print(json.dumps({'result': 'HOLD', 'failure_class': type(error).__name__}))
        raise SystemExit(2)
