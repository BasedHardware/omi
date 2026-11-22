#!/usr/bin/env python3
"""Verify the live projection-pump revision before using it as an inverse (dark, or activated once pinned)."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from cloud_run_traffic_snapshot import capture_snapshot
from verify_projection_pump_shape import PROCESS_ROLE, SERVICE, _application, evaluate

REPOSITORY = 'gcr.io/based-hardware/backend'
DARK_ENV = {
    'BATCH_PIPELINE_PROJECTION_PUMP_ENABLED': 'false',
    'FIRESTORE_READ_LEDGER_SERVICE': SERVICE,
    'OMI_PROCESS_ROLE': PROCESS_ROLE,
}
PUMP_FLAG = 'BATCH_PIPELINE_PROJECTION_PUMP_ENABLED'
# SCA-3318: after step 2 the pinned, routed inverse is the activated pump. Only its pump flag may
# differ from DARK_ENV, and only as the exact literal 'true'. A base before its first pin and a new
# create stay dark.
ACTIVE_ENV = {**DARK_ENV, PUMP_FLAG: 'true'}


def expected_routed_env(app: Mapping[str, Any], *, pinned_disposition: bool) -> Mapping[str, str]:
    if not pinned_disposition:
        return DARK_ENV
    flags = [e for e in app.get('env', []) if e.get('name') == PUMP_FLAG]
    if len(flags) == 1 and 'valueFrom' not in flags[0] and flags[0].get('value') == 'true':
        return ACTIVE_ENV
    return DARK_ENV


@dataclass(frozen=True)
class ExpectedInverse:
    revision: str
    source: str
    image: str
    disposition: str = ''

    def __post_init__(self) -> None:
        if len(self.revision) > 63 or not re.fullmatch(rf'{SERVICE}-[a-z0-9](?:[a-z0-9-]*[a-z0-9])?', self.revision):
            raise ValueError('expected a named projection pump revision')
        if not re.fullmatch(r'[0-9a-f]{40}', self.source):
            raise ValueError('expected a full source SHA for the projection pump inverse')
        if not re.fullmatch(rf'{re.escape(REPOSITORY)}@sha256:[0-9a-f]{{64}}', self.image):
            raise ValueError('expected an immutable fat backend image for the projection pump inverse')

    @classmethod
    def from_disposition(cls, value: str) -> ExpectedInverse:
        fields = value.split()
        if len(fields) != 4 or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', fields[0]):
            raise ValueError(
                'existing pump requires a recorded Release disposition: comment UUID, revision, SHA, image'
            )
        return cls(*fields[1:], disposition=fields[0])


def verify(
    service: Mapping[str, Any],
    revision: Mapping[str, Any],
    iam_policy: Mapping[str, Any],
    expected: ExpectedInverse,
    *,
    before_first_pin: bool,
) -> None:
    # Check both routing views, including zero-percent tags. The inverse must be
    # a single named revision. Only the new base may follow LATEST before its pin.
    status = service.get('status', {})
    for section in ('spec', 'status'):
        traffic = service.get(section, {}).get('traffic')
        if not isinstance(traffic, list) or len(traffic) != 1 or not isinstance(traffic[0], dict):
            raise ValueError(f'{section}.traffic must have a single untagged 100% target')
        route = traffic[0]
        if (
            route.get('percent') != 100
            or route.get('tag')
            or (route.get('latestRevision', False) is not before_first_pin)
        ):
            raise ValueError(f'{section}.traffic must route 100% to the expected untagged revision')
        target = route.get('revisionName')
        if before_first_pin and section == 'spec' and target is None:
            target = status.get('latestReadyRevisionName')
        if target != expected.revision:
            raise ValueError(f'{section}.traffic does not route to the expected revision')
    if before_first_pin and (
        status.get('latestReadyRevisionName') != expected.revision
        or status.get('latestCreatedRevisionName') != expected.revision
    ):
        raise ValueError('LATEST does not resolve to the expected base revision')

    metadata = revision.get('metadata', {})
    if (
        metadata.get('name') != expected.revision
        or metadata.get('labels', {}).get('serving.knative.dev/service') != SERVICE
    ):
        raise ValueError('revision identity does not match the expected pump inverse')
    revision_status = revision.get('status', {})
    ready = [c.get('status') for c in revision_status.get('conditions', []) if c.get('type') == 'Ready']
    if ready != ['True']:
        raise ValueError('serving revision is not Ready')
    # Inspect the serving Revision, which is immutable and may differ from the
    # service template after a no-traffic candidate has been deployed.
    revision_spec = revision.get('spec', {})
    app = _application(revision_spec)
    if app.get('image') != expected.image:
        raise ValueError('serving revision image does not match the expected digest')
    resolved_digest = revision_status.get('imageDigest')
    if resolved_digest and resolved_digest not in (expected.image, expected.image.split('@')[1]):
        raise ValueError('serving revision resolved image digest does not match')
    stamps = [e for e in app.get('env', []) if e.get('name') == 'OMI_BACKEND_RELEASE_SHA']
    if len(stamps) != 1 or stamps[0].get('value') != expected.source or 'valueFrom' in stamps[0]:
        raise ValueError('serving revision source stamp does not match')

    errors = evaluate(
        service,
        iam_policy,
        revision=expected.revision,
        manifest_env=expected_routed_env(app, pinned_disposition=bool(expected.disposition) and not before_first_pin),
        revision_document=revision,
    )
    if errors:
        raise ValueError('; '.join(errors))


def _read(project: str, region: str, *args: str) -> dict[str, Any]:
    command = ['gcloud', 'run', *args, f'--project={project}', f'--region={region}', '--format=json']
    result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=60)
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        raise ValueError(f'gcloud run {args[0]} {args[1]} did not return a JSON object')
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--region', required=True)
    expectation = parser.add_mutually_exclusive_group(required=True)
    expectation.add_argument('--disposition', help='Release comment UUID, revision, SHA and digest-pinned image')
    expectation.add_argument('--new-base', nargs=3, metavar=('REVISION', 'SHA', 'IMAGE'))
    parser.add_argument('--before-first-pin', action='store_true')
    parser.add_argument('--snapshot', type=Path, help='Capture the exact verified traffic readback for restoration')
    args = parser.parse_args()
    if args.before_first_pin and args.snapshot:
        parser.error('LATEST is allowed only when verifying a base before its pin')
    try:
        expected = (
            ExpectedInverse(*args.new_base) if args.new_base else ExpectedInverse.from_disposition(args.disposition)
        )
        if (args.new_base or args.before_first_pin) and not expected.revision.endswith('-base'):
            # A pre-pin check (a new create, or an existing service still routed via LATEST,
            # SCA-3318) is only ever for the dark base revision.
            raise ValueError('expected the base revision before its pin')
        service = _read(args.project, args.region, 'services', 'describe', SERVICE)
        revision = _read(args.project, args.region, 'revisions', 'describe', expected.revision)
        iam = _read(args.project, args.region, 'services', 'get-iam-policy', SERVICE)
        verify(service, revision, iam, expected, before_first_pin=args.before_first_pin)
        if args.snapshot:
            snapshot = capture_snapshot(
                project=args.project,
                region=args.region,
                services=[SERVICE],
                fetcher=lambda **_: service,
            )
            args.snapshot.parent.mkdir(parents=True, exist_ok=True)
            args.snapshot.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f'ERROR [{SERVICE}]: {exc}', file=sys.stderr)
        print('Stop and record a Release disposition before recovering an existing pump service.', file=sys.stderr)
        return 1

    print(f'Verified serving pump inverse {expected.revision}, source {expected.source}, image {expected.image}.')
    if expected.disposition:
        print(f'Release disposition (operator-supplied): {expected.disposition}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
