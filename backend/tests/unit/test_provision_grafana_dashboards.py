"""Dashboard writes require recoverable snapshots and exact desired content/folders."""

import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import urllib.error

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/provision_grafana_dashboards.py'
spec = importlib.util.spec_from_file_location('provision_grafana_dashboards', SCRIPT)
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
TOKEN = 'dummy-token-never-print'
DESIRED = {
    'uid': 'overview',
    'title': 'Reviewed overview',
    'version': 4,
    'panels': [
        {'id': 1, 'title': 'Errors', 'pluginVersion': '11.0', 'targets': [{'refId': 'A', 'expr': 'sum(errors_total)'}]}
    ],
}


def served(version=4, folder='omi-services', uid='overview'):
    board = copy.deepcopy(DESIRED)
    board.update(uid=uid, version=version)
    return {'dashboard': board, 'meta': {'folderUid': folder}}


@pytest.fixture
def cli(tmp_path, monkeypatch):
    (tmp_path / 'overview.json').write_text(json.dumps(DESIRED))
    monkeypatch.setenv('MONITOR_GRAFANA_TOKEN', TOKEN)
    monkeypatch.setattr(
        sys,
        'argv',
        [
            'provision',
            '--dashboards-dir',
            str(tmp_path),
            '--grafana-url',
            'https://monitor.omi.me',
            '--backup-file',
            str(tmp_path / 'backup'),
        ],
    )
    return tmp_path


class Response:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def api(monkeypatch, responses, before_post=None):
    requests = []

    def open_request(request):
        requests.append(request)
        assert request.get_header('Authorization') == 'Bearer ' + TOKEN
        if request.get_method() == 'POST' and before_post:
            before_post(request)
        value = responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return Response(value)

    monkeypatch.setattr(s, '_open', open_request)
    return requests


def error(code):
    return urllib.error.HTTPError('https://monitor.omi.me', code, TOKEN, {}, io.BytesIO(TOKEN.encode()))


@pytest.mark.parametrize('folder_uid', ['omi-services', ''])
def test_existing_folder_and_complete_snapshot_preserved_before_post(cli, monkeypatch, folder_uid):
    before = served(folder=folder_uid)

    def snapshot_exists(request):
        backup = cli / 'backup'
        assert backup.stat().st_mode & 0o777 == 0o600
        assert json.loads(backup.read_text())['dashboards'] == {'overview': before}

    requests = api(monkeypatch, [before, {'status': 'success', 'version': 5}, served(5, folder_uid)], snapshot_exists)
    assert s.main() == 0
    assert [r.get_method() for r in requests] == ['GET', 'POST', 'GET']
    assert json.loads(requests[1].data)['folderUid'] == folder_uid


def test_new_dashboard_general_and_uid_recorded_for_rollback(cli, monkeypatch):
    requests = api(monkeypatch, [error(404), {'status': 'success', 'version': 1}, served(1, '')])
    assert s.main() == 0
    assert 'folderUid' not in json.loads(requests[1].data)
    assert json.loads((cli / 'backup').read_text())['created_uids'] == ['overview']


def test_new_dashboard_explicit_folder_is_held(cli, monkeypatch):
    (cli / 'overview.json').write_text(json.dumps(dict(DESIRED, folderUid='non-general')))
    requests = api(monkeypatch, [error(404)])
    assert s.main() == 1 and len(requests) == 1
    assert not (cli / 'backup').exists()


@pytest.mark.parametrize('phase', ['pre-read', 'post', 'read-back'])
def test_http401_is_sanitized_and_fails(cli, monkeypatch, capsys, phase):
    responses = [served(), {'status': 'success', 'version': 5}, served(5)]
    index = ['pre-read', 'post', 'read-back'].index(phase)
    responses[index:] = [error(401)]
    api(monkeypatch, responses)
    assert s.main() == 1
    output = capsys.readouterr()
    assert 'HTTP 401' in output.err
    assert TOKEN not in output.out + output.err
    assert 'Provisioned' not in output.out


@pytest.mark.parametrize('payload', [{'status': TOKEN, 'details': TOKEN}, {'status': 'success', 'version': TOKEN}])
def test_invalid_post_response_is_not_dumped(cli, monkeypatch, capsys, payload):
    api(monkeypatch, [served(), payload])
    assert s.main() == 1
    output = capsys.readouterr()
    assert TOKEN not in output.out + output.err


def test_missing_existing_folder_fails_before_post(cli, monkeypatch):
    before = served()
    before['meta'] = {}
    requests = api(monkeypatch, [before])
    assert s.main() == 1 and len(requests) == 1


def test_stale_readback_fails(cli, monkeypatch, capsys):
    api(monkeypatch, [served(), {'status': 'success', 'version': 5}, served(4)])
    ticks = iter([0, 1, 21])
    monkeypatch.setattr(s.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(s.time, 'sleep', lambda seconds: None)
    assert s.main() == 1
    assert 'OK ' not in capsys.readouterr().out


@pytest.mark.parametrize('corruption', ['folder', 'uid', 'title', 'panel', 'query', 'missing-meta'])
def test_newer_version_with_different_content_or_folder_fails(cli, monkeypatch, corruption):
    after = served(6)
    if corruption == 'folder':
        after['meta']['folderUid'] = 'wrong-folder'
    elif corruption == 'missing-meta':
        del after['meta']
    elif corruption == 'panel':
        after['dashboard']['panels'] = []
    elif corruption == 'query':
        after['dashboard']['panels'][0]['targets'][0]['expr'] = 'wrong_total'
    else:
        after['dashboard'][corruption] = 'wrong'
    api(monkeypatch, [served(), {'status': 'success', 'version': 5}, after])
    assert s.main() == 1


def test_server_defaults_revision_id_and_panel_plugin_version_are_accepted(cli, monkeypatch):
    after = served(6)
    after['dashboard'].update(id=999, serverDefault='added')
    after['dashboard']['panels'][0].update(pluginVersion='12.0', anotherDefault=True)
    api(monkeypatch, [served(), {'status': 'success', 'version': 5}, after])
    assert s.main() == 0


def test_all_prereads_validate_before_first_write(cli, monkeypatch):
    (cli / 'second.json').write_text(json.dumps(dict(DESIRED, uid='second')))
    requests = api(monkeypatch, [served(), error(401)])
    assert s.main() == 1
    assert [r.get_method() for r in requests] == ['GET', 'GET']
    assert not (cli / 'backup').exists()


def test_all_snapshots_persisted_before_first_post_and_failure_stops_next_write(cli, monkeypatch):
    (cli / 'second.json').write_text(json.dumps(dict(DESIRED, uid='second')))
    before, second = served(), served(uid='second')

    def verify_snapshot(request):
        snapshot = json.loads((cli / 'backup').read_text())
        assert snapshot['dashboards'] == {'overview': before, 'second': second}

    requests = api(monkeypatch, [before, second, error(500)], verify_snapshot)
    assert s.main() == 1
    assert [r.get_method() for r in requests] == ['GET', 'GET', 'POST']


@pytest.mark.parametrize('kind', ['existing', 'symlink', 'unwritable'])
def test_backup_failure_prevents_any_post(cli, monkeypatch, kind):
    if kind == 'existing':
        (cli / 'backup').write_text('preserve')
    elif kind == 'symlink':
        target = cli / 'untouched'
        target.write_text('preserve')
        (cli / 'backup').symlink_to(target)
    else:
        monkeypatch.setattr(s, 'persist_backup', lambda *a: (_ for _ in ()).throw(OSError('private error')))
    requests = api(monkeypatch, [served()])
    assert s.main() == 1 and [r.get_method() for r in requests] == ['GET']
    if kind != 'unwritable':
        assert (cli / 'backup').read_text() == 'preserve'


@pytest.mark.parametrize('method', ['GET', 'POST'])
@pytest.mark.parametrize('destination', ['https://other.invalid/path', 'http://other.invalid/path'])
def test_authenticated_requests_reject_redirects(monkeypatch, method, destination):
    seen = []

    class Opener:
        def open(self, request, timeout):
            assert timeout == 30
            assert seen[0].redirect_request(request, None, 302, 'Found', {}, destination) is None
            raise error(302)

    def build(handler):
        seen.append(handler)
        assert isinstance(handler, s.NoRedirect)
        return Opener()

    monkeypatch.setattr(s.urllib.request, 'build_opener', build)
    with pytest.raises(urllib.error.HTTPError) as exc:
        if method == 'GET':
            s._get_dashboard('https://monitor.omi.me', TOKEN, 'overview')
        else:
            s._post_dashboard('https://monitor.omi.me', TOKEN, {'uid': 'overview'}, 'main', 'omi-services')
    assert exc.value.code == 302


@pytest.mark.parametrize('payload', [None, [TOKEN]])
def test_nonobject_pre_read_cannot_create_board_in_general(cli, monkeypatch, capsys, payload):
    requests = api(monkeypatch, [payload])
    assert s.main() == 1 and len(requests) == 1
    output = capsys.readouterr()
    assert TOKEN not in output.out + output.err


def test_existing_cli_allowlist_and_source_sha_remain_supported(cli, monkeypatch):
    (cli / 'excluded.json').write_text('not JSON')
    monkeypatch.setattr(sys, 'argv', sys.argv + ['--allowlist', 'overview.json', '--source-sha', 'abc123'])
    requests = api(monkeypatch, [error(404), {'status': 'success', 'version': 1}, served(1, '')])
    assert s.main() == 0
    assert json.loads(requests[1].data)['message'] == 'provisioned from main abc123'


def test_missing_backup_flag_cannot_write(cli, monkeypatch):
    monkeypatch.setattr(sys, 'argv', sys.argv[:-2])
    requests = api(monkeypatch, [])
    with pytest.raises(SystemExit):
        s.main()
    assert requests == []


def test_readback_failure_stops_before_next_dashboard_post(cli, monkeypatch):
    (cli / 'second.json').write_text(json.dumps(dict(DESIRED, uid='second')))
    wrong = served(6)
    wrong['dashboard']['panels'][0]['targets'][0]['expr'] = 'wrong_total'
    requests = api(monkeypatch, [served(), served(uid='second'), {'status': 'success', 'version': 5}, wrong])
    assert s.main() == 1
    assert [r.get_method() for r in requests] == ['GET', 'GET', 'POST', 'GET']
    assert (cli / 'backup').exists()


def test_invalid_later_source_prevents_all_reads_and_writes(cli, monkeypatch):
    (cli / 'second.json').write_text('not JSON')
    requests = api(monkeypatch, [])
    assert s.main() == 1
    assert requests == [] and not (cli / 'backup').exists()


def test_json_numeric_equivalence_preserves_boolean_distinction():
    assert s.desired_matches({'field': 1.0}, {'field': 1})
    assert not s.desired_matches({'field': True}, {'field': 1})
