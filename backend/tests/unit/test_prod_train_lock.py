"""B5: reading the prod-train lock from GitHub run and deployment state."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))

import prod_train_lock as lock  # noqa: E402

WORKFLOWS = '/repos/BasedHardware/omi/actions/workflows'


def _run(run_id, workflow, status='in_progress', event='workflow_dispatch', created='2026-10-19T06:00:00Z'):
    return {
        'id': run_id,
        'path': f'.github/workflows/{workflow}',
        'status': status,
        'event': event,
        'created_at': created,
        'html_url': f'https://github.com/BasedHardware/omi/actions/runs/{run_id}',
        'triggering_actor': {'login': 'lead'},
    }


class FakeApi:
    def __init__(self, runs, deployments=None, pending=None, registered=None):
        self.runs = runs
        self.registered = registered
        self.deployments = deployments or {}  # env -> [(id, created_at, run_id)]
        self.pending = pending or {}
        self.calls = []

    def __call__(self, path, params):
        self.calls.append((path, dict(params)))
        if path == WORKFLOWS:
            paths = (
                sorted(lock.PROD_TRAIN_WORKFLOWS | {r['path'] for r in self.runs})
                if self.registered is None
                else self.registered
            )
            return {'total_count': len(paths), 'workflows': [{'id': i, 'path': p} for i, p in enumerate(paths)]}
        if path.startswith(WORKFLOWS + '/') and path.endswith('/runs'):
            paths = (
                sorted(lock.PROD_TRAIN_WORKFLOWS | {r['path'] for r in self.runs})
                if self.registered is None
                else self.registered
            )
            workflow = paths[int(path[len(WORKFLOWS) + 1 :].split('/')[0])]
            matched = [r for r in self.runs if r['status'] == params['status'] and r['path'] == workflow]
            size, page = params['per_page'], params['page']
            return {'total_count': len(matched), 'workflow_runs': matched[(page - 1) * size : page * size]}
        if path == '/repos/BasedHardware/omi/deployments':
            return [{'id': d, 'created_at': c} for d, c, _ in self.deployments.get(params['environment'], [])]
        if path.endswith('/statuses'):
            deployment_id = int(path.split('/')[-2])
            for items in self.deployments.values():
                for d, _, run_id in items:
                    if d == deployment_id:
                        return [
                            {
                                'state': 'in_progress',
                                'log_url': f'https://github.com/BasedHardware/omi/actions/runs/{run_id}/job/1',
                            }
                        ]
            return []
        if path.endswith('/pending_deployments'):
            return [{'environment': {'name': env}} for env in self.pending.get(int(path.split('/')[-2]), [])]
        raise AssertionError(path)


def test_free_when_no_prod_train_workflow_is_active():
    api = FakeApi([_run(1, 'gcp_frontend.yml')])
    assert lock.read_status(api).held is False


def test_prod_backend_train_holds_the_lock():
    api = FakeApi([_run(7, 'gcp_backend.yml')], {'prod': [(70, '2026-10-19T06:01:00Z', 7)]})
    status = lock.read_status(api)
    assert status.held and [(h.run_id, h.environment, h.workflow) for h in status.holders] == [
        (7, 'prod', 'gcp_backend.yml')
    ]


def test_development_dispatch_and_push_runs_never_hold_it():
    api = FakeApi(
        [_run(8, 'gcp_backend.yml'), _run(9, 'gcp_backend_listen_helm.yml', event='push')],
        {'development': [(80, '2026-10-19T06:01:00Z', 8)]},
    )
    assert lock.read_status(api).held is False


def test_unknown_environment_fails_closed():
    """The group is taken at run start, before any environment job records a deployment."""

    api = FakeApi([_run(5, 'gcp_parakeet.yml', status='queued')])
    status = lock.read_status(api)
    assert status.held and status.holders[0].environment == 'unknown'


def test_run_waiting_on_prod_approval_holds_it():
    api = FakeApi([_run(6, 'config_train.yml', status='waiting')], pending={6: ['prod']})
    assert lock.read_status(api).holders[0].environment == 'prod'


def test_old_deployments_are_not_scanned():
    api = FakeApi([_run(7, 'gcp_backend.yml')], {'prod': [(1, '2026-10-18T00:00:00Z', 7)]})
    lock.read_status(api)
    assert not any(path.endswith('/statuses') for path, _ in api.calls)


@pytest.mark.parametrize(
    'api, code',
    [
        (FakeApi([]), lock.EXIT_FREE),
        (FakeApi([_run(5, 'gcp_parakeet.yml')]), lock.EXIT_HELD),
    ],
)
def test_cli_exit_codes(api, code):
    assert lock.main(['status'], api=api) == code


def test_cli_read_failure_is_unknown():
    def broken(path, params):
        raise lock.LockReadError('rate limited')

    assert lock.main(['status'], api=broken) == lock.EXIT_UNKNOWN


def test_lock_workflow_list_matches_the_concurrency_policy():
    policy = (Path(__file__).resolve().parents[3] / '.github/scripts/check-deployment-concurrency.py').read_text()
    for path in lock.PROD_TRAIN_WORKFLOWS:
        assert f'"{path.rsplit("/", 1)[-1]}":' in policy.split('PROD_TRAIN_WRITERS = {', 1)[1].split('}', 1)[0]


def test_an_old_prod_train_behind_a_full_page_still_holds_it():
    """M1 L07-1: a long train must not age off the first page of active runs."""
    newer = [_run(1000 + i, 'gcp_backend.yml', event='push') for i in range(150)]
    old = _run(7, 'gcp_backend.yml', created='2026-10-19T01:00:00Z')
    api = FakeApi(newer + [old], {'prod': [(70, '2026-10-19T01:01:00Z', 7)]})
    status = lock.read_status(api)
    assert status.held and [h.run_id for h in status.holders] == [7]


def test_a_listing_short_of_its_total_count_is_unknown():
    def truncated(path, params):
        if path.endswith('/workflows'):
            return {'total_count': 1, 'workflows': [{'id': 1, 'path': '.github/workflows/gcp_backend.yml'}]}
        if path.endswith('/runs'):
            return {'total_count': 5, 'workflow_runs': []}
        return []

    assert lock.main(['status'], api=truncated) == lock.EXIT_UNKNOWN


def test_a_prod_train_workflow_github_does_not_list_has_no_runs():
    api = FakeApi([], registered=['.github/workflows/gcp_backend.yml'])
    assert lock.read_status(api).held is False
    assert not any('/workflows/' in path and path.endswith('/runs') and 'config_train' in path for path, _ in api.calls)
