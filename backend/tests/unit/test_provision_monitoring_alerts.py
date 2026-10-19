"""Exercise alert reconciliation, drift detection, and pre-write backups."""

import copy
import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/provision_monitoring_alerts.py'


@pytest.fixture(scope='module')
def provisioner():
    return SimpleNamespace(**runpy.run_path(str(SCRIPT)))


def rule(uid='example'):
    return {
        'uid': uid,
        'folderUID': 'folder',
        'ruleGroup': 'group',
        'title': uid,
        'condition': 'A',
        'data': [],
        'isPaused': False,
        'labels': {'alert_identity': uid},
        'notification_settings': {'receiver': 'Omi - Services Alerting (Telegram)'},
    }


class FakeGrafana:
    def __init__(self, rules):
        self.live = copy.deepcopy(rules)
        self.writes = []
        self.ignore_writes = False
        self.contacts = [{'name': 'Omi - Services Alerting (Telegram)', 'type': 'telegram'}]

    def rules(self):
        return copy.deepcopy(self.live)

    def request(self, path, body=None, method='GET', *, editable=False):
        if path.endswith('contact-points'):
            return self.contacts
        if method == 'GET':
            assert path == '/api/folders/folder'
            return {'uid': 'folder'}
        self.writes.append((method, path, body, editable))
        if not self.ignore_writes:
            self.live[body['uid']] = copy.deepcopy(body)
        return body


def test_read_only_check_detects_paused_and_timing_drift_without_writes(provisioner):
    expected = rule()
    actual = {**expected, 'isPaused': True, 'notification_settings': {'receiver': 'other'}}
    api = FakeGrafana({'example': actual, 'unmanaged': rule('unmanaged')})
    differences = provisioner.reconcile(api, {'example': expected})
    assert 'isPaused,notification_settings' in differences[0]
    assert differences[1] == 'unmanaged: live but uncommitted (retained)'
    assert api.writes == []


def test_apply_backs_up_before_writes_and_strips_runtime_fields(provisioner, tmp_path):
    desired = {'example': {**rule(), 'id': 19, 'updated': 'old'}, 'new': rule('new')}
    old = {**rule(), 'title': 'old'}
    api = FakeGrafana({'example': old})
    backup = tmp_path / 'backup.json'
    assert provisioner.reconcile(api, desired, backup=backup) == []
    assert json.loads(backup.read_text()) == {'rules': [old], 'created_uids': ['new']}
    assert backup.stat().st_mode & 0o777 == 0o600
    assert [write[0] for write in api.writes] == ['PUT', 'POST']
    assert all('id' not in write[2] and 'updated' not in write[2] for write in api.writes)


def test_noop_does_not_write_and_preserves_extra_live_rules(provisioner, tmp_path):
    api = FakeGrafana({'example': rule(), 'extra': rule('extra')})
    assert provisioner.reconcile(api, {'example': rule()}, backup=tmp_path / 'backup') == [
        'extra: live but uncommitted (retained)'
    ]
    assert api.writes == []


def test_failed_readback_is_not_reported_as_applied(provisioner, tmp_path):
    api = FakeGrafana({})
    api.ignore_writes = True
    assert provisioner.reconcile(api, {'example': rule()}, backup=tmp_path / 'backup') == ['example: absent']


def test_existing_ui_and_api_group_provenance_is_preserved(provisioner, tmp_path):
    for provenance, editable in [('', True), ('api', False)]:
        old = {**rule(), 'title': 'old', 'provenance': provenance}
        api = FakeGrafana({'example': old})
        assert (
            provisioner.reconcile(api, {'example': rule(), 'new': rule('new')}, backup=tmp_path / str(editable)) == []
        )
        assert all(write[3] is editable for write in api.writes)


def test_file_provisioner_is_not_taken_over_partway(provisioner, tmp_path):
    old = {**rule(), 'title': 'old', 'provenance': 'file'}
    api = FakeGrafana({'example': old})
    with pytest.raises(ValueError, match='another provisioner'):
        provisioner.reconcile(api, {'example': rule()}, backup=tmp_path / 'backup')
    assert api.writes == []
    assert not (tmp_path / 'backup').exists()


def test_existing_backup_prevents_any_writes(provisioner, tmp_path):
    backup = tmp_path / 'backup'
    backup.write_text('retain me')
    api = FakeGrafana({})
    with pytest.raises(FileExistsError):
        provisioner.reconcile(api, {'example': rule()}, backup=backup)
    assert api.writes == []
    assert backup.read_text() == 'retain me'


def test_missing_receiver_fails_before_backup_or_mutation(provisioner, tmp_path):
    api = FakeGrafana({})
    api.contacts = []
    backup = tmp_path / 'backup'
    with pytest.raises(ValueError, match='Telegram'):
        provisioner.reconcile(api, {'example': rule()}, backup=backup)
    assert not backup.exists()
    assert api.writes == []


def test_split_mismatch_duplicate_and_prod_only_fail_closed(provisioner, tmp_path):
    path = tmp_path / 'alert-rules.json'
    (tmp_path / 'alerts').mkdir()
    path.write_text(json.dumps([rule()]))
    (tmp_path / 'alerts/example.json').write_text(json.dumps([{**rule(), 'isPaused': True}]))
    with pytest.raises(ValueError, match='differ'):
        provisioner.load_rules(path)
    with pytest.raises(ValueError, match='duplicate'):
        provisioner.index_rules([rule(), rule()])
    with pytest.raises(ValueError, match='production-specific'):
        provisioner.Grafana('https://monitor.omiapi.com', 'never-log')


def test_actual_source_exports_match(provisioner):
    assert provisioner.load_rules(provisioner.RULES)


@pytest.mark.parametrize(
    'sample,expected_fail', [(1, False), (0, True), (float('nan'), True), (True, True), ('error', True)]
)
def test_query_probe_reads_finite_sentinel_without_provisioning(provisioner, sample, expected_fail, capsys):
    canary = {
        **rule('omi-datasource-test'),
        'data': [
            {'refId': 'A', 'relativeTimeRange': {'from': 600, 'to': 0}, 'model': {'refId': 'A'}},
            {'model': {'conditions': [{'evaluator': {'type': 'lt', 'params': [1]}}]}},
        ],
    }
    calls = []

    class QueryOnly:
        def request(self, path, body, method):
            calls.append((path, method))
            return {
                'results': {
                    'A': {'frames': [{'schema': {'fields': [{'type': 'number'}]}, 'data': {'values': [[sample]]}}]}
                }
            }

    assert bool(provisioner.probe_datasources(QueryOnly(), {canary['uid']: canary})) is expected_fail
    assert calls == [('/api/ds/query', 'POST')]
    assert 'error' not in capsys.readouterr().out


def test_query_probe_rejects_successful_empty_response(provisioner):
    canary = {
        **rule('omi-datasource-test'),
        'data': [
            {'refId': 'A', 'relativeTimeRange': {'from': 600, 'to': 0}, 'model': {'refId': 'A'}},
            {'model': {'conditions': [{'evaluator': {'type': 'lt', 'params': [0]}}]}},
        ],
    }

    class QueryOnly:
        def request(self, *args):
            return {'results': {'A': {'frames': []}}}

    assert provisioner.probe_datasources(QueryOnly(), {canary['uid']: canary})


def protected_rules(provisioner):
    source = provisioner.load_rules(provisioner.RULES)
    canaries = {
        uid: {**copy.deepcopy(source[uid]), 'folderUID': 'folder', 'ruleGroup': 'canaries'}
        for uid in provisioner.CANARY_UIDS
    }
    return {'aaa-business': {**rule('aaa-business'), 'execErrState': 'KeepLast'}, **canaries}


class CanaryGrafana(FakeGrafana):
    def __init__(self, *, drop_canary=False, probe_sample=1):
        super().__init__({})
        self.drop_canary, self.probe_sample = drop_canary, probe_sample
        self.events = []

    def request(self, path, body=None, method='GET', *, editable=False):
        if path == '/api/ds/query':
            self.events.append('probe')
            return {
                'results': {
                    'A': {
                        'frames': [
                            {'schema': {'fields': [{'type': 'number'}]}, 'data': {'values': [[self.probe_sample]]}}
                        ]
                    }
                }
            }
        if method in ('POST', 'PUT'):
            self.events.append(body['uid'])
            if self.drop_canary and body['uid'].startswith('omi-datasource-'):
                self.writes.append((method, path, body, editable))
                return body
        return super().request(path, body, method, editable=editable)


def test_apply_verifies_healthy_canaries_before_keep_last_business_writes(provisioner, tmp_path):
    api = CanaryGrafana()
    desired = protected_rules(provisioner)
    assert provisioner.reconcile(api, desired, backup=tmp_path / 'backup') == []
    assert set(api.events[:3]) == set(provisioner.CANARY_UIDS)
    assert api.events[3:6] == ['probe'] * 3
    assert api.events[6:] == ['aaa-business']


@pytest.mark.parametrize('drop_canary,probe_sample', [(True, 1), (False, -1), (False, float('nan'))])
def test_failed_canary_readback_or_query_blocks_business_updates(provisioner, tmp_path, drop_canary, probe_sample):
    api = CanaryGrafana(drop_canary=drop_canary, probe_sample=probe_sample)
    assert provisioner.reconcile(api, protected_rules(provisioner), backup=tmp_path / 'backup')
    assert 'aaa-business' not in api.events
    assert (tmp_path / 'backup').exists()


def test_keep_last_without_all_active_paging_canaries_fails_before_backup(provisioner, tmp_path):
    desired = protected_rules(provisioner)
    desired.pop(provisioner.CANARY_UIDS[0])
    api = CanaryGrafana()
    with pytest.raises(ValueError, match='every committed datasource canary'):
        provisioner.reconcile(api, desired, backup=tmp_path / 'backup')
    desired = protected_rules(provisioner)
    desired[provisioner.CANARY_UIDS[0]]['isPaused'] = True
    with pytest.raises(ValueError, match='must be active'):
        provisioner.reconcile(api, desired, backup=tmp_path / 'backup')
    assert not (tmp_path / 'backup').exists()
    assert api.events == []


@pytest.mark.parametrize(
    'field,value', [('record', {'metric': 'changed', 'from': 'A'}), ('missingSeriesEvalsToResolve', 99)]
)
def test_semantic_rule_fields_are_detected_in_drift_and_post_write_readback(provisioner, tmp_path, field, value):
    desired = {'example': {**rule(), 'record': None}}
    api = FakeGrafana({'example': {**rule(), field: value}})
    assert field in provisioner.reconcile(api, desired)[0]

    class RetainsSemanticDrift(FakeGrafana):
        def request(self, path, body=None, method='GET', *, editable=False):
            result = super().request(path, body, method, editable=editable)
            if method in ('POST', 'PUT'):
                self.live[body['uid']][field] = value
            return result

    stale = RetainsSemanticDrift({})
    assert field in provisioner.reconcile(stale, desired, backup=tmp_path / 'backup')[0]


def test_nullable_semantic_defaults_do_not_create_spurious_writes(provisioner, tmp_path):
    desired = {'example': {**rule(), 'record': None, 'missingSeriesEvalsToResolve': None}}
    api = FakeGrafana({'example': rule()})
    assert provisioner.reconcile(api, desired, backup=tmp_path / 'backup') == []
    assert api.writes == []


def test_grafana13_readback_defaults_are_not_drift(provisioner):
    desired = {
        'uid': 'r',
        'data': [{'refId': 'B', 'model': {'type': 'reduce'}}],
        'notification_settings': {'receiver': 'x', 'repeat_interval': '24h', 'group_wait': '90s'},
    }
    live = {
        'uid': 'r',
        'data': [
            {'refId': 'B', 'queryType': '', 'model': {'type': 'reduce', 'intervalMs': 1000, 'maxDataPoints': 43200}}
        ],
        'notification_settings': {'receiver': 'x', 'repeat_interval': '1d', 'group_wait': '1m30s'},
    }
    assert provisioner.comparable(desired) == provisioner.comparable(live)
    assert 'queryType' not in desired['data'][0]
    # The write payload keeps the committed strings; only comparison normalizes.
    assert provisioner.definition(desired)['notification_settings']['repeat_interval'] == '24h'


def test_readback_still_reports_semantic_changes(provisioner):
    base = {'uid': 'r', 'execErrState': 'KeepLast', 'data': [{'refId': 'A', 'model': {'intervalMs': 30000}}]}
    assert provisioner.comparable(base) != provisioner.comparable(dict(base, execErrState='Error'))
    other = {'uid': 'r', 'execErrState': 'KeepLast', 'data': [{'refId': 'A', 'model': {'intervalMs': 1000}}]}
    assert provisioner.comparable(base) != provisioner.comparable(other)
    assert provisioner.duration_seconds('24h') == provisioner.duration_seconds('1d') == 86400
    assert provisioner.duration_seconds('5ms') == 0.005
