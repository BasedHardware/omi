#!/usr/bin/env python3
"""Stage an image-only Backend candidate from the named Ready donor at zero traffic."""

import argparse
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cloud_run_split_canary import decode_plan, gcloud_json, valid_revision
from serving_has import Registry

if __package__:
    from .integration_canary_controller import (
        PROJECT,
        REGION,
        STAMP,
        app,
        identity,
        ready,
        require,
        template,
        template_config,
        write_body,
    )
else:
    from integration_canary_controller import (
        PROJECT,
        REGION,
        STAMP,
        app,
        identity,
        ready,
        require,
        template,
        template_config,
        write_body,
    )

SERVICE = 'backend'
URL = f'https://{REGION}-run.googleapis.com/apis/serving.knative.dev/v1/namespaces/{PROJECT}'
SERVER_ANNOTATIONS = {
    'run.googleapis.com/lastPinned',
    'run.googleapis.com/client-name',
    'run.googleapis.com/client-version',
}


def pinned_traffic(rows):
    allocations, tags = {}, {}
    for row in rows:
        revision, percent = row.get('revisionName', ''), row.get('percent', 0)
        require(
            valid_revision(SERVICE, revision)
            and row.get('latestRevision', False) is False
            and type(percent) is int
            and 0 <= percent <= 100,
            'unpinned_traffic',
        )
        if percent:
            allocations[revision] = allocations.get(revision, 0) + percent
        tag = row.get('tag')
        if tag:
            require(tag not in tags, 'duplicate_tag')
            tags[tag] = revision
    require(sum(allocations.values()) == 100, 'traffic_incomplete')
    return allocations, tags


def stage_body(service, donor, plan, candidate, image, source):
    name = plan['donor']
    identity(service, SERVICE, service=True)
    ready(service, service=True)
    requested = pinned_traffic(service['spec']['traffic'])
    observed = pinned_traffic(service['status']['traffic'])
    require(requested == observed and requested[0] == plan['inverse'], 'named_inverse_mismatch')
    identity(donor, name)
    ready(donor)
    donor_meta = donor['metadata']
    require(
        donor_meta['namespace'] == service['metadata']['namespace']
        and donor_meta['labels']['serving.knative.dev/service'] == SERVICE,
        'donor_identity_mismatch',
    )
    require(
        valid_revision(SERVICE, candidate)
        and candidate not in plan['inverse']
        and candidate not in requested[1].values(),
        'invalid_candidate',
    )
    body = write_body(service)
    cloned = template(donor, candidate)
    for annotation in SERVER_ANNOTATIONS:
        cloned['metadata']['annotations'].pop(annotation, None)
    cloned['metadata']['labels']['commit-sha'] = source
    cloned['metadata']['labels']['release-source-sha'] = source
    ingress = app(cloned['spec'])
    ingress['image'] = image
    env = ingress['env']
    require(
        sum(entry.get('name') == STAMP and 'value' in entry for entry in env) == 1
        and sum(entry.get('name') == STAMP for entry in env) == 1,
        'donor_source_stamp_missing',
    )
    ingress['env'] = [dict(entry, value=source) if entry.get('name') == STAMP else entry for entry in env]
    # All service-level settings, revision references and tags come from the same CAS read.
    body['spec']['template'] = cloned
    return body


def runtime_env_config(entries):
    """Return the comparable runtime-config map, excluding the image source stamp."""
    config = {}
    for entry in entries:
        name = entry.get('name')
        require(isinstance(name, str) and bool(name), 'env_entry_invalid')
        if name == STAMP:
            continue
        if 'value' in entry:
            config[name] = ('value', str(entry['value']))
            continue
        ref = (entry.get('valueFrom') or {}).get('secretKeyRef') or {}
        require(isinstance(ref.get('name'), str) and isinstance(ref.get('key'), str), 'env_entry_invalid')
        config[name] = ('secret', ref['name'], ref['key'])
    return config


def require_inherited_env(entries, expected_state):
    """Refuse a split plan whose inherited donor config is not this source's config.

    The staged candidate is the donor template with only the image and release
    stamp replaced, so an env-changing split plan would promote a runtime config
    that differs from the manifest. Refuse it here, before promotion, instead of
    letting the post-deploy live checks discover it. Only key names are reported.
    """
    require(
        isinstance(expected_state, dict) and SERVICE in (expected_state.get('services') or {}),
        'split_plan_expected_state_incomplete',
    )
    expected = runtime_env_config(expected_state['services'][SERVICE]['env'])
    actual = runtime_env_config(entries)
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(name for name in set(expected) & set(actual) if expected[name] != actual[name])
    require(
        not (missing or extra or changed),
        'split_plan_changes_runtime_env:'
        + ','.join(
            [*(f'-{name}' for name in missing), *(f'+{name}' for name in extra), *(f'~{name}' for name in changed)][:20]
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('plan', 'candidate', 'image', 'source'):
        parser.add_argument('--' + field, required=True)
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--expected-state', type=Path)
    args = parser.parse_args()
    try:
        require(
            os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'),
            'stage_requires_workflow_wif',
        )
        plan = decode_plan(SERVICE, args.plan)
        require(len(plan['inverse']) > 1, 'split_required')
        require(
            re.fullmatch('[0-9a-f]{40}', args.source)
            and re.fullmatch(r'gcr\.io/based-hardware/backend:[0-9a-f]{7,40}', args.image)
            and args.source.startswith(args.image.rsplit(':', 1)[1]),
            'image_input_invalid',
        )
        service_url = URL + '/services/' + SERVICE
        donor = gcloud_json('GET', URL + '/revisions/' + plan['donor'], timeout=30)
        service = gcloud_json('GET', service_url, timeout=30)
        body = stage_body(service, donor, plan, args.candidate, args.image, args.source)
        if args.verify:
            candidate = gcloud_json('GET', URL + '/revisions/' + args.candidate, timeout=30)
            identity(candidate, args.candidate)
            ready(candidate)
            require(
                candidate['metadata']['labels']['serving.knative.dev/service'] == SERVICE
                and candidate['metadata']['namespace'] == service['metadata']['namespace'],
                'candidate_identity_mismatch',
            )
            actual = template_config(candidate)
            for annotation in SERVER_ANNOTATIONS:
                actual['annotations'].pop(annotation, None)
            ingress = app(candidate['spec'])
            status = candidate['status']
            states = [
                row['imageDigest']
                for row in status.get('containerStatuses', [])
                if row.get('name') == ingress.get('name')
            ]
            if len(candidate['spec']['containers']) == 1 and not states:
                states = [status['imageDigest']]
            require(
                len(states) == 1
                and states[0].startswith('gcr.io/based-hardware/backend@sha256:')
                and ingress['image'] in (states[0], args.image)
                and Registry().revision(states[0]) == (args.source, 'label'),
                'candidate_image_source_mismatch',
            )
            # The v1 Revision reports a resolved digest where the template has
            # the commit tag. Normalize only the application image we proved.
            app(actual['spec'])['image'] = args.image
            require(actual == template_config(body['spec']['template']), 'candidate_config_mismatch')
            if args.expected_state is not None:
                require_inherited_env(
                    ingress['env'],
                    json.loads(args.expected_state.read_text(encoding='utf-8')),
                )
        else:
            gcloud_json('PUT', service_url, body=body, timeout=30)
    except Exception:
        # Provider exceptions may embed runtime configuration. Keep them private.
        print('SPLIT_IMAGE_STAGE_REFUSED', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
