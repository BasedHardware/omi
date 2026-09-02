import importlib.util
import json
from pathlib import Path
import subprocess
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
import yaml

BACKEND_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = BACKEND_DIR.parent


def _load_provisioner() -> ModuleType:
    path = BACKEND_DIR / 'scripts' / 'provision_notifications_scheduler.py'
    spec = importlib.util.spec_from_file_location('provision_notifications_scheduler_test_target', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def scheduler() -> ModuleType:
    return _load_provisioner()


def _state(scheduler: ModuleType, *, schedule: str = '0 * * * *', state: str = 'ENABLED') -> dict[str, Any]:
    return {
        'schedule': schedule,
        'timeZone': 'Etc/UTC',
        'state': state,
        'httpTarget': {
            'httpMethod': 'POST',
            'uri': scheduler.scheduler_target_uri('omi-project', 'us-central1', 'notifications-job'),
            'oauthToken': {'serviceAccountEmail': 'scheduler@omi-project.iam.gserviceaccount.com'},
        },
    }


class _Runner:
    def __init__(self, scheduler: ModuleType, *, existing: bool = True, describe_error: str | None = None):
        self.scheduler = scheduler
        self.existing = existing
        self.describe_error = describe_error
        self.calls: list[list[str]] = []
        self.describe_calls = 0

    def __call__(self, args: list[str], **_kwargs: Any) -> SimpleNamespace:
        self.calls.append(args)
        if args[1:4] == ['scheduler', 'jobs', 'describe']:
            self.describe_calls += 1
            if self.describe_calls == 1 and self.describe_error is not None:
                return SimpleNamespace(returncode=1, stdout='', stderr=self.describe_error)
            if self.describe_calls == 1 and not self.existing:
                return SimpleNamespace(returncode=1, stdout='', stderr='NOT_FOUND: scheduler job')
            return SimpleNamespace(returncode=0, stdout=json.dumps(_state(self.scheduler)), stderr='')
        return SimpleNamespace(returncode=0, stdout='', stderr='')


def _ensure(scheduler: ModuleType, runner: _Runner) -> str:
    return scheduler.ensure_scheduler(
        project='omi-project',
        region='us-central1',
        service_account='scheduler@omi-project.iam.gserviceaccount.com',
        runner=runner,
    )


def test_existing_scheduler_is_updated_to_exact_hourly_contract_and_resumed(scheduler: ModuleType) -> None:
    runner = _Runner(scheduler)

    assert _ensure(scheduler, runner) == 'update'

    update = next(call for call in runner.calls if call[1:5] == ['scheduler', 'jobs', 'update', 'http'])
    assert '--schedule=0 * * * *' in update
    assert '--time-zone=Etc/UTC' in update
    assert '--http-method=POST' in update
    assert any(call[1:4] == ['scheduler', 'jobs', 'resume'] for call in runner.calls)
    assert not any('--schedule=*/1 * * * *' in call for call in runner.calls)


def test_missing_scheduler_is_created_without_resume(scheduler: ModuleType) -> None:
    runner = _Runner(scheduler, existing=False)

    assert _ensure(scheduler, runner) == 'create'

    assert any(call[1:5] == ['scheduler', 'jobs', 'create', 'http'] for call in runner.calls)
    assert not any(call[1:4] == ['scheduler', 'jobs', 'resume'] for call in runner.calls)


def test_describe_permission_failure_is_not_misclassified_as_missing(scheduler: ModuleType) -> None:
    runner = _Runner(scheduler, describe_error='PERMISSION_DENIED: forbidden')

    with pytest.raises(subprocess.CalledProcessError):
        _ensure(scheduler, runner)

    assert len(runner.calls) == 1


def test_scheduler_identity_and_final_state_fail_closed(scheduler: ModuleType) -> None:
    with pytest.raises(ValueError, match='identity'):
        scheduler.scheduler_http_args(
            'update',
            project='omi-project',
            region='us-central1',
            scheduler_job='other-job',
            cloud_run_job='notifications-job',
            service_account='scheduler@omi-project.iam.gserviceaccount.com',
        )

    with pytest.raises(ValueError, match='schedule'):
        scheduler.validate_scheduler_state(
            _state(scheduler, schedule='*/1 * * * *'),
            project='omi-project',
            region='us-central1',
            service_account='scheduler@omi-project.iam.gserviceaccount.com',
        )


def test_workflow_owns_scheduler_and_bounded_job_runtime_contract() -> None:
    workflow = (ROOT_DIR / '.github' / 'workflows' / 'gcp_notifications_job.yml').read_text(encoding='utf-8')
    manifest = yaml.safe_load((BACKEND_DIR / 'deploy' / 'runtime_env' / '_base.yaml').read_text(encoding='utf-8'))
    flags = manifest['environment_shared']['cloud_run']['jobs']['notifications-job']['flags']

    assert 'release_sha:' in workflow
    assert '\n      branch:' not in workflow
    assert 'release_sha must equal the current origin/main SHA' in workflow
    assert 'roles/run.invoker' in workflow
    assert 'provision_notifications_scheduler.py' in workflow
    assert '${{ steps.runtime-env.outputs.notifications_job_flags }}' in workflow
    assert flags == {
        '--task-timeout': '3600s',
        '--max-retries': '0',
        '--tasks': '1',
        '--parallelism': '1',
    }
