"""Hermetic end to end through the CLI: corpus add-day -> run (fake engine, real proxy) -> baseline -> inspector.

Synthetic snapshot only. The LLM upstream is the lab's scripted fake behind the real record/replay
proxy; the chain uses the ``fake`` engine (no Firestore emulator), so this proves the lab's plumbing,
not product fidelity (that is ``stack/chain_smoke.py`` on the local stack).
"""

import http.client
import io
import json
import os

import pytest

from testing.pipeline_lab import cli
from testing.pipeline_lab.inspector import server
from testing.pipeline_lab.llm_proxy.fake_upstream import FakeUpstream
from testing.pipeline_lab.llm_proxy.server import _Handler
from testing.pipeline_lab.seed.synthetic import SYNTHETIC_SOURCE_UID, write_synthetic_snapshot

DAY = '2026-03-14'


@pytest.fixture()
def lab(tmp_path, monkeypatch):
    root, verdicts = tmp_path / 'store', tmp_path / 'verdicts'
    monkeypatch.setenv('OMI_PIPELINE_LAB_ROOT', str(root))
    monkeypatch.setenv('OMI_PIPELINE_LAB_VERDICTS', str(verdicts))

    handle_post = _Handler.do_POST

    def respond_after_logging(handler):
        # The fake chain runs in a subprocess. Release its non-streaming HTTP
        # response only after the proxy handler finishes appending the call.
        socket_writer = handler.wfile
        with io.BytesIO() as response:
            handler.wfile = response
            try:
                handle_post(handler)
            finally:
                handler.wfile = socket_writer
            socket_writer.write(response.getvalue())

    monkeypatch.setattr(_Handler, 'do_POST', respond_after_logging)
    upstream = FakeUpstream().start()
    yield {
        'root': root,
        'verdicts': verdicts,
        'snap': write_synthetic_snapshot(tmp_path / 'snap', day=DAY),
        'up': upstream,
    }
    upstream.stop()


def run_cli(capsys, *argv):
    code = cli.main(['--json', *argv])
    out = capsys.readouterr().out.strip().splitlines()
    return code, json.loads(out[-1]) if out else None


def get(port, path):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    conn.request('GET', path)
    res = conn.getresponse()
    body = res.read()
    conn.close()
    return res.status, json.loads(body) if body else None


def post(port, path, payload):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    conn.request('POST', path, body=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    res = conn.getresponse()
    body = res.read()
    conn.close()
    return res.status, json.loads(body) if body else None


def test_add_day_run_baseline_and_inspector(lab, capsys):
    root = lab['root']
    code, added = run_cli(
        capsys, 'corpus', 'add-day', '--snapshot', str(lab['snap']), '--date', DAY, '--timezone', 'UTC'
    )
    assert code == 0, added
    assert added['conversations'] == 3 and added['start_state']['conversations'] == 6
    day_dir = root / 'corpus' / DAY
    for name in (
        'day.json',
        'timeline.json',
        'baseline/conversations.jsonl',
        'baseline/raw_conversations.jsonl',
        'baseline/daily_summary.json',
        'start_state/meta.json',
    ):
        assert (day_dir / name).is_file(), name
    contract_row = json.loads((day_dir / 'baseline/conversations.jsonl').read_text().splitlines()[0])
    assert {'segments', 'structured', 'action_items', 'lane'} <= set(contract_row)
    assert 'transcript_segments' in (day_dir / 'baseline/raw_conversations.jsonl').read_text()
    for path in root.rglob('*'):  # the source uid never reaches the store
        if path.is_file():
            assert SYNTHETIC_SOURCE_UID not in path.read_text(errors='ignore'), path
            assert oct(path.stat().st_mode & 0o077) == '0o0', path

    code, run = run_cli(
        capsys,
        'run',
        '--day',
        DAY,
        '--ref',
        'HEAD',
        '--in-place',
        '--engine',
        'fake',
        '--from-stage',
        'discard',
        '--llm-upstream',
        lab['up'].url,
        '--budget-usd',
        '1',
    )
    assert code == 0, run
    assert run['status'] == 'complete' and run['commit'] and run['stt'] == 'stored production transcripts'
    assert {s: run['stages'][s]['status'] for s in ('ingest', 'transcribe', 'boundaries', 'speakers')} == dict.fromkeys(
        ('ingest', 'transcribe', 'boundaries', 'speakers'), 'skipped'
    )
    assert all(run['stages'][s]['status'] == 'complete' for s in ('discard', 'notes', 'tasks', 'chat_index'))
    assert run['spend_usd'] > 0
    run_dir = root / 'runs' / run['run_id']
    calls = [json.loads(line) for line in (run_dir / 'llm_calls.jsonl').read_text().splitlines()]
    notes_calls = [c for c in calls if c['stage'] == 'notes']
    assert len(notes_calls) == 3 and all(c['conversation_id'] for c in notes_calls)
    assert [c['stage'] for c in calls].count('daily_summary') == 1
    # attribution headers are the proxy's, never forwarded upstream (RULINGS 8)
    assert lab['up'].requests and not any(
        k.startswith('x-pipeline-lab-') for r in lab['up'].requests for k in r['headers']
    )
    conversations = list((run_dir / 'conversations').glob('*.json'))
    assert len(conversations) == len(notes_calls)
    for path in conversations:
        conversation = json.loads(path.read_text())
        assert conversation['baseline_id'] == conversation['id'] and conversation['llm_call_ids']
    baseline = json.loads((run_dir / 'baseline.json').read_text())
    assert sum(baseline['counts'].values()) == 3
    day_file = json.loads((run_dir / 'day.json').read_text())
    assert set(day_file['daily_summary']) >= {'title', 'overview', 'highlights'}

    # a second run is served from the proxy cache: same calls, no spend
    code, again = run_cli(
        capsys,
        'run',
        '--day',
        DAY,
        '--ref',
        'HEAD',
        '--in-place',
        '--engine',
        'fake',
        '--from-stage',
        'discard',
        '--llm-upstream',
        lab['up'].url,
        '--llm-mode',
        'replay',
    )
    assert code == 0, again
    assert again['spend_usd'] == 0
    second = [
        json.loads(line) for line in (root / 'runs' / again['run_id'] / 'llm_calls.jsonl').read_text().splitlines()
    ]
    assert len(second) == len(calls) and all(c['cache_hit'] for c in second)

    code, shown = run_cli(capsys, 'show', run['run_id'])
    assert code == 0 and shown['conversations']['total'] == 3 and shown['llm_calls']['total'] == len(calls)

    srv = server.make_server(root, lab['verdicts'])
    stop = server.serve_in_thread(srv)
    try:
        port = srv.server_address[1]
        status, runs = get(port, '/api/runs')
        assert status == 200 and {r['run_id'] for r in runs['runs']} >= {run['run_id'], again['run_id']}
        status, overview = get(port, f'/api/runs/{run["run_id"]}')
        assert status == 200 and overview['run']['engine'] == 'fake'
        rows = overview['conversations']
        assert len(rows) == 3 and all(r['status'] in ('same', 'changed', 'discard flipped') for r in rows)
        cid = rows[0]['id']
        status, detail = get(port, f'/api/runs/{run["run_id"]}/conversations/{cid}')
        assert status == 200 and detail['baseline'] is not None
        assert {'summary', 'tasks', 'memories', 'pushes'} <= set(detail['pairs'])
        assert detail['llm_calls'] and detail['status'] == rows[0]['status']
        status, _ = get(port, f'/api/runs/{run["run_id"]}/day')
        assert status == 200
        status, body = post(
            port,
            '/api/verdicts',
            {
                'run_id': run['run_id'],
                'conversation_id': cid,
                'item_kind': 'summary',
                'item_key': detail['keys']['replay']['summary'],
                'mark': 'good',
            },
        )
        assert status == 201, body
        assert body['verdict']['conversation_id'] == detail['replay']['baseline_id']
    finally:
        stop()

    code, listed = run_cli(capsys, 'verdicts', 'list', '--latest')
    assert code == 0
    assert os.path.exists(lab['verdicts'] / 'verdicts.jsonl')


def test_stage_registry_covers_every_stage_and_tool(lab, capsys):
    code, described = run_cli(capsys, 'stages')
    assert code == 0
    assert all(described['stages'][stage] for stage in described['stages'])
    assert all(described['tools'].values())
