#!/usr/bin/env python3
"""Validate and etag-fence an image-only update of the production notifications job."""

import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

JOB = 'projects/based-hardware/locations/us-central1/jobs/notifications-job'
JOB_NAMES = {JOB, JOB.replace('/based-hardware/', '/208440318997/')}
API = 'https://run.googleapis.com/v2/'
JOB_TYPE = 'type.googleapis.com/google.cloud.run.v2.Job'
OPERATION = re.compile(r'projects/(?:based-hardware|208440318997)/locations/us-central1/operations/[a-zA-Z0-9_-]+')
CONTAINER = 'notifications-job-1'
REPOSITORY = 'gcr.io/based-hardware/notifications-job'
ROLLBACK = f'{REPOSITORY}@sha256:2a9cc998375712c9a841212bb75f26a76658dcd7e348919d28d299f47ad944f1'
DIGEST = re.compile(r'sha256:[0-9a-f]{64}')
ENDPOINT = 'OMI_LLM_GATEWAY_URL'
BLANK = 'CONVERSATIONS_V3_FIRST_APP_BUILD'
OUTPUT_FIELDS = {
    'uid',
    'generation',
    'createTime',
    'updateTime',
    'deleteTime',
    'expireTime',
    'creator',
    'lastModifier',
    'observedGeneration',
    'terminalCondition',
    'conditions',
    'executionCount',
    'latestCreatedExecution',
    'reconciling',
    'satisfiesPzs',
}
CONFIG_FIELDS = {
    'name',
    'labels',
    'annotations',
    'client',
    'clientVersion',
    'launchStage',
    'binaryAuthorization',
    'template',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def app_container(job):
    containers = job['template']['template']['containers']
    targets = [container for container in containers if container.get('name') == CONTAINER]
    require(len(targets) == 1, 'Expected exactly one notifications-job-1 container')
    return targets[0]


def image_pin(image):
    require(image.startswith(f'{REPOSITORY}@') and DIGEST.fullmatch(image.split('@', 1)[1]), 'Invalid image digest')
    return image


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def registry_pin(image):
    if image.startswith(f'{REPOSITORY}@'):
        return image_pin(image)
    require(re.fullmatch(re.escape(REPOSITORY) + r':[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}', image), 'Unexpected live image')
    digest = command('docker', 'buildx', 'imagetools', 'inspect', '--format', '{{.Manifest.Digest}}', image)
    return image_pin(f'{REPOSITORY}@{digest}')


def verify_candidate(candidate, source):
    image_pin(candidate)
    subprocess.run(['docker', 'pull', '--platform', 'linux/amd64', candidate], check=True)
    revision = command(
        'docker',
        'image',
        'inspect',
        '--format',
        '{{index .Config.Labels "org.opencontainers.image.revision"}}',
        candidate,
    )
    require(revision == source, 'Published image source revision does not match admitted source')


def configuration(job):
    unknown = job.keys() - OUTPUT_FIELDS - CONFIG_FIELDS - {'etag'}
    # An execution token or new API field requires review before this path can replay it.
    require(not unknown, 'Unexpected Cloud Run Job fields')
    require(job.get('name') in JOB_NAMES and not job.get('deleteTime'), 'Unexpected or deleted Cloud Run Job')
    config = {key: value for key, value in job.items() if key in CONFIG_FIELDS}
    config['name'] = JOB
    return config


def literal_env(job):
    entries = app_container(job).get('env', [])
    by_name = {entry['name']: entry for entry in entries}
    require(len(by_name) == len(entries), 'Duplicate environment variable in notifications-job-1')
    return by_name


def normalize_blank(entry):
    if entry == {'name': BLANK}:
        entry['value'] = ''


def compare_env(job, expected):
    by_name = literal_env(job)
    for name in (ENDPOINT, BLANK):
        entry = dict(by_name.get(name, {}))
        normalize_blank(entry)
        require(entry == {'name': name, 'value': expected[name]}, f'Live {name} differs from the rendered literal')


def config_digest(job):
    config = copy.deepcopy(configuration(job))
    container = app_container(config)
    del container['image']
    for entry in container.get('env', []):
        normalize_blank(entry)
    encoded = json.dumps(config, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def assert_projection(job, projection):
    require(config_digest(job) == config_digest(projection), 'Cloud Run Job configuration drift detected')
    require(app_container(job)['image'] == app_container(projection)['image'], 'Unexpected container image')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def request_job(token, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = Request(
        API + path,
        data=data,
        method='PATCH' if data is not None else 'GET',
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
    )
    try:
        with build_opener(NoRedirect()).open(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        # Cloud API diagnostics can include runtime configuration. Log only status.
        if exc.code >= 500:
            raise TimeoutError(f'Cloud Run {request.method} outcome unknown after HTTP {exc.code}') from None
        raise ValueError(f'Cloud Run {request.method} failed with HTTP {exc.code}') from None


def patch_job(request, body, *, validate_only):
    query = '?validateOnly=true' if validate_only else '?validateOnly=false'
    operation = request(JOB + query, body)
    name = operation.get('name', '')
    deadline = time.monotonic() + 300
    if not validate_only and 'error' not in operation:
        require(OPERATION.fullmatch(name), 'Unexpected Cloud Run operation name')
        print(f'Cloud Run update operation: {name}', flush=True)
        while operation.get('done') is not True and 'error' not in operation:
            if time.monotonic() >= deadline:
                raise TimeoutError('Timed out waiting for Cloud Run operation')
            time.sleep(2)
            operation = request(name)
            require(operation.get('name') == name, 'Cloud Run returned a different operation')
    require('error' not in operation, f'Cloud Run operation failed with code {operation.get("error", {}).get("code")}')
    # Cloud Run may return an unpersisted validate-only operation with the
    # proposed resource in metadata. Require the full projection in either form.
    result = operation.get('response' if operation.get('done') is True else 'metadata')
    require(
        isinstance(result, dict) and result.get('@type') == JOB_TYPE, 'Cloud Run did not return a typed Job projection'
    )
    return {key: value for key, value in result.items() if key != '@type'}, name


def require_live_generation(job, generation):
    require(job.get('generation') == generation, 'Cloud Run Job generation differs from approved generation')
    require(
        job.get('observedGeneration') == generation
        and not job.get('reconciling')
        and job.get('terminalCondition', {}).get('state') == 'CONDITION_SUCCEEDED',
        'Cloud Run Job is not reconciled successfully',
    )
    require(job.get('uid') and job.get('etag'), 'Cloud Run Job is missing its UID or etag')


def project_image(job, image):
    projected = copy.deepcopy(configuration(job))
    app_container(projected)['image'] = image
    return {**projected, 'etag': job['etag']}


def change_image(request, *, mode, source, generation, candidate, expected_env, receipt=None):
    baseline = request(JOB)
    require_live_generation(baseline, generation)
    rollback = mode == 'image-only-rollback'
    if not rollback:
        compare_env(baseline, expected_env)
    # The receipt binds the whole non-image configuration, including the
    # previously verified gateway literal. Rollback can therefore work during
    # a gateway outage while still rejecting endpoint or configuration drift.
    digest = config_digest(baseline)
    validate = mode == 'image-only-validate'
    if not validate:
        require(
            receipt['source'] == source
            and receipt['candidate'] == candidate
            and receipt['rollback'] == ROLLBACK
            and receipt['uid'] == baseline['uid']
            and receipt['config_sha256'] == digest,
            'Live job or source differs from the validation receipt',
        )
        approved_generation = int(receipt['generation']) + int(rollback)
        require(int(generation) == approved_generation, 'Generation differs from the validation receipt')

    live_image = app_container(baseline)['image']
    if rollback:
        require(live_image == candidate, 'Rollback requires the exact forward image digest on the live job')
    else:
        require(registry_pin(live_image) == ROLLBACK, 'Current image differs from the pinned rollback digest')

    image = ROLLBACK if rollback else candidate
    target = project_image(baseline, image)
    validated, validation_operation = patch_job(request, target, validate_only=True)
    assert_projection(validated, target)

    details = {
        'job': JOB,
        'uid': baseline['uid'],
        'generation': generation,
        'source': source,
        'candidate': candidate,
        'rollback': ROLLBACK,
        'config_sha256': digest,
        'etag_sha256': hashlib.sha256(baseline['etag'].encode()).hexdigest(),
        'validate_operation': validation_operation,
    }
    if not rollback:
        # Preflight the inverse against the same live resource and etag. At actual
        # rollback time the inverse is validated again against the forward generation.
        inverse = project_image(baseline, ROLLBACK)
        validated_inverse, operation = patch_job(request, inverse, validate_only=True)
        assert_projection(validated_inverse, inverse)
        details['inverse_validate_operation'] = operation

    current = request(JOB)
    require_live_generation(current, generation)
    require(
        current['uid'] == baseline['uid'] and current['etag'] == baseline['etag'],
        'Cloud Run Job identity or etag changed during validation',
    )
    assert_projection(current, baseline)
    if validate:
        return details

    # Carry the original etag through the last GET-to-PATCH race. No retry or
    # etag refresh after conflict. The caller must obtain fresh admission.
    operation = None
    try:
        applied, operation = patch_job(request, target, validate_only=False)
    except (TimeoutError, URLError):
        print('Cloud Run update outcome unknown. Checking live Job without resubmitting.', flush=True)
    else:
        assert_projection(applied, target)
    deadline = time.monotonic() + 120
    next_generation = str(int(generation) + 1)
    while True:
        live = request(JOB)
        require(live['uid'] == baseline['uid'], 'Cloud Run Job identity changed after update')
        if operation is None and live.get('generation') == generation:
            require(live['etag'] == baseline['etag'], 'Cloud Run Job etag drift after ambiguous update')
            assert_projection(live, baseline)
            require(time.monotonic() < deadline, 'Cloud Run update outcome remains unconfirmed')
            time.sleep(2)
            continue
        require(live.get('generation') == next_generation, 'Unexpected post-update Cloud Run Job generation')
        assert_projection(live, target)
        if live.get('observedGeneration') == next_generation and not live.get('reconciling'):
            state = live.get('terminalCondition', {}).get('state')
            require(state != 'CONDITION_FAILED', 'Cloud Run Job reconciliation failed')
            if state == 'CONDITION_SUCCEEDED':
                require_live_generation(live, next_generation)
                break
        require(time.monotonic() < deadline, 'Cloud Run Job reconciliation timed out')
        time.sleep(2)
    return {**details, 'applied_generation': live['generation'], 'installed_image': image, 'apply_operation': operation}


def main(load_expected_env=None):
    mode = os.environ['MODE']
    require(mode in {'image-only-validate', 'image-only-apply', 'image-only-rollback'}, 'Unknown image-only mode')
    rollback = mode == 'image-only-rollback'
    require(rollback == (load_expected_env is None), 'Image-only mode does not match this entry point')
    source = os.environ['RELEASE_SHA']
    generation = os.environ['EXPECTED_GENERATION']
    temp = Path(os.environ['RUNNER_TEMP'])
    receipt_path = temp / 'notifications-image-receipt.json'
    validate = mode == 'image-only-validate'
    receipt = None
    if validate:
        candidate = (temp / 'notifications-pushed-image').read_text().strip()
        tag = f'{REPOSITORY}:{source}-{os.environ["GITHUB_RUN_ID"]}-{os.environ["GITHUB_RUN_ATTEMPT"]}'
        require(registry_pin(tag) == candidate, 'Registry digest differs from the smoked and pushed image')
    else:
        receipt = json.loads((temp / 'notifications-validation' / receipt_path.name).read_text())
        require(
            receipt['job'] == JOB and receipt['source'] == source and receipt['inverse_validate_operation'] is not None,
            'Validation receipt does not prove this source and job',
        )
        candidate = receipt['candidate']
    require(image_pin(candidate) != ROLLBACK, 'Candidate and rollback digests must be distinct')
    if not rollback:
        verify_candidate(candidate, source)
    # Check availability by digest, even when the live job still uses a tag.
    require(
        command('docker', 'buildx', 'imagetools', 'inspect', '--format', '{{.Manifest.Digest}}', ROLLBACK)
        == ROLLBACK.split('@', 1)[1],
        'Pinned rollback image does not resolve',
    )

    expected = load_expected_env() if load_expected_env is not None else None
    token = command('gcloud', 'auth', 'print-access-token')
    require(token, 'Cloud Run access token is missing')

    def request(path, body=None):
        return request_job(token, path, body)

    result = change_image(
        request,
        mode=mode,
        source=source,
        generation=generation,
        candidate=candidate,
        expected_env=expected,
        receipt=receipt,
    )
    rendered = json.dumps(result, indent=2)
    if validate:
        receipt_path.write_text(rendered + '\n', encoding='utf-8')
    print(rendered)


def run_cli(load_expected_env=None):
    try:
        main(load_expected_env)
    except (ValueError, KeyError, TypeError, OSError, URLError, subprocess.CalledProcessError) as exc:
        sys.exit(f'Image-only operation failed: {exc}')


if __name__ == '__main__':
    run_cli()
