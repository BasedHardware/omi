"""Hermetic v3 day through the CLI: add-day (v3 export) -> run (v3 picked by the overlay) -> baseline -> inspector.

Synthetic snapshot only; the v3 builder is the ``fake`` stand-in behind the real LLM proxy, so this
proves pipeline selection, the v3 store shape, pairing by recording and the inspector API, not
product fidelity (``v3/smoke.py`` runs the real v3 code on the local stack).
"""

import http.client
import json

import pytest

from testing.pipeline_lab import cli
from testing.pipeline_lab.inspector import server
from testing.pipeline_lab.llm_proxy.fake_upstream import FakeUpstream
from testing.pipeline_lab.seed.synthetic import write_synthetic_snapshot

DAY = '2026-03-14'


@pytest.fixture()
def lab(tmp_path, monkeypatch):
    root, verdicts = tmp_path / 'store', tmp_path / 'verdicts'
    monkeypatch.setenv('OMI_PIPELINE_LAB_ROOT', str(root))
    monkeypatch.setenv('OMI_PIPELINE_LAB_VERDICTS', str(verdicts))
    upstream = FakeUpstream().start()
    overlays = {}
    for name, payload in (
        ('v3', {'name': 'v3-on', 'env': {'CONVERSATIONS_V3': 'on'}}),
        ('classic', {'name': 'classic', 'env': {'CONVERSATIONS_V3': 'on'}, 'model_config': {'pipeline': 'classic'}}),
    ):
        path = tmp_path / f'{name}.json'
        path.write_text(json.dumps(payload))
        overlays[name] = path
    yield {
        'root': root,
        'verdicts': verdicts,
        'snap': write_synthetic_snapshot(tmp_path / 'snap', day=DAY, v3=True),
        'up': upstream,
        'overlays': overlays,
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


def run_day(capsys, lab, overlay):
    return run_cli(
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
        '--overlay',
        str(lab['overlays'][overlay]),
        '--llm-upstream',
        lab['up'].url,
        '--budget-usd',
        '1',
    )


@pytest.mark.slow  # a whole v3 day replay; over the fast-unit CPU limit on CI runners
def test_v3_day_runs_by_default_when_the_overlay_turns_v3_on(lab, capsys):
    code, added = run_cli(
        capsys, 'corpus', 'add-day', '--snapshot', str(lab['snap']), '--date', DAY, '--timezone', 'UTC'
    )
    assert code == 0, added
    assert added['v3']['recordings'] == 5 and added['v3']['v3_conversations'] == 3

    code, run = run_day(capsys, lab, 'v3')
    assert code == 0, run
    assert run['status'] == 'complete' and run['pipeline'] == 'v3'
    run_dir = lab['root'] / 'runs' / run['run_id']
    conversations = [json.loads(p.read_text()) for p in sorted((run_dir / 'conversations').glob('*.json'))]
    by_recordings = {tuple(c['recordings']): c for c in conversations}
    # the stand-in cuts stretches at 5 min of silence: rec-a and rec-b share one, rec-c is alone
    assert set(by_recordings) == {('rec-a', 'rec-b'), ('rec-c',)}
    seeds = by_recordings[('rec-a', 'rec-b')]
    assert seeds['lane'] == 'v3' and seeds['baseline_ids'] == ['v3-seeds', 'v3-water']
    assert seeds['baseline_id'] in ('v3-seeds', 'v3-water') and seeds['llm_call_ids']
    assert by_recordings[('rec-c',)]['baseline_id'] == 'v3-festival'
    assert by_recordings[('rec-c',)]['v3']['visible'] is True
    calls = [json.loads(line) for line in (run_dir / 'llm_calls.jsonl').read_text().splitlines()]
    assert {c['stage'] for c in calls} == {'v3_outline'} and all(c['conversation_id'] for c in calls)
    driver = json.loads((run_dir / 'v3_driver.json').read_text())
    assert driver['plan']['arrivals'] == 3 and driver['plan']['skipped'] == {'deleted': 1, 'in_progress_no_speech': 1}
    baseline = json.loads((run_dir / 'baseline.json').read_text())
    assert {e['baseline_id'] for e in baseline['conversations'] if e['baseline_id']} >= {'v3-festival'}
    # Production split rec-a/rec-b in two; the second production row shares recordings with the replay.
    merged = [e for e in baseline['conversations'] if e['status'] == 'merged']
    assert len(merged) == 1 and merged[0]['merged_into'] == seeds['id']
    assert not any(e['status'] == 'missing' for e in baseline['conversations'])

    srv = server.make_server(lab['root'], lab['verdicts'])
    stop = server.serve_in_thread(srv)
    try:
        port = srv.server_address[1]
        status, overview = get(port, f'/api/runs/{run["run_id"]}')
        assert status == 200 and overview['run']['pipeline'] == 'v3'
        rows = {tuple(sorted(b['id'] for b in r['baseline'] if b)): r for r in overview['conversations']}
        festival = rows[('v3-festival',)]
        assert festival['hidden'] is False and festival['recordings'] == 1
        assert {c['id'] for g in overview['groups'] for c in g['production']} == {'v3-seeds', 'v3-water', 'v3-festival'}
        merge = next(g for g in overview['groups'] if g['kind'] == 'merge')
        assert [c['id'] for c in merge['production']] == ['v3-seeds', 'v3-water'] and merge['marker'] == '⇉'
        status, detail = get(port, f'/api/runs/{run["run_id"]}/conversations/{festival["id"]}')
        assert status == 200 and detail['baseline']['id'] == 'v3-festival'
        assert detail['baseline']['structured']['sections'] and detail['replay']['recordings'] == ['rec-c']
        merged = rows[('v3-seeds', 'v3-water')]
        status, detail = get(port, f'/api/runs/{run["run_id"]}/conversations/{merged["id"]}')
        assert detail['baseline']['merged_ids'] == ['v3-seeds', 'v3-water']
        assert detail['baseline']['recordings'] == ['rec-a', 'rec-b']
    finally:
        stop()

    # the classic chain stays available on the same day
    code, classic = run_day(capsys, lab, 'classic')
    assert code == 0, classic
    assert classic['pipeline'] == 'classic'
    classic_dir = lab['root'] / 'runs' / classic['run_id']
    assert not (classic_dir / 'v3_driver.json').exists()
