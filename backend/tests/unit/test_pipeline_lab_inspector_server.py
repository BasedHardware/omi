"""Pipeline-lab inspector server: JSON API, path safety, HTTP Range, access policy, verdict writes. Synthetic only."""

import http.client
import json
import os
import stat

import pytest

from testing.pipeline_lab.inspector import sample_run, server
from testing.pipeline_lab.inspector.reader import Reader, content_key, pair_items, task_key

DAY = sample_run.DAY_ID
RUN = sample_run.RUN_ID


@pytest.fixture(scope='module')
def lab(tmp_path_factory):
    base = tmp_path_factory.mktemp('plab-inspector')
    sample_run.write_sample(base / 'store', audio_rate=1000)
    srv = server.make_server(base / 'store', base / 'verdicts', allowed_logins=['owner@example.com'])
    stop = server.serve_in_thread(srv)
    yield {'base': base, 'port': srv.server_address[1], 'reader': srv.reader}
    stop()


def call(lab, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection('127.0.0.1', lab['port'], timeout=10)
    try:
        payload = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
        hdrs = dict(headers or {})
        if isinstance(body, (dict, list)):
            hdrs.setdefault('Content-Type', 'application/json')
        conn.request(method, path, body=payload, headers=hdrs)
        res = conn.getresponse()
        data = res.read()
        return res.status, dict(res.getheaders()), data
    finally:
        conn.close()


def get_json(lab, path, **kw):
    status, headers, data = call(lab, 'GET', path, **kw)
    return status, json.loads(data) if data else None


def first_clip(lab):
    return lab['reader'].audio_index(DAY)[0]


# ---- API ---------------------------------------------------------------------------------


def test_runs_and_overview(lab):
    status, body = get_json(lab, '/api/runs')
    assert status == 200
    assert {r['run_id'] for r in body['runs']} == {RUN, sample_run.MAIN_RUN_ID}
    assert next(r for r in body['runs'] if r['run_id'] == RUN)['statuses']['missing'] == 2
    status, ov = get_json(lab, f'/api/runs/{RUN}')
    assert status == 200
    assert ov['day']['window'] == {'start': '2026-03-14T07:00:00Z', 'end': '2026-03-15T07:00:00Z'}
    assert set(ov['statuses']) == {'same', 'changed', 'new', 'missing', 'merge', 'split'}
    assert ov['digest']['tags']['discard'] == 2  # a discard flip is a content change tagged ``discard``
    kinds = {row['kind'] for row in ov['conversations']}
    assert kinds == {'replay', 'production'}
    starts = [row['started_at'] for row in ov['conversations']]
    assert starts == sorted(starts)
    assert len(ov['timeline']['gaps']) == 2
    assert sum(len(g['production']) for g in ov['groups']) == 24


def test_conversation_detail_has_diff_ready_pairs_audio_and_calls(lab):
    _, ov = get_json(lab, f'/api/runs/{RUN}')
    row = next(r for r in ov['conversations'] if r['title'] == 'Packing list for the coastal hike')
    status, detail = get_json(lab, f'/api/runs/{RUN}/conversations/{row["id"]}')
    assert status == 200
    states = sorted(p['state'] for p in detail['pairs']['tasks'])
    assert states == ['added', 'changed', 'same']
    changed = next(p for p in detail['pairs']['tasks'] if p['state'] == 'changed')
    assert changed['replay']['description'] != changed['baseline']['description']
    assert detail['audio']['url'].startswith(f'/audio/{DAY}/')
    assert detail['audio']['offset'] == pytest.approx(15.0)
    assert {c['conversation_id'] for c in detail['llm_calls']} == {row['id']}
    assert detail['keys']['replay']['summary'] and detail['keys']['baseline']['summary']


def test_missing_conversation_is_served_production_only(lab):
    _, ov = get_json(lab, f'/api/runs/{RUN}')
    missing = [r for r in ov['conversations'] if r['status'] == 'missing']
    assert len(missing) == 2
    status, detail = get_json(lab, f'/api/runs/{RUN}/production/{missing[0]["id"]}')
    assert status == 200 and detail['replay'] is None and detail['kind'] == 'production'
    assert all(p['state'] == 'removed' for p in detail['pairs']['tasks'] + detail['pairs']['memories'])


def test_day_panel_baseline_and_llm_calls(lab):
    status, day = get_json(lab, f'/api/runs/{RUN}/day')
    assert status == 200
    assert day['daily_summary']['replay']['title'] != day['daily_summary']['baseline']['title']
    assert {p['state'] for p in day['notifications']} >= {'same', 'added', 'removed'}
    status, base = get_json(lab, f'/api/days/{DAY}/baseline')
    assert status == 200 and len(base['conversations']) == 24
    status, calls = get_json(lab, f'/api/runs/{RUN}/llm_calls')
    assert status == 200 and len(calls['calls']) > 50


def test_static_ui_is_served_with_a_strict_policy(lab):
    status, headers, body = call(lab, 'GET', '/')
    assert status == 200 and b'/static/app.js' in body
    assert "script-src 'self'" in headers['Content-Security-Policy']
    assert headers['Cache-Control'] == 'no-store' and headers['X-Content-Type-Options'] == 'nosniff'
    for name in ('app.js', 'app.css'):
        assert call(lab, 'GET', f'/static/{name}')[0] == 200


# ---- path safety ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'path',
    [
        '/static/..%2Fserver.py',
        '/static/../server.py',
        '/static/server.py',
        f'/audio/{DAY}/..%2F..%2Fday.json',
        f'/audio/{DAY}/..',
        '/audio/..%2F..%2Fetc/passwd',
        f'/api/runs/..%2F..%2Fcorpus%2F{DAY}',
        f'/api/runs/{RUN}/conversations/..%2Frun',
        '/api/runs/.hidden',
        '/api/days/..%2Fruns/baseline',
        '/etc/passwd',
    ],
)
def test_traversal_is_refused(lab, path):
    status, _, body = call(lab, 'GET', path)
    assert status in (400, 404)
    assert b'root:' not in body and b'"run_id"' not in body


def test_audio_index_entries_cannot_escape_the_audio_directory(tmp_path):
    store = tmp_path / 'store'
    audio = store / 'corpus' / 'd1' / 'audio'
    audio.mkdir(parents=True)
    (tmp_path / 'secret.wav').write_bytes(b'RIFFsecret')
    (audio / 'link.wav').symlink_to(tmp_path / 'secret.wav')
    index = [
        {
            'conversation_id': 'a1',
            'path': '../../../secret.wav',
            'start': '',
            'end': '',
            'codec': 'x',
            'sample_rate': 1,
        },
        {
            'conversation_id': 'a2',
            'path': str(tmp_path / 'secret.wav'),
            'start': '',
            'end': '',
            'codec': 'x',
            'sample_rate': 1,
        },
        {'conversation_id': 'a3', 'path': 'link.wav', 'start': '', 'end': '', 'codec': 'x', 'sample_rate': 1},
    ]
    (audio / 'index.json').write_text(json.dumps(index))
    reader = Reader(store, tmp_path / 'verdicts')
    for clip in ('a1', 'a2', 'a3'):
        with pytest.raises(LookupError):
            reader.audio_file('d1', clip)


# ---- range ---------------------------------------------------------------------------------


def test_audio_full_and_ranges(lab):
    clip = first_clip(lab)
    path = f'/audio/{DAY}/{clip["conversation_id"]}'
    full_status, headers, full = call(lab, 'GET', path)
    assert full_status == 200 and headers['Accept-Ranges'] == 'bytes' and headers['Content-Type'] == 'audio/wav'
    size = len(full)
    status, headers, part = call(lab, 'GET', path, headers={'Range': 'bytes=10-19'})
    assert status == 206 and part == full[10:20] and headers['Content-Range'] == f'bytes 10-19/{size}'
    status, headers, part = call(lab, 'GET', path, headers={'Range': 'bytes=-8'})
    assert status == 206 and part == full[-8:]
    status, headers, part = call(lab, 'GET', path, headers={'Range': f'bytes={size - 5}-'})
    assert status == 206 and part == full[-5:]
    status, headers, part = call(lab, 'GET', path, headers={'Range': f'bytes=0-{size * 2}'})
    assert status == 206 and part == full
    status, headers, _ = call(lab, 'GET', path, headers={'Range': f'bytes={size}-'})
    assert status == 416 and headers['Content-Range'] == f'bytes */{size}'
    status, _, part = call(lab, 'GET', path, headers={'Range': 'bytes=0-1,4-5'})
    assert status == 200 and part == full  # multi-range ignored
    status, headers, part = call(lab, 'HEAD', path, headers={'Range': 'bytes=0-9'})
    assert status == 206 and part == b'' and headers['Content-Length'] == '10'


@pytest.mark.parametrize(
    'header,expected',
    [
        (None, None),
        ('bytes=0-0', (0, 0)),
        ('bytes=5-', (5, 99)),
        ('bytes=-10', (90, 99)),
        ('bytes=-500', (0, 99)),
        ('bytes=10-5', None),
        ('items=0-5', None),
        ('bytes=abc', None),
    ],
)
def test_parse_range(header, expected):
    assert server.parse_range(header, 100) == expected


@pytest.mark.parametrize('header', ['bytes=100-', 'bytes=-0', 'bytes=150-200'])
def test_parse_range_unsatisfiable(header):
    with pytest.raises(ValueError):
        server.parse_range(header, 100)


# ---- access policy -------------------------------------------------------------------------


def test_foreign_host_is_refused(lab):
    assert call(lab, 'GET', '/api/runs', headers={'Host': 'attacker.example'})[0] == 421


def test_proxied_requests_need_an_allowed_login(lab):
    tailnet = {'Host': 'lab-host.tailnet-name.ts.net'}
    assert call(lab, 'GET', '/api/runs', headers=tailnet)[0] == 403
    assert call(lab, 'GET', '/api/runs', headers={**tailnet, 'Tailscale-User-Login': 'someone@example.com'})[0] == 403
    assert call(lab, 'GET', '/api/runs', headers={'X-Forwarded-For': '100.64.0.9'})[0] == 403
    assert call(lab, 'GET', '/api/runs', headers={**tailnet, 'Tailscale-User-Login': 'Owner@Example.com'})[0] == 200


def test_bind_is_loopback_only(tmp_path):
    with pytest.raises(ValueError):
        server.make_server(tmp_path, tmp_path / 'v', host='0.0.0.0', port=0)


# ---- verdicts ------------------------------------------------------------------------------


def _task_target(lab):
    _, ov = get_json(lab, f'/api/runs/{RUN}')
    row = next(r for r in ov['conversations'] if r['title'] == 'Bakery supplier call')
    _, detail = get_json(lab, f'/api/runs/{RUN}/conversations/{row["id"]}')
    return row['id'], detail


def test_verdict_write_appends_a_private_contract_row(lab):
    cid, detail = _task_target(lab)
    replay_task = next(p for p in detail['pairs']['tasks'] if p['replay'])
    body = {
        'run_id': RUN,
        'conversation_id': cid,
        'item_kind': 'task',
        'item_key': replay_task['key'],
        'mark': 'bad',
        'note': 'Too vague.',
    }
    status, _, data = call(lab, 'POST', '/api/verdicts', body)
    assert status == 201, data
    row = json.loads(data)['verdict']
    assert row['day_id'] == DAY and row['ref'] == 'feat/summary-prompt-v7'
    assert row['item_snapshot'] == {'side': 'replay', 'value': replay_task['replay']}
    path = lab['base'] / 'verdicts' / 'verdicts.jsonl'
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE((lab['base'] / 'verdicts').stat().st_mode) == 0o700
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert rows[-1]['id'] == row['id']
    assert set(rows[-1]) >= {
        'id',
        'at',
        'run_id',
        'day_id',
        'ref',
        'conversation_id',
        'item_kind',
        'item_key',
        'mark',
        'note',
        'item_snapshot',
    }

    # latest row per target wins on read; history keeps both
    body['mark'] = 'good'
    body['note'] = ''
    assert call(lab, 'POST', '/api/verdicts', body)[0] == 201
    _, latest = get_json(lab, f'/api/verdicts?conversation_id={cid}&item_kind=task')
    assert [v['mark'] for v in latest['verdicts'] if v['item_key'] == body['item_key']] == ['good']
    _, history = get_json(lab, f'/api/verdicts?conversation_id={cid}&item_kind=task&history=1')
    assert len([v for v in history['verdicts'] if v['item_key'] == body['item_key']]) == 2
    status, headers, export = call(lab, 'GET', '/api/verdicts/export')
    assert status == 200 and 'attachment' in headers['Content-Disposition']
    assert all(json.loads(line)['id'] for line in export.decode().splitlines())


def test_verdict_on_a_production_only_item_and_the_daily_summary(lab):
    cid, detail = _task_target(lab)
    removed = next(p for p in detail['pairs']['tasks'] if p['state'] == 'removed')
    status, _, data = call(
        lab,
        'POST',
        '/api/verdicts',
        {'run_id': RUN, 'conversation_id': cid, 'item_kind': 'task', 'item_key': removed['key'], 'mark': 'bad'},
    )
    assert status == 201
    assert json.loads(data)['verdict']['item_snapshot']['side'] == 'production'
    _, day = get_json(lab, f'/api/runs/{RUN}/day')
    status, _, data = call(
        lab,
        'POST',
        '/api/verdicts',
        {'run_id': RUN, 'item_kind': 'daily_summary', 'item_key': day['daily_summary']['key'], 'mark': 'good'},
    )
    assert status == 201 and json.loads(data)['verdict']['conversation_id'] is None


@pytest.mark.parametrize(
    'patch,expected',
    [
        ({'mark': 'meh'}, 400),
        ({'item_kind': 'vibes'}, 400),
        ({'note': 'x' * 5000}, 400),
        ({'item_key': content_key('task', 'never said')}, 404),
        ({'run_id': 'no-such-run'}, 404),
        ({'run_id': '../runs'}, 404),
        ({'conversation_id': '../../etc'}, 404),
    ],
)
def test_verdict_validation(lab, patch, expected):
    cid, detail = _task_target(lab)
    body = {
        'run_id': RUN,
        'conversation_id': cid,
        'item_kind': 'task',
        'item_key': detail['pairs']['tasks'][0]['key'],
        'mark': 'good',
        **patch,
    }
    assert call(lab, 'POST', '/api/verdicts', body)[0] == expected


def test_verdict_write_guards(lab):
    cid, detail = _task_target(lab)
    body = json.dumps(
        {'run_id': RUN, 'conversation_id': cid, 'item_kind': 'task', 'item_key': 'k', 'mark': 'good'}
    ).encode()
    assert call(lab, 'POST', '/api/verdicts', body, {'Content-Type': 'text/plain'})[0] == 415
    json_hdr = {'Content-Type': 'application/json'}
    assert call(lab, 'POST', '/api/verdicts', body, {**json_hdr, 'Origin': 'http://evil.example'})[0] == 403
    assert call(lab, 'POST', '/api/verdicts', body, {**json_hdr, 'Sec-Fetch-Site': 'cross-site'})[0] == 403
    assert call(lab, 'POST', '/api/verdicts', b'{' * (server.MAX_BODY + 1), json_hdr)[0] == 413
    assert call(lab, 'POST', '/api/verdicts', b'{not json', json_hdr)[0] == 400
    assert call(lab, 'POST', '/api/runs', body, json_hdr)[0] == 404


def test_verdict_root_is_never_inside_the_store(lab):
    store = lab['base'] / 'store'
    assert not any(p.name == 'verdicts.jsonl' for p in store.rglob('*'))
    assert os.path.commonpath([lab['base'] / 'verdicts', store]) != str(store)


# ---- pairing -------------------------------------------------------------------------------


def test_pair_items_prefers_exact_keys_then_near_matches():
    def task(text):
        return {'key': content_key('task', text), 'description': text}

    replay = [task('Pay the invoice'), task('Buy fennel and saffron for Sunday'), task('Call the mill')]
    production = [task('Buy fennel and saffron for the Sunday stew'), task('Pay the invoice'), task('Water plants')]
    pairs = pair_items(replay, production, task_key, lambda t: t['description'])
    by_state = {p['state']: p for p in pairs}
    assert [p['state'] for p in pairs] == ['same', 'changed', 'added', 'removed']
    assert by_state['changed']['baseline']['description'].endswith('stew')
    assert by_state['removed']['baseline']['description'] == 'Water plants'
