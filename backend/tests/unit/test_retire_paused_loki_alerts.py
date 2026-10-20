"""Constrain manual deletion to reviewed, backed-up, still-paused Loki identities."""

import copy
import io
import json
import runpy
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / 'backend/scripts/retire_paused_loki_alerts.py'


@pytest.fixture
def helper(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    return SimpleNamespace(**runpy.run_path(str(SCRIPT)))


class FakeGrafana:
    def __init__(self, helper, backup=None):
        self.live = copy.deepcopy(helper.retired_rules())
        self.calls = []
        self.backup = backup
        self.ignore_delete = False
        self.before_get = None

    def request(self, path, *, method='GET', editable=False):
        uid = path.rsplit('/', 1)[1]
        self.calls.append((method, uid))
        if method == 'DELETE':
            assert self.backup and self.backup.is_file()
            snapshot = json.loads(self.backup.read_text())
            assert uid in snapshot['rules']
            assert self.backup.stat().st_mode & 0o777 == 0o600
            if not self.ignore_delete:
                del self.live[uid]
            return None
        assert method == 'GET'
        if self.before_get:
            self.before_get(uid)
        return copy.deepcopy(self.live.get(uid))


def test_default_preflight_only_gets_four_explicit_uids(helper):
    api = FakeGrafana(helper)
    assert helper.retire(api, {}, helper.retired_rules()) == ['READY ' + uid for uid in sorted(helper.UIDS)]
    assert api.calls == [('GET', uid) for uid in sorted(helper.UIDS)]


def test_retained_canonical_rule_blocks_all_remote_access(helper):
    api = FakeGrafana(helper)
    with pytest.raises(ValueError):
        helper.retire(api, {next(iter(helper.UIDS)): {}}, helper.retired_rules())
    assert api.calls == []


@pytest.mark.parametrize(
    'change',
    [
        'unpause',
        'query',
        'source',
        'identity',
        'file_owned',
        'pending',
        'receiver',
        'annotations',
        'labels',
        'condition',
        'record',
        'missing_series',
    ],
)
def test_unknown_or_changed_live_rule_blocks_entire_plan(helper, change, tmp_path):
    backup = tmp_path / 'snapshot'
    api = FakeGrafana(helper, backup)
    r = api.live[sorted(helper.UIDS)[-1]]
    if change == 'unpause':
        r['isPaused'] = False
    elif change == 'query':
        r['data'][0]['model']['expr'] += ' or vector(0)'
    elif change == 'source':
        r['data'][0]['datasourceUid'] = 'unrelated'
    elif change == 'identity':
        r['title'] = 'unrelated new rule'
    elif change == 'file_owned':
        r['provenance'] = 'file'
    elif change == 'pending':
        r['for'] = '99m'
    elif change == 'receiver':
        r['notification_settings']['receiver'] = 'other'
    elif change == 'annotations':
        r['annotations']['summary'] = 'changed'
    elif change == 'labels':
        r['labels']['severity'] = 'changed'
    elif change == 'record':
        r['record'] = {'metric': 'repurposed_recording_rule', 'from': 'A'}
    elif change == 'missing_series':
        r['missingSeriesEvalsToResolve'] = 99
    else:
        r['condition'] = 'changed'
    with pytest.raises(ValueError):
        helper.retire(api, {}, helper.retired_rules(), backup=backup)
    assert not backup.exists()
    assert all(method == 'GET' for method, _ in api.calls)


def test_grafana13_readback_defaults_still_match_reviewed_rules(helper):
    api = FakeGrafana(helper)
    for rule in api.live.values():
        rule['notification_settings']['repeat_interval'] = '1d'
        for node in rule['data']:
            node.setdefault('queryType', '')
            node['model'].setdefault('intervalMs', 1000)
            node['model'].setdefault('maxDataPoints', 43200)
    assert helper.retire(api, {}, helper.retired_rules()) == ['READY ' + uid for uid in sorted(helper.UIDS)]


def test_apply_backup_precedes_deletes_and_all_four_read_back_absent(helper, tmp_path):
    backup = tmp_path / 'snapshot'
    api = FakeGrafana(helper, backup)
    assert helper.retire(api, {}, helper.retired_rules(), backup=backup) == [
        'ABSENT ' + uid for uid in sorted(helper.UIDS)
    ]
    assert not api.live
    assert set(json.loads(backup.read_text())['rules']) == helper.UIDS
    assert sum(method == 'DELETE' for method, _ in api.calls) == 4
    assert api.calls[-4:] == [('GET', uid) for uid in sorted(helper.UIDS)]


@pytest.mark.parametrize('symlink', [False, True])
def test_exclusive_backup_rejects_overwrite_and_symlink(helper, tmp_path, symlink):
    backup = tmp_path / 'snapshot'
    existing = tmp_path / 'existing'
    existing.write_text('preserve')
    if symlink:
        backup.symlink_to(existing)
    else:
        backup.write_text('preserve')
    api = FakeGrafana(helper, backup)
    with pytest.raises(FileExistsError):
        helper.retire(api, {}, helper.retired_rules(), backup=backup)
    assert all(method == 'GET' for method, _ in api.calls)
    assert existing.read_text() == 'preserve' and backup.read_text() == 'preserve'


def test_concurrent_unpause_after_snapshot_blocks_delete(helper, tmp_path):
    backup = tmp_path / 'snapshot'
    api = FakeGrafana(helper, backup)
    api.before_get = lambda uid: api.live[uid].update(isPaused=False) if backup.exists() else None
    with pytest.raises(ValueError):
        helper.retire(api, {}, helper.retired_rules(), backup=backup)
    assert backup.exists() and all(method == 'GET' for method, _ in api.calls)


def test_ignored_delete_fails_readback_and_stops(helper, tmp_path):
    backup = tmp_path / 'snapshot'
    api = FakeGrafana(helper, backup)
    api.ignore_delete = True
    with pytest.raises(ValueError):
        helper.retire(api, {}, helper.retired_rules(), backup=backup)
    assert sum(method == 'DELETE' for method, _ in api.calls) == 1


def test_absent_rules_are_idempotent_and_unknown_uids_retained(helper):
    api = FakeGrafana(helper)
    api.live = {'unrelated': {'uid': 'unrelated'}}
    assert helper.retire(api, {}, helper.retired_rules()) == ['ABSENT ' + uid for uid in sorted(helper.UIDS)]
    assert 'unrelated' in api.live


def test_client_limits_host_methods_and_follows_no_redirects(helper):
    with pytest.raises(ValueError):
        helper.RetirementGrafana('https://other.example', 'unused')
    client = helper.RetirementGrafana('https://monitor.omi.me', 'unused')
    with pytest.raises(ValueError):
        client.request(helper.API + '/unrelated', method='DELETE')
    with pytest.raises(ValueError):
        client.request(helper.API + '/' + next(iter(helper.UIDS)), method='POST')
    assert helper.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.example') is None


def test_only_http404_counts_as_absent_not_null_or_errors(helper, monkeypatch):
    uid = sorted(helper.UIDS)[0]
    client = helper.RetirementGrafana('https://monitor.omi.me', 'unused')
    path = helper.API + '/' + uid

    class Opener:
        def open(self, request, timeout):
            assert timeout == 30
            if self.code:
                raise urllib.error.HTTPError(request.full_url, self.code, '', {}, io.BytesIO())
            return io.BytesIO(b'null')

    opener = Opener()
    monkeypatch.setattr(helper.urllib.request, 'build_opener', lambda *_: opener)
    opener.code = 404
    assert client.request(path) is None
    for code in [0, 401, 500, 302]:
        opener.code = code
        with pytest.raises(ValueError):
            client.request(path)


def test_script_stays_bounded():
    assert len(SCRIPT.read_text().splitlines()) <= 250
