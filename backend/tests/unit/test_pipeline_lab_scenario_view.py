"""Pipeline-lab ``scenario view``: run-directory layouts, missing files, ordering, path safety, the read-only
loopback server and the page's self-containment. Synthetic run directories only."""

import http.client
import json
import os
import re
import shutil

import pytest

from testing.pipeline_lab import cli
from testing.pipeline_lab.inspector import scenario_view, server
from testing.pipeline_lab.inspector.reader import BadRequest, NotFound

STATIC = server.STATIC_DIR


def result(name, outcome, ok=True):
    return {
        'scenario': name,
        'outcome': outcome,
        'checks': [{'check': 'conversation of @finish: visible=true', 'ok': ok, 'detail': 'B in abcd1234'}],
        'conversations': [{'handle': 'abcd1234', 'recordings': ['B'], 'words': 10, 'visible': True}],
        'timeline': [{'t': 0.0, 'kind': 'capture_start', 'ref': 'B', 'outcome': 'recording'}],
        'stand_ins': {'record_admission': 1},
    }


def home_doc():
    return {
        'schema': 1,
        'route': 'GET /v1/conversations',
        'evidence': 'app/lib/providers/conversation_home_fetch.dart:115',
        'snapshots': [{'at': 60.0, 'label': 'final', 'status': 200, 'response': [{'id': 'abcd1234-x'}]}],
    }


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def make_run(root, outcomes, *, home=True, scenario=True):
    for name, outcome in outcomes.items():
        write(root / name / 'result.json', result(name, outcome, ok=outcome == 'passed'))
        if home:
            write(root / name / 'home.json', home_doc())
        if scenario:
            write(root / name / 'scenario.json', {'name': name, 'description': 'synthetic'})
    return root


# ---- layouts ------------------------------------------------------------------------------------


def test_run_layout_orders_failures_first_and_reports_missing_run_files(tmp_path):
    run = scenario_view.RunDir(
        make_run(tmp_path, {'b_pass': 'passed', 'a_fail': 'failed', 'c_err': 'error', 'd_x': 'xfail'})
    )
    view = run.overview()
    assert view['kind'] == 'run'
    assert view['scenarios'] == ['c_err', 'a_fail', 'd_x', 'b_pass']
    assert view['sides']['run']['outcomes']['a_fail'] == 'failed'
    assert {m['file'] for m in view['sides']['run']['missing']} == {'run.json', 'verdict.json'}


def test_run_json_and_verdict_json_are_read_when_present(tmp_path):
    make_run(tmp_path, {'one': 'passed'})
    write(tmp_path / 'run.json', {'ref': 'origin/main', 'backend_tree': 'abc123'})
    write(tmp_path / 'verdict.json', {'outcome': 'failed', 'scenarios': [{'name': 'one', 'outcome': 'failed'}]})
    view = scenario_view.RunDir(tmp_path).overview()
    assert view['sides']['run']['run'] == {'ref': 'origin/main', 'backend_tree': 'abc123'}
    assert view['sides']['run']['outcomes'] == {'one': 'failed'}  # verdict.json wins over result.json
    assert view['sides']['run']['missing'] == []


@pytest.mark.parametrize(
    'verdict',
    [
        {'scenarios': [{'scenario': 'one', 'outcome': 'xpass'}]},
        {'scenarios': {'one': 'xpass'}},
        {'scenarios': {'one': {'outcome': 'xpass'}}},
        {'one': 'xpass'},
    ],
)
def test_verdict_shapes(verdict):
    assert scenario_view._verdict_outcome(verdict, 'one') == 'xpass'
    assert scenario_view._verdict_outcome(verdict, 'two') is None


def test_scenario_bundle_names_each_missing_file(tmp_path):
    make_run(tmp_path, {'one': 'passed'}, home=False, scenario=False)
    (tmp_path / 'one' / 'home.json').write_text('{not json')
    bundle = scenario_view.RunDir(tmp_path).scenario('one')['sides']['run']
    assert bundle['result']['outcome'] == 'passed'
    assert bundle['home'] is None and bundle['scenario'] is None
    problems = {m['file']: m['problem'] for m in bundle['missing']}
    assert problems['scenario.json'] == 'missing'
    assert problems['home.json'].startswith('unreadable')


def test_compare_layout(tmp_path):
    make_run(tmp_path / 'base', {'one': 'failed', 'gone': 'passed'})
    make_run(tmp_path / 'head', {'one': 'passed', 'new': 'error'})
    run = scenario_view.RunDir(tmp_path)
    view = run.overview()
    assert view['kind'] == 'compare'
    assert view['missing'] == [{'file': 'compare.json', 'problem': 'missing'}]
    assert view['scenarios'][0] == 'new'  # head's error first
    assert set(view['scenarios']) == {'one', 'gone', 'new'}
    one = run.scenario('one')['sides']
    assert one['base']['result']['outcome'] == 'failed' and one['head']['result']['outcome'] == 'passed'
    assert run.scenario('gone')['sides']['head'] is None
    write(tmp_path / 'compare.json', {'schema': 1})
    assert scenario_view.RunDir(tmp_path).overview()['compare'] == {'schema': 1}


def test_single_scenario_directory(tmp_path):
    write(tmp_path / 'result.json', result('solo', 'passed'))
    run = scenario_view.RunDir(tmp_path)
    assert run.kind == 'scenario'
    assert run.overview()['scenarios'] == ['solo']
    assert run.scenario('solo')['sides']['run']['result']['scenario'] == 'solo'


def test_copied_directory_gives_the_same_answers(tmp_path):
    first = make_run(tmp_path / 'here', {'one': 'failed', 'two': 'passed'})
    second = tmp_path / 'elsewhere' / 'copy'
    shutil.copytree(first, second)
    a, b = scenario_view.RunDir(first), scenario_view.RunDir(second)
    strip = lambda v: json.loads(json.dumps(v).replace(str(first), 'ROOT').replace(str(second), 'ROOT'))  # noqa: E731
    assert strip(a.overview()) == strip(b.overview())
    assert strip(a.scenario('one')) == strip(b.scenario('one'))


# ---- path safety --------------------------------------------------------------------------------


@pytest.mark.parametrize('name', ['..', '../etc', 'a/b', '.hidden', ''])
def test_bad_names_are_refused(tmp_path, name):
    run = scenario_view.RunDir(make_run(tmp_path, {'one': 'passed'}))
    with pytest.raises((BadRequest, NotFound)):
        run.scenario(name)


def test_symlink_out_of_the_run_directory_is_refused(tmp_path):
    outside = make_run(tmp_path / 'outside', {'secret': 'passed'})
    root = make_run(tmp_path / 'run', {'one': 'passed'})
    os.symlink(outside / 'secret', root / 'leak')
    run = scenario_view.RunDir(root)
    with pytest.raises(BadRequest):
        run.scenario('leak')
    assert run.overview()['scenarios'] == ['one']


# ---- server -------------------------------------------------------------------------------------


@pytest.fixture()
def served(tmp_path):
    root = make_run(tmp_path / 'run', {'one': 'failed', 'two': 'passed'})
    srv = scenario_view.make_server(root)
    stop = server.serve_in_thread(srv)
    yield srv.server_address[1]
    stop()


def call(port, method, path, headers=None):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    try:
        conn.request(method, path, headers=headers or {})
        res = conn.getresponse()
        return res.status, dict(res.getheaders()), res.read()
    finally:
        conn.close()


def test_server_routes(served):
    status, headers, body = call(served, 'GET', '/')
    assert status == 200 and b'scenario.js' in body
    assert "default-src 'none'" in headers['Content-Security-Policy']
    status, _, body = call(served, 'GET', '/api/run')
    assert status == 200 and json.loads(body)['scenarios'] == ['one', 'two']
    status, _, body = call(served, 'GET', '/api/scenarios/one')
    assert status == 200 and json.loads(body)['sides']['run']['home']['route'] == 'GET /v1/conversations'
    for path in ('/static/scenario.js', '/static/scenario.css', '/static/app.css'):
        assert call(served, 'GET', path)[0] == 200
    assert call(served, 'GET', '/api/scenarios/nope')[0] == 404
    assert call(served, 'GET', '/api/scenarios/..%2Fx')[0] in (400, 404)
    assert call(served, 'GET', '/api/runs')[0] == 404


def test_server_is_read_only_and_keeps_the_inspector_access_policy(served):
    assert call(served, 'POST', '/api/run')[0] == 405
    assert call(served, 'GET', '/api/run', {'Host': 'evil.example'})[0] == 421
    assert call(served, 'GET', '/api/run', {'Tailscale-User-Login': 'someone@example.com'})[0] == 403


def test_server_binds_loopback_only(tmp_path):
    with pytest.raises(ValueError):
        scenario_view.ScenarioViewServer(('0.0.0.0', 0), scenario_view.RunDir(make_run(tmp_path, {'one': 'passed'})))


# ---- page assets and CLI ------------------------------------------------------------------------


def test_page_assets_are_self_contained():
    for name in ('scenario.html', 'scenario.css', 'scenario.js'):
        text = (STATIC / name).read_text()
        assert not re.search(r'(?:https?:)?//[a-z0-9.-]+\.[a-z]{2,}/', text, re.I), name
        assert '@import' not in text
    js = (STATIC / 'scenario.js').read_text()
    assert not re.search(r'\.innerHTML\s*=|outerHTML|insertAdjacentHTML|document\.write|eval\(', js)
    assert re.findall(r'fetch\((\w+)', js) == ['url']  # one fetch helper
    assert {'/api/run', '/api/scenarios/'} <= set(re.findall(r"['`](/api/[a-z/]*)", js))


def test_day_replay_inspector_page_is_unchanged_by_the_view():
    assert (STATIC / 'index.html').read_text().count('/static/app.js') == 1
    assert 'scenario' not in (STATIC / 'index.html').read_text()


def test_cli_parses_scenario_view():
    args = cli.build_parser().parse_args(['scenario', 'view', '/tmp/run-dir', '--port', '0'])
    assert (args.command, args.scenario_command, args.run_dir, args.port) == ('scenario', 'view', '/tmp/run-dir', 0)
    args = cli.build_parser().parse_args(['scenario', 'view', '/tmp/run-dir'])
    assert args.port == 0


def test_cli_view_of_a_missing_directory_is_an_error(tmp_path, capsys):
    code = cli.main(['scenario', 'view', str(tmp_path / 'absent')])
    assert code != 0
    assert 'no such run directory' in capsys.readouterr().err
