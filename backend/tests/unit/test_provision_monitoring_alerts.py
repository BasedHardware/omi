"""Exercise alert reconciliation, drift detection, and pre-write backups."""

import copy
import json
import runpy
import sys
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


def _source_tree(tmp_path, rules):
    path = tmp_path / 'alert-rules.json'
    (tmp_path / 'alerts').mkdir()
    path.write_text(json.dumps(rules))
    for item in rules:
        (tmp_path / 'alerts' / f"{item['uid']}.json").write_text(json.dumps([item]))
    return path


@pytest.mark.parametrize(
    'window',
    [
        {'from': 0, 'to': 0},
        {'from': 900, 'to': 900},
        {'from': 0, 'to': 900},
        {'from': 900},
        {},
        None,
        {'from': '900', 'to': 0},
        {'from': True, 'to': 0},
    ],
)
def test_datasource_query_with_an_empty_or_invalid_relative_range_fails_before_provisioning(
    provisioner, tmp_path, window
):
    """Grafana rejects these windows with "invalid relative time range" (SCA-2055)."""
    broken = {
        **rule(),
        'data': [
            {'refId': 'A', 'datasourceUid': 'prometheus', 'relativeTimeRange': window},
            {'refId': 'B', 'datasourceUid': '__expr__', 'relativeTimeRange': {'from': 0, 'to': 0}},
        ],
    }
    with pytest.raises(ValueError, match='relative time range'):
        provisioner.load_rules(_source_tree(tmp_path, [broken]))


def test_expression_queries_keep_the_zero_window_and_datasource_queries_accept_a_past_window(provisioner, tmp_path):
    valid = {
        **rule(),
        'data': [
            {'refId': 'A', 'datasourceUid': 'prometheus', 'relativeTimeRange': {'from': 900, 'to': 0}},
            {'refId': 'B', 'datasourceUid': 'gmp-cloud-run', 'relativeTimeRange': {'from': 300, 'to': 0}},
            {'refId': 'C', 'datasourceUid': '__expr__', 'relativeTimeRange': {'from': 0, 'to': 0}},
            {'refId': 'D', 'datasourceUid': '-100', 'relativeTimeRange': {'from': 0, 'to': 0}},
        ],
    }
    assert list(provisioner.load_rules(_source_tree(tmp_path, [valid]))) == ['example']


def test_invalid_window_fails_before_the_provisioner_touches_grafana(provisioner, tmp_path, monkeypatch):
    broken = {
        **rule(),
        'data': [{'refId': 'A', 'datasourceUid': 'prometheus', 'relativeTimeRange': {'from': 0, 'to': 0}}],
    }
    path = _source_tree(tmp_path, [broken])

    def refuse(*_args, **_kwargs):
        raise AssertionError('provisioner reached Grafana')

    monkeypatch.setattr(provisioner, 'Grafana', refuse)
    monkeypatch.setattr(sys, 'argv', ['provision_monitoring_alerts.py', '--rules', str(path), '--lint'])
    assert provisioner.main() == 1


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


def test_regenerate_is_offline_preserves_order_and_rejects_duplicate_sources(provisioner, tmp_path):
    path = tmp_path / 'alert-rules.json'
    sources = tmp_path / 'alerts'
    sources.mkdir()
    path.write_text(json.dumps([rule('b'), rule('removed'), rule('a')]))
    (sources / 'a.json').write_text(json.dumps([rule('a'), rule('new')]))
    (sources / 'b.json').write_text(json.dumps([{**rule('b'), 'title': 'updated'}]))
    provisioner.regenerate_export(path)
    assert list(provisioner.load_rules(path)) == ['b', 'a', 'new']
    first = path.read_bytes()
    provisioner.regenerate_export(path)
    assert path.read_bytes() == first
    (sources / 'duplicate.json').write_text(json.dumps([rule('a')]))
    with pytest.raises(ValueError, match='duplicate'):
        provisioner.regenerate_export(path)
    assert path.read_bytes() == first


# SCA-2119: a production dispatch may be narrowed to the reviewed census scope.
# These tests pin selection, write scope, backup scope and the canary gate.


def test_census_scope_selects_exactly_the_registry_rendered_rules(provisioner):
    generator = SimpleNamespace(
        **runpy.run_path(str(Path(__file__).resolve().parents[2] / 'scripts/generate_batch_census_alerts.py'))
    )
    rendered = [item['uid'] for item in generator.rules()]
    scope = provisioner.monitoring_scope.resolve('census')
    assert len(rendered) == 29
    assert [path.name for path in scope.dashboards] == ['batch-stuck-census.json']
    assert provisioner.monitoring_scope.select_uids(scope) == rendered


def test_shipped_scopes_resolve_against_the_repo_trees(provisioner):
    scopes = provisioner.monitoring_scope.load()
    assert set(scopes) == {'census'}
    for scope in scopes.values():
        assert provisioner.monitoring_scope.select_uids(scope)


def test_unknown_scope_and_absent_scope_rules_fail_closed(provisioner):
    with pytest.raises(ValueError, match='unknown monitoring scope'):
        provisioner.monitoring_scope.resolve('not-a-scope')
    scope = provisioner.monitoring_scope.resolve('census')
    only_one = {'omi-census-snapshot-blind': rule('omi-census-snapshot-blind')}
    with pytest.raises(ValueError, match='absent from the combined export'):
        provisioner.scoped_rules(only_one, scope)


def test_scoped_drift_does_not_report_out_of_scope_rules(provisioner):
    api = FakeGrafana({'example': rule(), 'unrelated': rule('unrelated')})
    assert provisioner.reconcile(api, {'example': rule()}, scope='census') == []
    assert provisioner.reconcile(api, {'example': {**rule(), 'title': 'drifted'}}, scope='census') == [
        'example: divergent fields: title'
    ]


def test_scoped_apply_writes_only_scope_rules_and_backs_up_only_them(provisioner, tmp_path):
    api = FakeGrafana({'example': {**rule(), 'title': 'old'}, 'unrelated': rule('unrelated')})
    backup = tmp_path / 'backup'
    assert provisioner.reconcile(api, {'example': rule()}, backup=backup, scope='census') == []
    assert [write[0] for write in api.writes] == ['PUT']
    snapshot = json.loads(backup.read_text())
    assert snapshot['scope'] == 'census'
    assert [item['uid'] for item in snapshot['rules']] == ['example']
    assert snapshot['created_uids'] == []
    assert backup.stat().st_mode & 0o777 == 0o600


def test_unscoped_apply_keeps_the_whole_export_backup(provisioner, tmp_path):
    api = FakeGrafana({'example': {**rule(), 'title': 'old'}, 'unrelated': rule('unrelated')})
    backup = tmp_path / 'backup'
    assert provisioner.reconcile(api, {'example': rule()}, backup=backup) == [
        'unrelated: live but uncommitted (retained)'
    ]
    snapshot = json.loads(backup.read_text())
    assert set(snapshot) == {'rules', 'created_uids'}
    assert {item['uid'] for item in snapshot['rules']} == {'example', 'unrelated'}


def canary(provisioner, uid):
    return {
        **rule(uid),
        'execErrState': 'Alerting',
        'noDataState': 'Alerting',
        'data': [
            {
                'refId': 'A',
                'relativeTimeRange': {'from': 900, 'to': 0},
                'datasourceUid': 'prometheus',
                'model': {},
            },
            {
                'refId': 'B',
                'datasourceUid': '__expr__',
                'model': {'conditions': [{'evaluator': {'type': 'lt', 'params': [0]}}]},
            },
        ],
    }


def test_scoped_keep_last_requires_installed_canaries_before_any_write(provisioner, tmp_path):
    keep_last = {**rule(), 'execErrState': 'KeepLast'}
    canaries = {uid: canary(provisioner, uid) for uid in provisioner.CANARY_UIDS}
    api = FakeGrafana({})
    backup = tmp_path / 'backup'
    differences = provisioner.reconcile(api, {'example': keep_last}, backup=backup, scope='census', canaries=canaries)
    assert differences == [
        f'{uid}: scoped apply needs the committed datasource canary installed unchanged'
        for uid in sorted(provisioner.CANARY_UIDS)
    ]
    assert api.writes == []
    assert not backup.exists()


def test_scoped_keep_last_probe_failure_blocks_writes(provisioner, tmp_path):
    keep_last = {**rule(), 'execErrState': 'KeepLast'}
    canaries = {uid: canary(provisioner, uid) for uid in provisioner.CANARY_UIDS}

    class UnhealthyProbe(FakeGrafana):
        def request(self, path, body=None, method='GET', *, editable=False):
            if path == '/api/ds/query':
                return {'results': {}}
            return super().request(path, body, method, editable=editable)

    api = UnhealthyProbe(dict(canaries))
    backup = tmp_path / 'backup'
    differences = provisioner.reconcile(api, {'example': keep_last}, backup=backup, scope='census', canaries=canaries)
    assert differences and all('query failed' in item for item in differences)
    assert api.writes == []
    assert not backup.exists()


def mixed_provenance_group(folder='other', rule_group='other-group', prefix='other'):
    """Two live rules in one group that no single provisioner owns."""
    return {
        f'{prefix}-ui': {**rule(f'{prefix}-ui'), 'folderUID': folder, 'ruleGroup': rule_group, 'provenance': ''},
        f'{prefix}-api': {**rule(f'{prefix}-api'), 'folderUID': folder, 'ruleGroup': rule_group, 'provenance': 'api'},
    }


def test_unscoped_apply_still_rejects_mixed_provenance_in_an_unrelated_live_group(provisioner, tmp_path):
    """A full run keeps the pre-scope guard: every live group must be single-provenance."""
    live = {'example': rule(), **mixed_provenance_group()}
    api = FakeGrafana(live)
    backup = tmp_path / 'backup'
    with pytest.raises(ValueError, match='mixed provenance'):
        provisioner.reconcile(api, {'example': {**rule(), 'title': 'new'}}, backup=backup)
    assert api.writes == []
    assert not backup.exists()


def test_scoped_apply_ignores_an_unrelated_group_even_with_mixed_provenance(provisioner, tmp_path):
    """The census scope must not be blocked by provenance drift it cannot touch."""
    live = {'example': {**rule(), 'title': 'old'}, **mixed_provenance_group()}
    api = FakeGrafana(live)
    backup = tmp_path / 'backup'
    assert provisioner.reconcile(api, {'example': rule()}, backup=backup, scope='census') == []
    assert [write[0] for write in api.writes] == ['PUT']
    snapshot = json.loads(backup.read_text())
    assert [item['uid'] for item in snapshot['rules']] == ['example']


def test_scoped_apply_still_rejects_mixed_provenance_in_a_group_it_can_write(provisioner, tmp_path):
    """Narrowing the scan must not license a partial takeover of the census group."""
    live = {'example': {**rule(), 'provenance': ''}, 'sibling': {**rule('sibling'), 'provenance': 'api'}}
    api = FakeGrafana(live)
    backup = tmp_path / 'backup'
    with pytest.raises(ValueError, match='mixed provenance'):
        provisioner.reconcile(api, {'example': {**rule(), 'title': 'new'}}, backup=backup, scope='census')
    assert api.writes == []
    assert not backup.exists()
