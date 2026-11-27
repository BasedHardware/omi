"""Validate the per-rule Soniox inverse with Grafana resource-version CAS."""

import copy
import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/restore_soniox_alert.py'


@pytest.fixture(scope='module')
def restore_tool():
    return SimpleNamespace(**runpy.run_path(str(SCRIPT)))


def resource(uid, title, version='1'):
    return {
        'apiVersion': 'rules.alerting.grafana.app/v1beta1',
        'kind': 'AlertRule',
        'metadata': {
            'name': uid,
            'resourceVersion': version,
            'annotations': {'grafana.app/folder': 'folder', 'grafana.com/provenance': 'api'},
        },
        'spec': {'title': title, 'trigger': {'interval': '1m'}, 'expressions': {}},
    }


class FakeGrafana:
    def __init__(self, resources):
        self.app_resources = copy.deepcopy(resources)
        self.writes = []
        self.before_write = None
        self.after_write = None

    def app_alert_rule(self, uid):
        return copy.deepcopy(self.app_resources.get(uid))

    def request(self, path, body=None, method='GET', *, editable=False):
        uid = path.rsplit('/', 1)[-1]
        self.writes.append((method, path, copy.deepcopy(body), editable))
        if self.before_write is not None:
            callback, self.before_write = self.before_write, None
            callback()
        live = self.app_resources.get(uid)
        if method == 'PUT':
            expected = body['metadata']['resourceVersion']
            if live is None or live['metadata']['resourceVersion'] != expected:
                raise ValueError('Grafana PUT: HTTP 409')
            updated = copy.deepcopy(body)
            updated['metadata']['resourceVersion'] = str(int(expected) + 1)
            self.app_resources[uid] = updated
        elif method == 'DELETE':
            expected = body['preconditions']['resourceVersion']
            if live is None or live['metadata']['resourceVersion'] != expected:
                raise ValueError('Grafana DELETE: HTTP 409')
            self.app_resources.pop(uid)
        else:
            raise AssertionError(f'unexpected method {method}')
        if self.after_write is not None:
            callback, self.after_write = self.after_write, None
            callback()
        return None


def snapshot_file(path, uid, prior, desired, source_sha='a' * 40, source_run_id='123'):
    payload = {
        'schema_version': 2,
        'source_sha': source_sha,
        'source_run_id': source_run_id,
        'rules': [],
        'created_uids': [] if prior is not None else [uid],
        'soniox_alert_rollback': {
            'uid': uid,
            'desired': {'uid': uid},
            'previous_resource': prior,
            'desired_resource': desired,
        },
    }
    path.write_text(json.dumps(payload))
    return payload


def test_existing_rule_is_restored_with_current_resource_version(restore_tool, tmp_path):
    uid = restore_tool.SONIOX_DAILY_HOURS_UID
    prior = resource(uid, 'before', '4')
    desired = resource(uid, 'after', '5')
    path = tmp_path / 'backup.json'
    snapshot_file(path, uid, prior, desired)
    snapshot = restore_tool.load_snapshot(path, 'a' * 40, '123')
    api = FakeGrafana({uid: resource(uid, 'after', '9')})

    message = restore_tool.restore_soniox_alert(api, snapshot, apply=True)

    assert message.endswith('verified read-back')
    assert [(method, path) for method, path, _, _ in api.writes] == [
        ('PUT', restore_tool.APP_ALERT_RULES_API + '/' + uid)
    ]
    assert api.writes[0][2]['metadata']['resourceVersion'] == '9'
    assert restore_tool._app_rule_semantics(api.app_resources[uid]) == restore_tool._app_rule_semantics(prior)


def test_created_rule_is_deleted_with_resource_version_precondition(restore_tool, tmp_path):
    uid = restore_tool.SONIOX_DAILY_HOURS_UID
    desired = resource(uid, 'new Soniox page', '2')
    path = tmp_path / 'backup.json'
    snapshot_file(path, uid, None, desired)
    snapshot = restore_tool.load_snapshot(path, 'a' * 40, '123')
    api = FakeGrafana({uid: resource(uid, 'new Soniox page', '8'), 'other-rule': resource('other-rule', 'keep')})

    restore_tool.restore_soniox_alert(api, snapshot, apply=True)

    assert [(method, path) for method, path, _, _ in api.writes] == [
        ('DELETE', restore_tool.APP_ALERT_RULES_API + '/' + uid)
    ]
    assert api.writes[0][2] == {'preconditions': {'resourceVersion': '8'}}
    assert uid not in api.app_resources
    assert 'other-rule' in api.app_resources


def test_dry_run_and_already_restored_state_do_not_write(restore_tool, tmp_path):
    uid = restore_tool.SONIOX_DAILY_HOURS_UID
    prior = resource(uid, 'before')
    desired = resource(uid, 'after')
    path = tmp_path / 'backup.json'
    snapshot_file(path, uid, prior, desired)
    snapshot = restore_tool.load_snapshot(path, 'a' * 40, '123')

    api = FakeGrafana({uid: desired})
    assert restore_tool.restore_soniox_alert(api, snapshot, apply=False) == f'Would restore only {uid}'
    assert api.writes == []

    api = FakeGrafana({uid: prior})
    assert restore_tool.restore_soniox_alert(api, snapshot, apply=True).startswith('Soniox alert already')
    assert api.writes == []


def test_diverged_rule_refuses_to_overwrite(restore_tool, tmp_path):
    uid = restore_tool.SONIOX_DAILY_HOURS_UID
    prior, desired = resource(uid, 'before'), resource(uid, 'after')
    path = tmp_path / 'backup.json'
    snapshot_file(path, uid, prior, desired)
    snapshot = restore_tool.load_snapshot(path, 'a' * 40, '123')
    api = FakeGrafana({uid: resource(uid, 'concurrent edit')})

    with pytest.raises(ValueError, match='refusing to overwrite'):
        restore_tool.restore_soniox_alert(api, snapshot, apply=True)
    assert api.writes == []


@pytest.mark.parametrize('prior', [True, False])
def test_edit_between_rollback_read_and_write_fails_the_server_precondition(restore_tool, tmp_path, prior):
    uid = restore_tool.SONIOX_DAILY_HOURS_UID
    old = resource(uid, 'before', '1') if prior else None
    desired = resource(uid, 'after', '2')
    path = tmp_path / 'backup.json'
    snapshot_file(path, uid, old, desired)
    snapshot = restore_tool.load_snapshot(path, 'a' * 40, '123')
    api = FakeGrafana({uid: resource(uid, 'after', '7')})

    def concurrent_edit():
        api.app_resources[uid]['spec']['title'] = 'concurrent edit'
        api.app_resources[uid]['metadata']['resourceVersion'] = '8'

    api.before_write = concurrent_edit
    with pytest.raises(ValueError, match='HTTP 409'):
        restore_tool.restore_soniox_alert(api, snapshot, apply=True)
    assert api.app_resources[uid]['spec']['title'] == 'concurrent edit'
    assert api.app_resources[uid]['metadata']['resourceVersion'] == '8'


def test_rollback_fails_if_post_write_readback_differs(restore_tool, tmp_path):
    uid = restore_tool.SONIOX_DAILY_HOURS_UID
    prior, desired = resource(uid, 'before', '1'), resource(uid, 'after', '2')
    path = tmp_path / 'backup.json'
    snapshot_file(path, uid, prior, desired)
    snapshot = restore_tool.load_snapshot(path, 'a' * 40, '123')
    api = FakeGrafana({uid: resource(uid, 'after', '7')})

    def concurrent_post_write_edit():
        api.app_resources[uid]['spec']['title'] = 'edit after rollback write'
        api.app_resources[uid]['metadata']['resourceVersion'] = '9'

    api.after_write = concurrent_post_write_edit
    with pytest.raises(ValueError, match='read-back differs'):
        restore_tool.restore_soniox_alert(api, snapshot, apply=True)
    assert api.app_resources[uid]['spec']['title'] == 'edit after rollback write'


def test_wrong_run_or_sha_and_non_soniox_snapshot_fail_closed(restore_tool, tmp_path):
    uid = restore_tool.SONIOX_DAILY_HOURS_UID
    path = tmp_path / 'backup.json'
    snapshot_file(path, uid, None, resource(uid, 'new'))

    with pytest.raises(ValueError, match='selected source run'):
        restore_tool.load_snapshot(path, 'b' * 40, '123')
    with pytest.raises(ValueError, match='selected source run'):
        restore_tool.load_snapshot(path, 'a' * 40, '124')

    snapshot_file(path, 'other-rule', None, resource('other-rule', 'not Soniox'))
    with pytest.raises(ValueError, match='Soniox alert inverse'):
        restore_tool.load_snapshot(path, 'a' * 40, '123')
