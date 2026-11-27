"""Validate the per-rule Soniox alert inverse against captured Grafana state."""

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


def rule(uid, title):
    return {
        'uid': uid,
        'title': title,
        'folderUID': 'folder',
        'ruleGroup': 'group',
        'condition': 'A',
        'data': [],
        'isPaused': False,
        'labels': {'alert_identity': uid},
        'notification_settings': {'receiver': 'Omi - Services Alerting (Telegram)'},
    }


class FakeGrafana:
    def __init__(self, live):
        self.live = copy.deepcopy(live)
        self.writes = []

    def rules(self):
        return copy.deepcopy(self.live)

    def request(self, path, body=None, method='GET', *, editable=False):
        self.writes.append((method, path, body, editable))
        uid = path.rsplit('/', 1)[-1]
        if method == 'PUT':
            self.live[uid] = copy.deepcopy(body)
        elif method == 'DELETE':
            self.live.pop(uid, None)
        else:
            raise AssertionError(f'unexpected method {method}')
        return None


def snapshot_file(path, uid, prior, desired, source_sha='a' * 40, source_run_id='123'):
    payload = {
        'schema_version': 1,
        'source_sha': source_sha,
        'source_run_id': source_run_id,
        'rules': [prior] if prior is not None else [],
        'created_uids': [] if prior is not None else [uid],
        'soniox_alert_rollback': {'uid': uid, 'desired': desired},
    }
    path.write_text(json.dumps(payload))
    return payload


def test_existing_rule_is_restored_and_read_back(restore_tool, tmp_path):
    uid = restore_tool.SONIOX_DAILY_HOURS_UID
    prior = {**rule(uid, 'before'), 'provenance': 'api'}
    desired = {**rule(uid, 'after'), 'provenance': 'api'}
    path = tmp_path / 'backup.json'
    snapshot_file(path, uid, prior, desired)
    snapshot = restore_tool.load_snapshot(path, 'a' * 40, '123')
    api = FakeGrafana({uid: desired})

    message = restore_tool.restore_soniox_alert(api, snapshot, apply=True)

    assert message.endswith('verified read-back')
    assert [(method, path) for method, path, _, _ in api.writes] == [('PUT', restore_tool.API + '/' + uid)]
    assert restore_tool.comparable(api.live[uid]) == restore_tool.comparable(prior)
    assert api.writes[0][3] is False


def test_created_rule_is_deleted_only_when_it_matches_applied_definition(restore_tool, tmp_path):
    uid = restore_tool.SONIOX_DAILY_HOURS_UID
    desired = rule(uid, 'new Soniox page')
    path = tmp_path / 'backup.json'
    snapshot_file(path, uid, None, desired)
    snapshot = restore_tool.load_snapshot(path, 'a' * 40, '123')
    api = FakeGrafana({uid: desired, 'other-rule': rule('other-rule', 'keep')})

    restore_tool.restore_soniox_alert(api, snapshot, apply=True)

    assert [(method, path) for method, path, _, _ in api.writes] == [('DELETE', restore_tool.API + '/' + uid)]
    assert uid not in api.live
    assert 'other-rule' in api.live


def test_dry_run_and_already_restored_state_do_not_write(restore_tool, tmp_path):
    uid = restore_tool.SONIOX_DAILY_HOURS_UID
    prior = rule(uid, 'before')
    desired = rule(uid, 'after')
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
    prior, desired = rule(uid, 'before'), rule(uid, 'after')
    path = tmp_path / 'backup.json'
    snapshot_file(path, uid, prior, desired)
    snapshot = restore_tool.load_snapshot(path, 'a' * 40, '123')
    api = FakeGrafana({uid: rule(uid, 'concurrent edit')})

    with pytest.raises(ValueError, match='refusing to overwrite'):
        restore_tool.restore_soniox_alert(api, snapshot, apply=True)
    assert api.writes == []


def test_wrong_run_or_sha_and_non_soniox_snapshot_fail_closed(restore_tool, tmp_path):
    uid = restore_tool.SONIOX_DAILY_HOURS_UID
    path = tmp_path / 'backup.json'
    snapshot_file(path, uid, None, rule(uid, 'new'))

    with pytest.raises(ValueError, match='selected source run'):
        restore_tool.load_snapshot(path, 'b' * 40, '123')
    with pytest.raises(ValueError, match='selected source run'):
        restore_tool.load_snapshot(path, 'a' * 40, '124')

    snapshot_file(path, 'other-rule', None, rule('other-rule', 'not Soniox'))
    with pytest.raises(ValueError, match='Soniox alert inverse'):
        restore_tool.load_snapshot(path, 'a' * 40, '123')
