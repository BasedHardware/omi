"""SCA-2189 provisioning cannot mutate other alerts or any dashboard."""

import copy
import importlib.util
import json
import sys
import urllib.response
from io import BytesIO
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'


@pytest.fixture(scope='module')
def scoped():
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec = importlib.util.spec_from_file_location(
            'scoped_alert_test', SCRIPTS / 'provision_firestore_cost_alerts.py'
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS))


class Grafana:
    def __init__(self, rules):
        self.live = copy.deepcopy(rules)
        self.writes = []
        self.dashboards = {'ops': {'uid': 'ops', 'version': 4}, 'business': {'uid': 'business', 'version': 7}}
        self.ignore_writes = False
        self.mutate_other = False
        spec = importlib.util.spec_from_file_location('shared_canary_test', SCRIPTS / 'provision_monitoring_alerts.py')
        shared = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(shared)
        committed = shared.load_rules(shared.RULES)
        self.live.update({uid: committed[uid] for uid in shared.CANARY_UIDS})

    def rules(self):
        return copy.deepcopy(self.live)

    def request(self, path, body=None, method='GET', *, editable=False):
        if path == '/api/ds/query' and method == 'POST':
            ref = body['queries'][0]['refId']
            return {
                'results': {ref: {'frames': [{'schema': {'fields': [{'type': 'number'}]}, 'data': {'values': [[1]]}}]}}
            }
        if method == 'GET':
            if path.startswith('/api/search?'):
                return [{'uid': uid} for uid in self.dashboards]
            if path.startswith('/api/dashboards/uid/'):
                return {'dashboard': self.dashboards[path.rsplit('/', 1)[1]]}
            if path.endswith('contact-points'):
                return [{'name': 'Omi - Services Alerting (Telegram)', 'type': 'telegram'}]
            if path.startswith('/api/folders/'):
                return {}
            raise AssertionError(path)
        self.writes.append((method, path, copy.deepcopy(body)))
        if not self.ignore_writes:
            if method == 'DELETE':
                del self.live[path.rsplit('/', 1)[1]]
            else:
                self.live[body['uid']] = copy.deepcopy(body)
        if self.mutate_other:
            self.live['unrelated']['title'] = 'concurrent edit'
        return body


def desired(scoped):
    rules = scoped.shared.load_rules(scoped.shared.RULES)
    return {uid: rules[uid] for uid in scoped.TARGETS}


@pytest.mark.parametrize(
    'value',
    [
        '',
        '*',
        'omi-firestore-unattributed-reads',
        ',omi-firestore-billed-reads-step',
        'omi-firestore-billed-reads-step,omi-firestore-billed-reads-step',
        ' omi-firestore-billed-reads-step',
    ],
)
def test_refuses_unapproved_or_ambiguous_selection(scoped, value):
    with pytest.raises(ValueError):
        scoped.select_uids(value)


def test_dry_run_and_apply_leave_other_266_alerts_and_dashboards_unchanged(scoped, tmp_path):
    rules = desired(scoped)
    other = {f'other-{i}': {'uid': f'other-{i}', 'title': 'live differs from export'} for i in range(263)}
    api = Grafana(other)
    other = copy.deepcopy(api.live)  # 263 other rules plus three existing datasource canaries.
    dashboards = copy.deepcopy(api.dashboards)
    receipt = scoped.execute(api, rules, scoped.TARGETS)
    assert len(receipt['differences']) == 3
    assert api.writes == []
    backup = tmp_path / 'backup.json'
    receipt = scoped.execute(api, rules, scoped.TARGETS, backup=backup)
    assert receipt['differences'] == []
    assert receipt['unchanged_before'] == receipt['unchanged_after']
    assert {body['uid'] for _, _, body in api.writes} == scoped.TARGETS
    assert len(api.writes) == 3
    assert {uid: api.live[uid] for uid in other} == other
    assert api.dashboards == dashboards
    assert json.loads(backup.read_text()) == {'rules': [], 'created_uids': sorted(scoped.TARGETS)}
    assert backup.stat().st_mode & 0o777 == 0o600


def test_backup_restores_previous_rules_and_removes_only_new_selected_rules(scoped, tmp_path):
    rules = desired(scoped)
    uid = sorted(scoped.TARGETS)[0]
    old = {**rules[uid], 'title': 'previous production definition', 'provenance': ''}
    api = Grafana({uid: old, 'unrelated': {'uid': 'unrelated', 'title': 'keep'}})
    before = copy.deepcopy(api.live)
    backup = tmp_path / 'backup.json'
    scoped.execute(api, rules, scoped.TARGETS, backup=backup)
    assert scoped.execute(api, rules, scoped.TARGETS, restore=backup)['mode'] == 'dry-run'
    receipt = scoped.execute(api, rules, scoped.TARGETS, restore=backup, backup=tmp_path / 'reverse.json')
    assert receipt['differences'] == []
    assert scoped.shared.comparable(api.live[uid]) == scoped.shared.comparable(old)
    assert set(api.live) == set(before)
    assert api.live['unrelated'] == before['unrelated']


def test_restore_completes_all_deletes_through_real_empty_204_parser(scoped, tmp_path, monkeypatch):
    """Use the actual HTTP response parser, not the JSON-returning request fake."""
    state = Grafana({'unrelated': {'uid': 'unrelated', 'title': 'retain'}})
    before = copy.deepcopy(state.live)

    class Opener:
        def open(self, request, timeout):
            path = request.full_url.removeprefix('https://monitor.omi.me')
            method = request.get_method()
            if path == scoped.shared.API and method == 'GET':
                result = list(state.rules().values())
            else:
                body = json.loads(request.data) if request.data else None
                result = state.request(path, body, method)
            data = b'' if method == 'DELETE' else json.dumps(result).encode()
            return urllib.response.addinfourl(
                BytesIO(data), {}, request.full_url, code=204 if method == 'DELETE' else 200
            )

    monkeypatch.setattr(scoped.shared.urllib.request, 'build_opener', lambda *_: Opener())
    api = scoped.shared.Grafana('https://monitor.omi.me', 'fake-test-token')
    backup = tmp_path / 'apply-backup.json'
    apply_receipt = scoped.execute(api, desired(scoped), scoped.TARGETS, backup=backup)
    restore_receipt = scoped.execute(
        api, desired(scoped), scoped.TARGETS, restore=backup, backup=tmp_path / 'restore-backup.json'
    )
    assert restore_receipt['status'] == 'complete'
    assert restore_receipt['differences'] == []
    assert [path.rsplit('/', 1)[1] for method, path, _ in state.writes if method == 'DELETE'] == sorted(scoped.TARGETS)
    assert state.live == before
    assert apply_receipt['unchanged_before'] == restore_receipt['unchanged_after']
    (tmp_path / 'offline-204-receipts.json').write_text(
        json.dumps(
            {
                'evidence_kind': 'hermetic HTTP response-parser regression; not production',
                'apply': apply_receipt,
                'restore': restore_receipt,
            },
            indent=2,
        )
    )


@pytest.mark.parametrize(
    'method,path,body',
    [
        ('POST', '/api/dashboards/db', {'uid': 'ops'}),
        ('PUT', '/api/v1/provisioning/alert-rules/unrelated', {'uid': 'unrelated'}),
        ('POST', '/api/v1/provisioning/alert-rules', {'uid': 'unrelated'}),
        ('DELETE', '/api/v1/provisioning/alert-rules/unrelated', None),
        ('PUT', '/api/v1/provisioning/policies', {}),
    ],
)
def test_mutation_boundary_refuses_every_non_target_write(scoped, method, path, body):
    api = Grafana({})
    with pytest.raises(ValueError, match='outside selected'):
        scoped.ScopedGrafana(api, scoped.TARGETS).request(path, body, method)
    assert api.writes == []


def test_existing_backup_and_out_of_scope_restore_refused_before_writes(scoped, tmp_path):
    api = Grafana({})
    backup = tmp_path / 'backup.json'
    backup.write_text(json.dumps({'rules': [{'uid': 'unrelated'}], 'created_uids': []}))
    with pytest.raises(FileExistsError):
        scoped.execute(api, desired(scoped), scoped.TARGETS, backup=backup)
    with pytest.raises(ValueError, match='exactly the selected'):
        scoped.execute(api, desired(scoped), scoped.TARGETS, restore=backup)
    assert api.writes == []


def test_failed_target_readback_and_concurrent_other_changes_cannot_pass(scoped, tmp_path):
    api = Grafana({'unrelated': {'uid': 'unrelated', 'title': 'keep'}})
    api.ignore_writes = True
    receipt = scoped.execute(api, desired(scoped), scoped.TARGETS, backup=tmp_path / 'ignored.json')
    assert len(receipt['differences']) == 3
    assert receipt['status'] == 'failed-readback'
    assert receipt['selected_expected'] == desired(scoped)
    api.ignore_writes = False
    api.mutate_other = True
    with pytest.raises(ValueError, match='non-target alerts or dashboards changed'):
        scoped.execute(api, desired(scoped), scoped.TARGETS, backup=tmp_path / 'concurrent.json')


def test_missing_keep_last_canary_is_not_installed_as_a_side_effect(scoped, tmp_path):
    api = Grafana({})
    del api.live[scoped.shared.CANARY_UIDS[0]]
    with pytest.raises(ValueError, match='existing active committed datasource canaries'):
        scoped.execute(api, desired(scoped), scoped.TARGETS, backup=tmp_path / 'backup')
    assert api.writes == []
    assert not (tmp_path / 'backup').exists()


def test_cli_failure_preserves_backup_and_incomplete_evidence(scoped, tmp_path, monkeypatch):
    api = Grafana({})
    original = api.request

    def fail_second_write(path, body=None, method='GET', **kwargs):
        if method in ('POST', 'PUT') and path.startswith(scoped.shared.API) and api.writes:
            raise ValueError('simulated interrupted apply')
        return original(path, body, method, **kwargs)

    api.request = fail_second_write
    monkeypatch.setattr(scoped.shared, 'Grafana', lambda *_: api)
    monkeypatch.setenv('MONITOR_GRAFANA_TOKEN', 'fake-test-only')
    backup, receipt = tmp_path / 'backup.json', tmp_path / 'receipt.json'
    monkeypatch.setattr(
        sys,
        'argv',
        [
            'scoped',
            '--target-uids',
            ','.join(sorted(scoped.TARGETS)),
            '--source-sha',
            'a' * 40,
            '--apply',
            '--backup-file',
            str(backup),
            '--receipt-file',
            str(receipt),
        ],
    )
    assert scoped.main() == 1
    saved = json.loads(receipt.read_text())
    assert saved['status'] == 'incomplete'
    assert saved['source_sha'] == 'a' * 40
    assert saved['backup_sha256'] == scoped.hashlib.sha256(backup.read_bytes()).hexdigest()
    assert len(api.writes) == 1
    assert receipt.stat().st_mode & 0o777 == 0o600


def test_cli_invalid_scope_never_constructs_api(scoped, tmp_path, monkeypatch):
    def forbidden(*_):
        raise AssertionError('must refuse before network')

    monkeypatch.setattr(scoped.shared, 'Grafana', forbidden)
    monkeypatch.setattr(
        sys,
        'argv',
        ['scoped', '--target-uids', 'other', '--source-sha', 'a' * 40, '--receipt-file', str(tmp_path / 'receipt')],
    )
    assert scoped.main() == 1


def test_dedicated_workflow_is_dispatch_only_gated_main_with_no_dashboard_steps():
    root = SCRIPTS.parents[1]
    workflow = yaml.safe_load((root / '.github/workflows/firestore_cost_alert_provisioning.yml').read_text())
    assert set(workflow.get('on', workflow.get(True))) == {'workflow_dispatch'}
    job = workflow['jobs']['provision']
    assert job['environment'] == 'prod'
    assert "github.ref == 'refs/heads/main'" in job['if']
    assert workflow['concurrency']['group'] == 'grafana-dashboard-provisioning-prod'
    assert job['concurrency']['group'] == 'grafana-alert-provisioning-prod'
    steps = '\n'.join(step.get('run', '') for step in job['steps'])
    assert 'provision_firestore_cost_alerts.py' in steps
    assert 'provision_grafana_dashboards.py' not in steps
    assert 'provision_monitoring_alerts.py' not in steps
    assert 'BUSINESS_GRAFANA_TOKEN' not in json.dumps(job)
    assert 'test "$EXPECTED_SOURCE_SHA" = "$GITHUB_SHA"' in steps
