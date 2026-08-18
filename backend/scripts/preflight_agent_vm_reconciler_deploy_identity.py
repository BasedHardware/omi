#!/usr/bin/env python3
"""Fail closed if production cannot attach the Agent VM reconciler job identity.

SCA-323 / workflow 32012710785 rolled back a proven desktop-backend candidate
because the CI deployer lacked iam.serviceAccounts.actAs on the absent
agent-vm-reconciler@based-hardware.iam.gserviceaccount.com identity after
traffic had already been routed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

PROD_PROJECT = 'based-hardware'
PROD_DEPLOYER = 'josancamon-mb-pro-2@based-hardware.iam.gserviceaccount.com'
PROD_RUNTIME_SERVICE_ACCOUNT = 'agent-vm-reconciler@based-hardware.iam.gserviceaccount.com'
REQUIRED_ROLE = 'roles/iam.serviceAccountUser'
INCIDENT = (
    'SCA-323 / workflow 32012710785: production desktop-backend rolled back after '
    'candidate probes because the CI deployer lacked iam.serviceAccounts.actAs on '
    'the absent agent-vm-reconciler runtime identity.'
)

GcloudRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class ProductionIdentity:
    project: str
    deployer: str
    runtime_service_account: str
    required_role: str = REQUIRED_ROLE


PRODUCTION = ProductionIdentity(
    project=PROD_PROJECT,
    deployer=PROD_DEPLOYER,
    runtime_service_account=PROD_RUNTIME_SERVICE_ACCOUNT,
)


class PreflightError(Exception):
    """A deterministic identity-prerequisite failure."""


def _run_gcloud(args: Sequence[str], *, runner: GcloudRunner | None = None) -> subprocess.CompletedProcess[str]:
    command = ['gcloud', *args]
    if runner is not None:
        return runner(command)
    return subprocess.run(command, check=False, capture_output=True, text=True)


def _fail(message: str) -> None:
    raise PreflightError(f'{message} {INCIDENT}')


def _binding_is_unconditional(binding: Mapping[str, Any]) -> bool:
    condition = binding.get('condition')
    return condition in (None, {}, '')


def _members(binding: Mapping[str, Any]) -> set[str]:
    raw = binding.get('members') or ()
    if isinstance(raw, str):
        return {raw}
    return {member for member in raw if isinstance(member, str)}


def parse_identity_args(argv: Sequence[str] | None = None) -> ProductionIdentity:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--deployer', default=PROD_DEPLOYER)
    parser.add_argument('--runtime-service-account', default=PROD_RUNTIME_SERVICE_ACCOUNT)
    args = parser.parse_args(argv)
    identity = ProductionIdentity(
        project=args.project,
        deployer=args.deployer,
        runtime_service_account=args.runtime_service_account,
    )
    if identity != PRODUCTION:
        _fail(
            'production Agent VM reconciler deploy identity is pinned to '
            f'project={PRODUCTION.project} deployer={PRODUCTION.deployer} '
            f'runtime={PRODUCTION.runtime_service_account}; got '
            f'project={identity.project} deployer={identity.deployer} '
            f'runtime={identity.runtime_service_account}.'
        )
    return identity


def check_current_account(identity: ProductionIdentity, *, runner: GcloudRunner | None = None) -> None:
    result = _run_gcloud(['config', 'get-value', 'account'], runner=runner)
    account = (result.stdout or '').strip()
    if result.returncode != 0 or not account:
        _fail('could not resolve the authenticated gcloud account before attaching the reconciler job identity.')
    if account != identity.deployer:
        _fail(
            f'authenticated gcloud account {account!r} is not the pinned production deployer '
            f'{identity.deployer}; GCP_CREDENTIALS must be that service account.'
        )


def check_runtime_service_account_exists(identity: ProductionIdentity, *, runner: GcloudRunner | None = None) -> None:
    result = _run_gcloud(
        [
            'iam',
            'service-accounts',
            'describe',
            identity.runtime_service_account,
            f'--project={identity.project}',
        ],
        runner=runner,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or '').strip() or f'exit {result.returncode}'
        _fail(
            f'runtime identity {identity.runtime_service_account} is absent in {identity.project} ({detail}). '
            'Create it and grant the deployer roles/iam.serviceAccountUser before routing production traffic.'
        )


def check_deployer_can_act_as(identity: ProductionIdentity, *, runner: GcloudRunner | None = None) -> None:
    result = _run_gcloud(
        [
            'iam',
            'service-accounts',
            'get-iam-policy',
            identity.runtime_service_account,
            f'--project={identity.project}',
            '--format=json',
        ],
        runner=runner,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or '').strip() or f'exit {result.returncode}'
        _fail(
            f'could not read IAM policy for {identity.runtime_service_account} ({detail}). '
            f'The deployer {identity.deployer} must have {identity.required_role} '
            '(iam.serviceAccounts.actAs) on that identity.'
        )
    try:
        policy = json.loads(result.stdout or '{}')
    except json.JSONDecodeError as exc:
        _fail(f'IAM policy for {identity.runtime_service_account} was not JSON: {exc}.')
    expected_member = f'serviceAccount:{identity.deployer}'
    for binding in policy.get('bindings') or ():
        if not isinstance(binding, Mapping):
            continue
        if binding.get('role') != identity.required_role:
            continue
        if not _binding_is_unconditional(binding):
            continue
        if expected_member in _members(binding):
            return
    _fail(
        f'{identity.deployer} lacks {identity.required_role} (iam.serviceAccounts.actAs) on '
        f'{identity.runtime_service_account}. Grant that binding on the runtime identity only; '
        'do not grant Service Account User at project scope.'
    )


def preflight(identity: ProductionIdentity, *, runner: GcloudRunner | None = None) -> None:
    check_current_account(identity, runner=runner)
    check_runtime_service_account_exists(identity, runner=runner)
    check_deployer_can_act_as(identity, runner=runner)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        identity = parse_identity_args(argv)
        preflight(identity)
    except PreflightError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    print(f'OK: {PRODUCTION.deployer} can actAs {PRODUCTION.runtime_service_account} ' f'in {PRODUCTION.project}.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
