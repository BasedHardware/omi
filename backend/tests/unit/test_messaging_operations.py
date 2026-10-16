"""Operator tooling is read-only unless explicitly applied; alert/job contracts are executable."""

import copy
import json
from types import SimpleNamespace

import pytest

from scripts import messaging_operations as ops
from utils.messaging import maintenance

IMAGE = 'gcr.io/based-hardware/backend@sha256:' + 'a' * 64
CHANNELS = ['projects/based-hardware/notificationChannels/123']


class Session:
    def __init__(self, existing=()):
        self.policies = list(existing)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if method == 'GET':
            if 'locations/' in url:
                return SimpleNamespace(ok=False, status_code=404)
            if url.endswith('alertPolicies'):
                value = {'alertPolicies': self.policies}
            else:
                value = next(p for p in self.policies if url.endswith(p['name']))
        elif 'locations/' in url:
            value = {'name': 'projects/based-hardware/locations/us-central1/operations/validation'}
        else:
            value = copy.deepcopy(kwargs['json'])
            value.setdefault('name', 'projects/based-hardware/alertPolicies/' + str(len(self.policies) + 1))
            self.policies.append(value)
        return SimpleNamespace(ok=True, status_code=200, json=lambda: value)


def test_read_only_diffs_and_job_validation_never_execute():
    session = Session()
    assert ops.reconcile_job(session, IMAGE, 'check')
    assert all(c[0] == 'GET' for c in session.calls)
    ops.reconcile_job(session, IMAGE, 'validate')
    assert session.calls[-1][2]['params']['validateOnly'] == 'true'
    body = session.calls[-1][2]['json']
    task = body['template']['template']
    assert task['maxRetries'] == 1 and task['timeout'] == '600s'
    assert task['containers'][0]['args'] == ['-m', 'utils.messaging.maintenance']
    assert 'SERVICE_ACCOUNT_JSON' not in json.dumps(body)
    assert ops.reconcile_alerts(session, CHANNELS, 'check')
    assert not any(':run' in c[1] for c in session.calls)


def test_alert_create_is_verified_and_second_run_is_noop():
    session = Session()
    ops.reconcile_alerts(session, CHANNELS, 'apply')
    assert len(session.policies) == 10
    session.calls.clear()
    assert not ops.reconcile_alerts(session, CHANNELS, 'apply')
    assert all(c[0] == 'GET' for c in session.calls)


def test_duplicate_policy_fails_before_any_write():
    body = ops.desired_alerts(CHANNELS)[-1]
    session = Session([body, body])
    with pytest.raises(RuntimeError, match='Duplicate'):
        ops.reconcile_alerts(session, CHANNELS, 'apply')
    assert all(c[0] == 'GET' for c in session.calls)


@pytest.mark.parametrize(
    'image', ['latest', 'gcr.io/based-hardware/backend:main', 'gcr.io/other/backend@sha256:' + 'a' * 64]
)
def test_job_rejects_unpinned_or_foreign_images(image):
    with pytest.raises(ValueError):
        ops.desired_job(image)


def test_maintenance_failure_is_redacted_and_nonzero(monkeypatch, caplog):
    def fail():
        raise PermissionError('private account and provider data')

    monkeypatch.setattr(maintenance, 'run', fail)
    with pytest.raises(SystemExit) as error:
        maintenance.main()
    assert error.value.code == 1
    assert 'outcome=failed reason=permission error_type=PermissionError' in caplog.text
    assert 'private account' not in caplog.text
