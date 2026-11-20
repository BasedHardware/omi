#!/usr/bin/env python3
"""Read back the access and shape backend-projection-pump must keep (SCA-3120).

Offline evaluation of a ``gcloud run services describe --format=json`` document
and its ``get-iam-policy`` document, written by the deploy-projection-pump
composite before traffic moves. It fails when the service is reachable from
outside the VPC, has any invoker, is not fixed at four always-allocated 2 vCPU /
4Gi instances, or its candidate revision does not carry the projection-pump process role
and the dark batch settings the rendered runtime manifest declares. It never calls a
cloud API itself.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

SERVICE = 'backend-projection-pump'
FIXED_INSTANCES = '4'
TIMEOUT_SECONDS = 3600
CONCURRENCY = 80
CPU_LIMIT = '2'
MEMORY_LIMIT = '4Gi'
NON_INVOKING_ROLES = frozenset({'roles/run.viewer'})
PUBLIC_MEMBERS = frozenset({'allUsers', 'allAuthenticatedUsers'})
PROCESS_ROLE = 'projection_pump'
# Unconditional: the pump never runs the serving loops, and its startup is always the pump's
# isolated set (config/process_role.py). Only the pump flag and ledger identity follow the manifest.
FIXED_ENV = {'BATCH_PIPELINE_SERVING_ENABLED': 'false', 'OMI_PROCESS_ROLE': PROCESS_ROLE}
MANIFEST_ENV = ('BATCH_PIPELINE_PROJECTION_PUMP_ENABLED', 'FIRESTORE_READ_LEDGER_SERVICE', 'OMI_PROCESS_ROLE')


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _application(template_spec: Mapping[str, Any]) -> Mapping[str, Any]:
    containers = [item for item in template_spec.get('containers') or [] if isinstance(item, Mapping)]
    application = [item for item in containers if item.get('name') != 'collector']
    return application[0] if len(application) == 1 else {}


def _ingress_env(template_spec: Mapping[str, Any]) -> dict[str, str]:
    env: dict[str, str] = {}
    seen: set[str] = set()
    for entry in _application(template_spec).get('env') or []:
        if isinstance(entry, Mapping) and isinstance(name := entry.get('name'), str):
            if name in seen:
                env.pop(name, None)
            elif 'valueFrom' not in entry and isinstance(entry.get('value'), str):
                env[name] = entry['value']
            seen.add(name)
    return env


def expected_env(state: Mapping[str, Any]) -> dict[str, str]:
    entries = _mapping(_mapping(state.get('services')).get(SERVICE)).get('env')
    if not isinstance(entries, list):
        raise ValueError(f'rendered state has no env for {SERVICE}')
    rendered = {
        str(entry['name']): str(entry['value'])
        for entry in entries
        if isinstance(entry, Mapping) and 'name' in entry and 'value' in entry
    }
    return {name: rendered.get(name, '') for name in MANIFEST_ENV}


def evaluate(
    service: Mapping[str, Any],
    iam_policy: Mapping[str, Any],
    *,
    revision: str,
    manifest_env: Mapping[str, str],
    revision_document: Mapping[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    metadata = _mapping(service.get('metadata'))
    annotations = _mapping(metadata.get('annotations'))
    spec = _mapping(service.get('spec'))
    template = revision_document if revision_document is not None else _mapping(spec.get('template'))
    template_metadata = _mapping(template.get('metadata'))
    template_annotations = _mapping(template_metadata.get('annotations'))
    template_spec = _mapping(template.get('spec'))

    if metadata.get('name') != SERVICE:
        errors.append(f'service name is not {SERVICE}')
    if annotations.get('run.googleapis.com/ingress') != 'internal':
        errors.append('ingress must be internal')
    if annotations.get('run.googleapis.com/invoker-iam-disabled', 'false') != 'false':
        errors.append('invoker IAM check must be enabled')
    for binding in iam_policy.get('bindings') or []:
        members = set(_mapping(binding).get('members') or [])
        public = sorted(members & PUBLIC_MEMBERS)
        if public:
            errors.append(f'IAM role {_mapping(binding).get("role")} grants public members {public}')
        # Restrict direct bindings to known read-only permissions. Cloud Run
        # admin, developer, editor and custom roles can also grant route invocation.
        role = _mapping(binding).get('role')
        if members and role not in NON_INVOKING_ROLES:
            errors.append(f'{role} must have no members, found {sorted(members)}')
    if template_metadata.get('name') != revision:
        errors.append(f'template revision is not {revision}')
    for key in ('autoscaling.knative.dev/minScale', 'autoscaling.knative.dev/maxScale'):
        if str(template_annotations.get(key, '')) != FIXED_INSTANCES:
            errors.append(f'{key} must be {FIXED_INSTANCES}')
    # A service-level bound (config-train) overrides the template; it may be absent or equal.
    for key in ('run.googleapis.com/minScale', 'run.googleapis.com/maxScale'):
        if key in annotations and str(annotations[key]) != FIXED_INSTANCES:
            errors.append(f'service-level {key} must be absent or {FIXED_INSTANCES}')
    if annotations.get('run.googleapis.com/scalingMode', 'automatic') != 'automatic':
        errors.append('service scaling mode must be automatic with fixed bounds')
    if str(template_annotations.get('run.googleapis.com/cpu-throttling', '')).lower() != 'false':
        errors.append('CPU must be always allocated (cpu-throttling false)')
    if template_spec.get('timeoutSeconds') != TIMEOUT_SECONDS:
        errors.append(f'timeoutSeconds must be {TIMEOUT_SECONDS}')
    if template_spec.get('containerConcurrency') != CONCURRENCY:
        errors.append(f'containerConcurrency must be {CONCURRENCY}')
    limits = _mapping(_mapping(_application(template_spec).get('resources')).get('limits'))
    if str(limits.get('cpu', '')) != CPU_LIMIT or str(limits.get('memory', '')) != MEMORY_LIMIT:
        errors.append(f'application container limits must be cpu {CPU_LIMIT} and memory {MEMORY_LIMIT}')
    env = _ingress_env(template_spec)
    if not env:
        errors.append('revision has no unambiguous application container env')
    for name, value in FIXED_ENV.items():
        if env.get(name) != value:
            errors.append(f'{name} must be {value!r} on {SERVICE}')
    for name, value in manifest_env.items():
        if env.get(name) != value:
            errors.append(f'{name} must match the rendered manifest value {value!r}')
    if manifest_env.get('FIRESTORE_READ_LEDGER_SERVICE') != SERVICE:
        errors.append(f'rendered FIRESTORE_READ_LEDGER_SERVICE must be {SERVICE}')
    if manifest_env.get('OMI_PROCESS_ROLE') != PROCESS_ROLE:
        errors.append(f'rendered OMI_PROCESS_ROLE must be {PROCESS_ROLE}')
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--service', type=Path, required=True, help='gcloud run services describe --format=json')
    parser.add_argument('--iam-policy', type=Path, required=True, help='gcloud run services get-iam-policy JSON')
    parser.add_argument('--revision', required=True)
    parser.add_argument('--expected-env-state', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        errors = evaluate(
            json.loads(args.service.read_text(encoding='utf-8')),
            json.loads(args.iam_policy.read_text(encoding='utf-8')),
            revision=args.revision,
            manifest_env=expected_env(json.loads(args.expected_env_state.read_text(encoding='utf-8'))),
        )
    except (OSError, ValueError) as error:
        errors = [str(error)]
    for error in errors:
        print(f'ERROR [{SERVICE}]: {error}', file=sys.stderr)
    if not errors:
        print(
            f'{SERVICE}: internal ingress, no public invoker, fixed {FIXED_INSTANCES}/{FIXED_INSTANCES}, pump role, dark contract'
        )
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
