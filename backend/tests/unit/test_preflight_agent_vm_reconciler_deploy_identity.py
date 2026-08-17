from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent
SCRIPT = BACKEND_DIR / 'scripts' / 'preflight_agent_vm_reconciler_deploy_identity.py'


def load_preflight():
    spec = importlib.util.spec_from_file_location('preflight_agent_vm_reconciler_deploy_identity', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _policy(*, members: list[str] | None = None, role: str | None = None, condition=None) -> str:
    preflight = load_preflight()
    binding = {
        'role': role or preflight.REQUIRED_ROLE,
        'members': members or [f'serviceAccount:{preflight.PROD_DEPLOYER}'],
    }
    if condition is not None:
        binding['condition'] = condition
    return json.dumps({'bindings': [binding]})


class FakeGcloud:
    def __init__(
        self,
        *,
        account: str | None = None,
        describe_code: int = 0,
        policy: str | None = None,
        policy_code: int = 0,
    ) -> None:
        preflight = load_preflight()
        self.account = account if account is not None else preflight.PROD_DEPLOYER
        self.describe_code = describe_code
        self.policy = policy if policy is not None else _policy()
        self.policy_code = policy_code
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str]) -> SimpleNamespace:
        self.commands.append(command)
        if command[1:3] == ['config', 'get-value']:
            return SimpleNamespace(returncode=0, stdout=f'{self.account}\n', stderr='')
        if command[1:4] == ['iam', 'service-accounts', 'describe']:
            return SimpleNamespace(
                returncode=self.describe_code, stdout='', stderr='NOT_FOUND' if self.describe_code else ''
            )
        if command[1:4] == ['iam', 'service-accounts', 'get-iam-policy']:
            return SimpleNamespace(
                returncode=self.policy_code, stdout=self.policy, stderr='DENIED' if self.policy_code else ''
            )
        raise AssertionError(f'unexpected gcloud command: {command}')


def test_production_pins_are_the_exact_rollback_identities():
    preflight = load_preflight()

    assert preflight.PROD_PROJECT == 'based-hardware'
    assert preflight.PROD_DEPLOYER == 'josancamon-mb-pro-2@based-hardware.iam.gserviceaccount.com'
    assert preflight.PROD_RUNTIME_SERVICE_ACCOUNT == 'agent-vm-reconciler@based-hardware.iam.gserviceaccount.com'
    assert preflight.REQUIRED_ROLE == 'roles/iam.serviceAccountUser'
    assert '32012710785' in preflight.INCIDENT
    assert 'iam.serviceAccounts.actAs' in preflight.INCIDENT


def test_parse_identity_args_rejects_any_drift_from_the_production_pin():
    preflight = load_preflight()

    assert preflight.parse_identity_args(['--project', preflight.PROD_PROJECT]) == preflight.PRODUCTION
    with pytest.raises(preflight.PreflightError, match='32012710785'):
        preflight.parse_identity_args(['--project', 'based-hardware-dev'])
    with pytest.raises(preflight.PreflightError, match=preflight.PROD_DEPLOYER):
        preflight.parse_identity_args(
            ['--project', preflight.PROD_PROJECT, '--deployer', 'other@based-hardware.iam.gserviceaccount.com']
        )


def test_preflight_passes_when_the_pinned_deployer_can_act_as_the_runtime_identity():
    preflight = load_preflight()
    runner = FakeGcloud()

    preflight.preflight(preflight.PRODUCTION, runner=runner)
    assert any(command[1:4] == ['iam', 'service-accounts', 'describe'] for command in runner.commands)
    assert any(command[1:4] == ['iam', 'service-accounts', 'get-iam-policy'] for command in runner.commands)


def test_missing_runtime_service_account_fails_closed_before_any_success():
    preflight = load_preflight()
    runner = FakeGcloud(describe_code=1)

    with pytest.raises(preflight.PreflightError, match='runtime identity .* is absent'):
        preflight.preflight(preflight.PRODUCTION, runner=runner)
    assert not any(command[1:4] == ['iam', 'service-accounts', 'get-iam-policy'] for command in runner.commands)


def test_missing_act_as_binding_fails_closed():
    preflight = load_preflight()
    runner = FakeGcloud(policy=_policy(members=['serviceAccount:other@based-hardware.iam.gserviceaccount.com']))

    with pytest.raises(preflight.PreflightError, match='lacks roles/iam.serviceAccountUser'):
        preflight.preflight(preflight.PRODUCTION, runner=runner)


def test_conditional_act_as_binding_does_not_satisfy_the_job_attach_prerequisite():
    preflight = load_preflight()
    runner = FakeGcloud(policy=_policy(condition={'title': 'not for Cloud Run Job attach'}))

    with pytest.raises(preflight.PreflightError, match='lacks roles/iam.serviceAccountUser'):
        preflight.preflight(preflight.PRODUCTION, runner=runner)


def test_wrong_authenticated_account_fails_closed():
    preflight = load_preflight()
    runner = FakeGcloud(account='someone-else@based-hardware.iam.gserviceaccount.com')

    with pytest.raises(preflight.PreflightError, match='authenticated gcloud account'):
        preflight.preflight(preflight.PRODUCTION, runner=runner)


def test_production_workflow_stages_and_runs_the_preflight_before_routing_traffic():
    preflight = load_preflight()
    workflow = (REPO_DIR / '.github/workflows/desktop_backend_prod.yml').read_text(encoding='utf-8')

    stage = 'cp .workflow-source/backend/scripts/preflight_agent_vm_reconciler_deploy_identity.py "$controls/backend/scripts/"'
    invoke = 'python3 "$DESKTOP_BACKEND_CONTROLS/backend/scripts/preflight_agent_vm_reconciler_deploy_identity.py"'
    assert stage in workflow
    assert invoke in workflow
    assert f'--deployer={preflight.PROD_DEPLOYER}' in workflow
    assert f'--runtime-service-account={preflight.PROD_RUNTIME_SERVICE_ACCOUNT}' in workflow
    assert '--service-account=agent-vm-reconciler@${{ vars.GCP_PROJECT_ID }}.iam.gserviceaccount.com' in workflow
    assert workflow.index('Preflight Agent VM reconciler deploy identity') < workflow.index(
        'Route traffic to accepted production revision'
    )
    assert workflow.index(stage) < workflow.index('rm -rf .workflow-source')
