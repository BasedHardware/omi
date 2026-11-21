#!/usr/bin/env python3
"""SCA-3318: one reviewed cap-only correction under the workflow's prod-train lock."""

import argparse
import copy
import http.client
import json
import re
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from verify_projection_pump_inverse import ExpectedInverse, _read, verify
from verify_projection_pump_shape import SERVICE

PROJECT = 'based-hardware'
PROJECT_NUMBER = '208440318997'
REGION = 'us-central1'
RESOURCE = f'projects/{PROJECT}/locations/{REGION}/services/{SERVICE}'
RESOURCE_NAMES = {RESOURCE, f'projects/{PROJECT_NUMBER}/locations/{REGION}/services/{SERVICE}'}
OPERATIONS = f'projects/{PROJECT}/locations/{REGION}/operations/'
OPERATION_NAME = re.compile(
    rf'(?:{re.escape(OPERATIONS)}|projects/{PROJECT_NUMBER}/locations/{REGION}/operations/)[a-zA-Z0-9_-]+'
)
SERVICE_TYPE = 'type.googleapis.com/google.cloud.run.v2.Service'
ORIGIN = 'https://run.googleapis.com/v2/'
BASE = ExpectedInverse(
    'backend-projection-pump-f7060aa-44736735776-1-base',
    'f7060aa1a0c9e3481790d497140096ae99f9b062',
    'gcr.io/based-hardware/backend@sha256:9d9ef7722fee6196d6a16c2b5f0bed7eb3d2854723c3718a65b8917125313eac',
)
BEFORE, AFTER = 20, 4
CAP_ANNOTATION = 'run.googleapis.com/maxScale'
MASK = 'scaling.maxInstanceCount'
PERMISSIONS = {'run.services.get', 'run.services.getIamPolicy', 'run.services.update'}
# Server-managed fields changed by a service update, not part of desired state.
SERVER_FIELDS = {
    'etag',
    'generation',
    'observedGeneration',
    'updateTime',
    'lastModifier',
    'conditions',
    'terminalCondition',
    'reconciling',
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


class RunAPI:
    def __init__(self, token):
        self.token = token
        self.opener = build_opener(NoRedirect())

    def request(self, method, path, body=None):
        if method == 'PATCH':
            stage = 'validate' if path.endswith('validateOnly=true') else 'submit'
        elif OPERATION_NAME.fullmatch(path):
            stage = 'operation-read'
        else:
            stage = 'service-permissions' if method == 'POST' else 'service-read'
        request = Request(
            ORIGIN + path,
            data=None if body is None else json.dumps(body).encode(),
            headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'},
            method=method,
        )
        try:
            with self.opener.open(request, timeout=20) as response:
                data = response.read(2_000_001)
            if len(data) > 2_000_000:
                raise ValueError('Cloud Run response exceeded the read limit')
            doc = json.loads(data)
        except HTTPError as error:
            print(f'PUMP_CAP_API_ERROR stage={stage} status={error.code}', file=sys.stderr, flush=True)
            raise ValueError('Cloud Run request was refused') from None
        except (URLError, OSError, UnicodeError, ValueError, http.client.HTTPException):
            print(f'PUMP_CAP_API_ERROR stage={stage} status=unconfirmed', file=sys.stderr, flush=True)
            raise ValueError('Cloud Run request failed or response was unreadable') from None
        if not isinstance(doc, dict):
            raise ValueError('Cloud Run response was not an object')
        return doc

    def permission_check(self):
        result = self.request('POST', RESOURCE + ':testIamPermissions', {'permissions': sorted(PERMISSIONS)})
        granted = result.get('permissions')
        if not isinstance(granted, list) or set(granted) != PERMISSIONS:
            raise ValueError('workflow identity lacks the permission hint on the exact pump service')

    def service(self):
        return self.request('GET', RESOURCE)

    def patch(self, etag, cap, *, validate_only):
        query = urlencode({'updateMask': MASK, 'validateOnly': str(validate_only).lower()})
        return self.request(
            'PATCH',
            RESOURCE + '?' + query,
            {
                'name': RESOURCE,
                'etag': etag,
                'scaling': {'maxInstanceCount': cap},
            },
        )

    def complete(self, operation, cap, *, submitted, sleep=time.sleep):
        name = operation.get('name')
        if not submitted:
            # Safe shape marker: key names and types only, never values.
            metadata = operation.get('metadata')
            print(
                'PUMP_CAP_VALIDATE_SHAPE '
                f'keys={",".join(sorted(operation))} done={operation.get("done") is True} '
                f'metadata_type={(metadata.get("@type") or "absent") if isinstance(metadata, dict) else "absent" if metadata is None else type(metadata).__name__}',
                flush=True,
            )
            if operation.get('done') is not True and 'error' not in operation:
                # Cloud Run v2 does not persist validate-only operations: GET on
                # the returned name is 404 (run 44862200539). Never poll it.
                # Accept only the operation's own Service preview, and only
                # when it names the exact pump service and the requested cap.
                if (
                    isinstance(metadata, dict)
                    and metadata.get('@type') == SERVICE_TYPE
                    and metadata.get('name') in RESOURCE_NAMES
                    and isinstance(metadata.get('scaling'), dict)
                    and metadata['scaling'].get('maxInstanceCount') == cap
                ):
                    return
                raise ValueError('Cloud Run validation returned no exact pump service preview')
        if submitted or operation.get('done') is not True:
            if not isinstance(name, str) or not OPERATION_NAME.fullmatch(name):
                raise ValueError('Cloud Run returned no bound operation identity')
        if submitted:
            print(f'PUMP_CAP_OPERATION {name}', flush=True)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if 'error' in operation:
                error = operation['error']
                if isinstance(error, dict) and type(error.get('code')) is int:
                    print(f'PUMP_CAP_OPERATION_ERROR code={error["code"]}', file=sys.stderr, flush=True)
                raise ValueError('Cloud Run operation reported failure')
            if operation.get('done') is True:
                response = operation.get('response')
                # AIP-151 allows an error-free terminal validation with a
                # typed, empty response. If the server returns a preview,
                # each echoed identity/cap must agree with the request.
                if not submitted and response == {'@type': SERVICE_TYPE}:
                    return
                if (
                    not isinstance(response, dict)
                    or response.get('@type') != SERVICE_TYPE
                    or response.get('name') not in RESOURCE_NAMES
                    or response.get('scaling', {}).get('maxInstanceCount') != cap
                ):
                    raise ValueError('Cloud Run operation did not return the exact pump service and cap')
                return
            sleep(2)
            operation = self.request('GET', name)
            if operation.get('name') != name:
                raise ValueError('Cloud Run returned a different operation')
        raise ValueError('Cloud Run operation did not settle within the read budget')


def assert_service(service, cap):
    scaling = service.get('scaling', {})
    if (
        service.get('name') not in RESOURCE_NAMES
        or not service.get('uid')
        or not service.get('generation')
        or not service.get('etag')
        or service.get('reconciling', False) is not False
        or service.get('observedGeneration') != service['generation']
        or service.get('terminalCondition', {}).get('state') != 'CONDITION_SUCCEEDED'
        or scaling.get('maxInstanceCount') != cap
    ):
        raise ValueError('Cloud Run service identity, version, readiness or cap drifted')


def snapshot(api, read, cap):
    start = api.service()
    assert_service(start, cap)
    service = read('services', 'describe', SERVICE)
    revision = read('revisions', 'describe', BASE.revision)
    policy = read('services', 'get-iam-policy', SERVICE)
    if service.get('metadata', {}).get('uid') != start['uid'] or not policy.get('etag'):
        raise ValueError('pump UID or IAM policy version was not confirmed')
    if revision.get('status', {}).get('imageDigest') not in (BASE.image, BASE.image.split('@')[1]):
        raise ValueError('pump resolved base image is missing or differs from the approved digest')
    shape = copy.deepcopy(service)
    annotations = shape['metadata']['annotations']
    if annotations.get(CAP_ANNOTATION) != str(cap):
        raise ValueError('service scaling differs between API readbacks')
    # The verifier normally requires max 4. Exclude only the already checked
    # cap mismatch so the interrupted base must pass every other dark check.
    annotations[CAP_ANNOTATION] = str(AFTER)
    verify(shape, revision, policy, BASE, before_first_pin=True)
    if api.service() != start:
        raise ValueError('pump version or shape changed during baseline readback')
    return start, revision, policy


SETTLE_SECONDS = 120


def settled_snapshot(api, read, cap):
    """Wait (read-only, bounded) for Cloud Run to finish reconciling, then snapshot once.

    A done operation can precede `reconciling: false` and `observedGeneration == generation`
    by a few seconds (run 44900134239 refused 5 s after a write that had landed). Only that
    settling state, or a transient read failure, is waited out. A terminal failed condition
    refuses at once, and any other mismatch still refuses in snapshot().
    """
    deadline = time.monotonic() + SETTLE_SECONDS
    attempt = 0
    while True:
        attempt += 1
        try:
            service = api.service()
        except ValueError:
            service = None  # RunAPI already printed a safe PUMP_CAP_API_ERROR marker.
        if service is not None:
            reconciling = service.get('reconciling', False) is not False
            observed = bool(service.get('generation')) and service.get('observedGeneration') == service.get(
                'generation'
            )
            state = service.get('terminalCondition', {}).get('state')
            if not reconciling and observed:
                if state == 'CONDITION_SUCCEEDED':
                    print(f'PUMP_CAP_SETTLED attempts={attempt}', flush=True)
                    return snapshot(api, read, cap)
                if state == 'CONDITION_FAILED':
                    print('PUMP_CAP_SETTLE_FAILED terminal condition failed', file=sys.stderr, flush=True)
                    raise ValueError('Cloud Run service reconciled to a failed condition')
        if time.monotonic() >= deadline:
            print(f'PUMP_CAP_SETTLE_TIMEOUT attempts={attempt}', file=sys.stderr, flush=True)
            raise ValueError('Cloud Run service did not finish reconciling within the read budget')
        print(f'PUMP_CAP_SETTLING attempt={attempt}', flush=True)
        time.sleep(5)


def stable_shape(snapshot_value):
    service, revision, policy = snapshot_value
    config = copy.deepcopy({key: value for key, value in service.items() if key not in SERVER_FIELDS})
    del config['scaling']['maxInstanceCount']
    return config, revision, policy


def recover(api, read, approved_etag):
    api.permission_check()
    before = snapshot(api, read, BEFORE)
    version = before[0]['etag']
    if version != approved_etag:
        raise ValueError('live etag differs from the production-approved input')
    # Inverse target is currently a no-op. Validate the same inverse again
    # against the actual post-write version before reporting success.
    for cap in (AFTER, BEFORE):
        api.complete(api.patch(version, cap, validate_only=True), cap, submitted=False)
    if snapshot(api, read, BEFORE) != before:
        raise ValueError('pump or IAM drift after server validation')
    print(f'PUMP_CAP_VALIDATED service={RESOURCE} forward={BEFORE}->{AFTER} inverse={AFTER}->{BEFORE}', flush=True)
    print(
        'PUMP_CAP_SUBMITTING one version-guarded update; reconcile any interruption before another dispatch', flush=True
    )
    try:
        api.complete(api.patch(version, AFTER, validate_only=False), AFTER, submitted=True)
        after = settled_snapshot(api, read, AFTER)
        if after[0]['etag'] == version or stable_shape(after) != stable_shape(before):
            raise ValueError('post-write version or preserved shape mismatch')
        api.complete(api.patch(after[0]['etag'], BEFORE, validate_only=True), BEFORE, submitted=False)
        if snapshot(api, read, AFTER) != after:
            raise ValueError('pump or IAM drift after inverse validation')
    except (ValueError, OSError, KeyError, TypeError, AttributeError, subprocess.SubprocessError):
        raise ValueError('post-submission state needs independent Release reconciliation; do not retry') from None
    print(
        f'PUMP_CAP_READBACK cap={AFTER} route=LATEST:100 revision={BASE.revision} source={BASE.source} '
        f'image={BASE.image} inverse_cap={BEFORE}',
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--etag', required=True)
    args = parser.parse_args()
    try:
        token = subprocess.run(
            ['gcloud', 'auth', 'print-access-token'],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()
        if not token or not args.etag:
            raise ValueError('workflow bearer token or approved etag is missing')
        recover(RunAPI(token), lambda *args: _read(PROJECT, REGION, *args), args.etag)
    except (ValueError, OSError, KeyError, TypeError, AttributeError, subprocess.SubprocessError):
        # API responses and CLI errors may contain environment or access data.
        print('PUMP_CAP_REFUSED: see safe stage markers; reconcile any submitted write before retry', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
