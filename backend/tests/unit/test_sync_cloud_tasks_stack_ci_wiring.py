"""Static wiring contract for the blocking Sync Cloud Tasks stack gauntlet.

Behavior is proved by the emulator stack itself.  This test prevents its
package script, high-risk workflow contract, or blocking CI job from silently
disconnecting.
"""

from __future__ import annotations

import json
from pathlib import Path

from google.cloud import tasks_v2
from google.protobuf import duration_pb2
from testing.sync_cloud_tasks_stack.cloud_tasks import CloudTasksRecorder
from utils.cloud_tasks import DISPATCH_DEADLINE_SECONDS, SYNC_JOB_TASK_PAYLOAD_KEYS

_REPO_ROOT = Path(__file__).resolve().parents[3]

# Keep in lockstep with test_listen_pusher_stack_ci_wiring._BOUNDED_APT_GET:
# unbounded apt-get is the hang that previously burned this job's timeout.
_BOUNDED_APT_GET = 'sudo apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=10 -o Acquire::https::Timeout=10'


def test_sync_cloud_tasks_stack_gauntlet_has_a_deterministic_hermetic_ci_job() -> None:
    workflow = (_REPO_ROOT / '.github' / 'workflows' / 'backend-hermetic-e2e.yml').read_text(encoding='utf-8')
    package = json.loads((_REPO_ROOT / 'package.json').read_text(encoding='utf-8'))
    contracts = json.loads((_REPO_ROOT / 'backend' / 'testing' / 'workflow_contracts.json').read_text(encoding='utf-8'))

    assert '  sync-cloud-tasks-stack-gauntlet:' in workflow
    job = workflow.split('  sync-cloud-tasks-stack-gauntlet:\n', 1)[1].split(
        '\n  replay-harness-phase0a-gauntlet:\n', 1
    )[0]

    assert 'timeout-minutes: 20' in job
    assert 'needs: scope' in job
    assert "if: needs.scope.outputs.applies == 'true'" in job
    assert 'uses: actions/setup-python@v6' in job
    assert 'uses: astral-sh/setup-uv@ecd24dd710f2fb0dca1693a67af11fc4a5c5ec84' in job
    assert 'uv venv .venv' in job
    assert 'uv pip sync pylock.toml --python .venv/bin/python' in job
    assert 'uses: actions/setup-node@v7' in job
    assert "node-version: '22'" in job
    assert 'cache-dependency-path: package-lock.json' in job
    assert 'npm ci --ignore-scripts' in job
    assert 'uses: actions/setup-java@v5' in job
    assert "java-version: '21'" in job
    assert f'{_BOUNDED_APT_GET} update' in job
    assert f'{_BOUNDED_APT_GET} install --yes redis-server' in job
    assert 'timeout-minutes: 5' in job
    assert 'npm run test:sync-cloud-tasks-stack:emulator' in job

    assert package['scripts']['test:sync-cloud-tasks-stack:emulator'] == 'backend/testing/sync_cloud_tasks_stack/run.sh'
    run_script = (_REPO_ROOT / 'backend' / 'testing' / 'sync_cloud_tasks_stack' / 'run.sh').read_text(encoding='utf-8')
    assert 'websocketPort' in run_script
    sync_contract = next(contract for contract in contracts['workflows'] if contract['id'] == 'sync_cloud_tasks')
    assert 'backend/testing/sync_cloud_tasks_stack/**' in sync_contract['sources']
    assert 'tests/unit/test_sync_cloud_tasks_stack_ci_wiring.py' in sync_contract['tests']


def test_gauntlet_recorder_shares_the_production_task_payload_schema(monkeypatch, tmp_path) -> None:
    """The recorder must accept every durable field admission can enqueue."""
    handler_url = 'http://127.0.0.1:39123/v2/sync-jobs/run'
    monkeypatch.setenv('SYNC_TASKS_PROJECT', 'test-project')
    monkeypatch.setenv('SYNC_TASKS_LOCATION', 'us-central1')
    monkeypatch.setenv('SYNC_TASKS_QUEUE', 'sync-jobs')
    monkeypatch.setenv('SYNC_TASKS_HANDLER_URL', handler_url)
    monkeypatch.setenv('SYNC_TASKS_OIDC_AUDIENCE', handler_url)
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'invoker@test-project.iam.gserviceaccount.com')
    monkeypatch.setenv('OMI_SYNC_STACK_STATE_DIR', str(tmp_path))

    payload = {key: None for key in SYNC_JOB_TASK_PAYLOAD_KEYS}
    payload.update(
        {
            'schema_version': 1,
            'job_id': 'job-1',
            'raw_blob_paths': ['gs://sync/job-1.opus'],
        }
    )
    recorder = CloudTasksRecorder()
    task = tasks_v2.Task(
        name=recorder.task_path('test-project', 'us-central1', 'sync-jobs', 'job-1'),
        http_request=tasks_v2.HttpRequest(
            http_method=tasks_v2.HttpMethod.POST,
            url=handler_url,
            headers={'Content-Type': 'application/json'},
            body=json.dumps(payload).encode('utf-8'),
            oidc_token=tasks_v2.OidcToken(
                service_account_email='invoker@test-project.iam.gserviceaccount.com',
                audience=handler_url,
            ),
        ),
        dispatch_deadline=duration_pb2.Duration(seconds=DISPATCH_DEADLINE_SECONDS),
    )

    assert (
        recorder.create_task(parent=recorder.queue_path('test-project', 'us-central1', 'sync-jobs'), task=task) is task
    )
    assert recorder._tasks['job-1'].body == payload
