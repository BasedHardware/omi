"""Proposed exact-digest publication; invoked only by the protected CI job."""

import argparse
import image_smoke
import base64
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
from operator_ingress import sha, release_metadata, validate_release
from validate_saved_oci import validate
from registry_access import validate_evidence, permission_hint

DESTINATION = 'gcr.io/based-hardware/jobstore-reconcile-operator'


def validate_qualification(contract, receipt):
    image_smoke.source_refusal_program(contract.get('readiness_sha256'))
    expected = {
        'result': 'NATIVE_AMD64_QUALIFIED_OFFLINE_ONLY',
        'source_sha': contract['source_sha'],
        'source_tree': contract['source_tree'],
        'archive_sha256': contract['archive_sha256'],
        'oci_manifest_digest': contract['oci_manifest_digest'],
        'build_inputs_sha256': contract['build_inputs_sha256'],
        'supervisor_sha256': contract['supervisor_sha256'],
        'tests_run': 58,
        'tests_skipped': 0,
        'uid': 1000,
        'container_network': 'none',
        'real_state_accessed': False,
        'production_calls': False,
        'workflow_sha': os.environ['GITHUB_WORKFLOW_SHA'],
        'run_id': os.environ['GITHUB_RUN_ID'],
    }
    if any(receipt.get(k) != v for k, v in expected.items()):
        raise ValueError('CURRENT_RUN_EXACT_NATIVE_QUALIFICATION_REQUIRED')
    image_smoke.validate_source_refusal(receipt.get('resource_bound_source_refusal', {}), contract['readiness_sha256'])
    host = receipt.get('native_host', {})
    if (
        host.get('system') != 'Linux'
        or host.get('machine') not in ('x86_64', 'amd64')
        or host.get('docker_architecture') not in ('x86_64', 'amd64')
    ):
        raise ValueError('NATIVE_AMD64_RECEIPT_REQUIRED')
    validate_evidence(contract)


def command(argv, env=None):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1200, env=env)
    if result.returncode:
        raise RuntimeError('REGISTRY_COMMAND_FAILED')
    return result.stdout


def publish(contract, directory, receipt, output):
    hint = None
    write_attempted = False

    def progress(state):
        output.write_text(
            json.dumps(
                {
                    'result': 'IN_PROGRESS',
                    'publication_state': state,
                    'image': DESTINATION + '@' + contract['oci_manifest_digest'],
                    'source_sha': contract['source_sha'],
                    'registry_permission_hint': hint,
                    'effective_registry_write': 'UNVERIFIED',
                    'write_attempted': write_attempted,
                    'deployed': False,
                    'runtime_admission': 'CLOSED',
                },
                indent=2,
            )
            + '\n'
        )

    progress('VALIDATING_NO_PUBLICATION_ATTEMPT')
    validate_qualification(contract, receipt)
    validate_release(contract, release_metadata(contract['release_id']))
    archive = directory / 'operator.oci.tar'
    if sha(archive) != contract['archive_sha256']:
        raise ValueError('APPROVED_ARCHIVE_CHANGED')
    checked = validate(archive, contract['source_sha'], contract['build_inputs_sha256'], contract['supervisor_sha256'])
    if checked['manifest_digest'] != contract['oci_manifest_digest']:
        raise ValueError('APPROVED_MANIFEST_CHANGED')
    version = command(['skopeo', '--version']).decode().strip()
    if version != 'skopeo version 1.13.3':
        raise ValueError('QUALIFIED_CI_SKOPEO_VERSION_REQUIRED')
    env = dict(os.environ)
    for key in ('GH_TOKEN', 'GITHUB_TOKEN'):
        env.pop(key, None)
    token = command(['gcloud', 'auth', 'print-access-token'], env).decode().strip()
    if not token or '\n' in token:
        raise ValueError('KEYLESS_WORKFLOW_TOKEN_REQUIRED')
    hint = permission_hint(token)
    progress('CALLER_PERMISSION_HINT_COMPLETE_NO_WRITE_ATTEMPT')
    with tempfile.TemporaryDirectory(prefix='operator-registry-auth-', dir=directory.parent) as temporary:
        auth = Path(temporary) / 'auth.json'
        with open(auth, 'x', opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
            json.dump(
                {'auths': {'gcr.io': {'auth': base64.b64encode(('oauth2accesstoken:' + token).encode()).decode()}}},
                stream,
            )
        token = None
        tag = 'sha256-' + contract['oci_manifest_digest'].split(':')[1]
        target = 'docker://' + DESTINATION + ':' + tag
        before = subprocess.run(
            ['skopeo', 'inspect', '--raw', '--authfile', str(auth), target],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
            env=env,
        )
        if before.returncode == 0:
            import hashlib

            if 'sha256:' + hashlib.sha256(before.stdout).hexdigest() != contract['oci_manifest_digest']:
                raise ValueError('CONFLICTING_EXISTING_PUBLICATION')
            progress('EXACT_MANIFEST_ALREADY_PRESENT_READBACK_PENDING')
        else:
            # Fail on permission/network/unknown failures; accept only the
            # registry's explicit absent-manifest response before a first push.
            if b'manifest unknown' not in before.stderr.lower():
                raise ValueError('DESTINATION_STATE_UNKNOWN')
            write_attempted = True
            progress('PUBLICATION_ATTEMPTED_OUTCOME_UNKNOWN_UNTIL_READBACK')
            command(
                [
                    'skopeo',
                    'copy',
                    '--all',
                    '--preserve-digests',
                    '--dest-authfile',
                    str(auth),
                    'oci-archive:' + str(archive),
                    target,
                ],
                env,
            )
        readback = directory / 'registry-readback.oci.tar'
        command(
            [
                'skopeo',
                'copy',
                '--all',
                '--preserve-digests',
                '--src-authfile',
                str(auth),
                'docker://' + DESTINATION + '@' + contract['oci_manifest_digest'],
                'oci-archive:' + str(readback),
            ],
            env,
        )
        remote = validate(
            readback, contract['source_sha'], contract['build_inputs_sha256'], contract['supervisor_sha256']
        )
        if (
            remote['manifest_digest'] != checked['manifest_digest']
            or remote['layers'] != checked['layers']
            or remote['config_digest'] != checked['config_digest']
        ):
            raise ValueError('REGISTRY_EXACT_MANIFEST_AND_BLOBS_REQUIRED')
    output.write_text(
        json.dumps(
            {
                'result': 'PUBLISHED_EXACT_OPERATOR_ARTIFACT_ONLY',
                'image': DESTINATION + '@' + contract['oci_manifest_digest'],
                'archive_sha256': contract['archive_sha256'],
                'source_sha': contract['source_sha'],
                'workflow_sha': os.environ['GITHUB_WORKFLOW_SHA'],
                'run_id': os.environ['GITHUB_RUN_ID'],
                'registry_permission_hint': hint,
                'write_attempted': write_attempted,
                'effective_registry_write': (
                    'CONFIRMED_BY_SUCCESSFUL_COPY_AND_READBACK'
                    if write_attempted
                    else 'NOT_TESTED_EXISTING_EXACT_ARTIFACT_REUSED'
                ),
                'deployed': False,
                'runtime_admission': 'CLOSED',
            },
            indent=2,
        )
        + '\n'
    )


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--contract', type=Path, required=True)
    p.add_argument('--directory', type=Path, required=True)
    p.add_argument('--qualification', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    try:
        publish(json.loads(a.contract.read_text()), a.directory, json.loads(a.qualification.read_text()), a.output)
    except Exception as error:
        if a.output.exists():
            state = json.loads(a.output.read_text())
            state.update(result='HOLD', failure_class=type(error).__name__)
            a.output.write_text(json.dumps(state, indent=2) + '\n')
        print(json.dumps({'result': 'HOLD', 'failure_class': type(error).__name__}))
        raise SystemExit(2)
