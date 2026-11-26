"""LOCAL-STACK SMOKE (not a unit test): the real conversations-v3 code on a synthetic day.

    corpus add-day (synthetic snapshot with a v3 export) -> overlay from-runtime-env (backend-sync)
    -> run --in-place --engine product --from-stage discard  (v3 picked by the overlay)
    -> baseline.json -> inspector API

Recordings go through the product's admission, durable finalization and ``recording_short_path``;
named Cloud Tasks run in process; ``service.reconcile`` outlines (the fake upstream answers the
outline prompt), plans, commits and drains notes through ``process_conversation``. Nothing leaves
the host. Prints one JSON report; exit 0 when the v3 builder committed at least one conversation
from the recordings and the inspector served it.

    FS_PORT=8296 REDIS_PORT=6392 SMOKE_MODULE=testing.pipeline_lab.v3.smoke \\
      backend/testing/pipeline_lab/stack/run_chain_smoke.sh
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from testing.pipeline_lab.stack.chain_smoke import DAY, _cli, _get


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m testing.pipeline_lab.v3.smoke')
    parser.add_argument('--keep', help='store root to write (default: a fresh temp dir)')
    parser.add_argument('--ref', help='run a pinned arm of this ref (e.g. the production release) instead of in place')
    parser.add_argument('--overlay', help='use this overlay file instead of building one from the runtime env')
    args = parser.parse_args(argv)
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        print(json.dumps({'ok': False, 'error': 'FIRESTORE_EMULATOR_HOST must name a loopback emulator'}))
        return 1
    base = Path(args.keep or tempfile.mkdtemp(prefix='plab-v3-smoke-'))
    os.environ.update(
        {
            'OMI_PIPELINE_LAB_ROOT': str(base / 'store'),
            'OMI_PIPELINE_LAB_VERDICTS': str(base / 'verdicts'),
            'OMI_PIPELINE_LAB_EMBEDDER': 'fake',
        }
    )
    from testing.pipeline_lab.inspector import server
    from testing.pipeline_lab.llm_proxy.fake_upstream import FakeUpstream
    from testing.pipeline_lab.seed.synthetic import write_synthetic_snapshot

    report: dict[str, Any] = {'root': str(base), 'firestore': host, 'redis': os.environ.get('OMI_PIPELINE_LAB_REDIS')}
    runtime_env: list[str] = []
    if args.ref:
        code, arm = _cli('worktree', 'ensure', args.ref)
        if code != 0 or not arm:
            print(json.dumps({'ok': False, 'error': f'worktree ensure failed: {arm}'}))
            return 1
        report['arm'] = {'sha': arm.get('sha'), 'backend_tree': arm.get('backend_tree')}
        runtime_env = ['--runtime-env', str(Path(arm['path']) / 'backend' / 'deploy' / 'runtime_env.yaml')]
    if args.overlay:
        built = {'service': 'given', 'source': 'file'}
        from testing.pipeline_lab.store import private_write_text

        private_write_text(base / 'overlay.json', Path(args.overlay).read_text())  # may name the owner uid
    else:
        code, built = _cli('overlay', 'from-runtime-env', *runtime_env, '--out', str(base / 'overlay.json'))
    report['overlay'] = (
        {k: built.get(k) for k in ('service', 'kept', 'cohorts', 'pinned_static', 'unresolved', 'v3')}
        if built
        else code
    )
    snapshot = write_synthetic_snapshot(base / 'snapshot', day=DAY, v3=True)
    code, added = _cli('corpus', 'add-day', '--snapshot', str(snapshot), '--date', DAY, '--timezone', 'UTC')
    report['add_day'] = {'code': code, 'v3': (added or {}).get('v3')}
    upstream = FakeUpstream().start()
    try:
        code, run = _cli(
            'run',
            '--day',
            DAY,
            *(['--ref', args.ref] if args.ref else ['--ref', 'HEAD', '--in-place']),
            '--engine',
            'product',
            '--from-stage',
            'discard',
            '--llm-upstream',
            upstream.url,
            '--budget-usd',
            '1',
            '--overlay',
            str(base / 'overlay.json'),
        )
    finally:
        upstream.stop()
    run = run or {}
    report['run'] = {
        'code': code,
        'status': run.get('status'),
        'pipeline': run.get('pipeline'),
        'error': run.get('error'),
        'spend_usd': run.get('spend_usd'),
        'stages': {name: state.get('status') for name, state in (run.get('stages') or {}).items()},
        'timings': run.get('timings'),
        'warnings': run.get('warnings'),
    }
    ok = False
    if run.get('run_id'):
        run_dir = base / 'store' / 'runs' / run['run_id']
        driver = json.loads((run_dir / 'v3_driver.json').read_text()) if (run_dir / 'v3_driver.json').exists() else {}
        report['driver'] = {
            'plan': driver.get('plan'),
            'summary': driver.get('summary'),
            'tasks': driver.get('tasks'),
            'events': [
                {k: e.get(k) for k in ('at', 'kind', 'ref', 'outcome', 'error', 'detail')}
                for e in driver.get('events') or []
            ],
            'warnings': driver.get('warnings'),
        }
        conversations = [json.loads(p.read_text()) for p in sorted((run_dir / 'conversations').glob('*.json'))]
        report['conversations'] = [
            {
                'recordings': c.get('recordings'),
                'title': (c.get('structured') or {}).get('title'),
                'baseline_id': c.get('baseline_id'),
                'v3': {k: (c.get('v3') or {}).get(k) for k in ('visible', 'home_hidden_reason', 'kind', 'status')},
                'tasks': len(c.get('action_items') or []),
                'memories': len(c.get('memories') or []),
                'calls': len(c.get('llm_call_ids') or []),
            }
            for c in conversations
        ]
        fate = (
            json.loads((run_dir / 'v3_recordings.json').read_text())
            if (run_dir / 'v3_recordings.json').exists()
            else {}
        )
        report['recordings'] = {k: fate.get(k) for k in ('recordings', 'unclaimed', 'still_pending')}
        calls = _jsonl(run_dir / 'llm_calls.jsonl')
        report['llm_calls'] = {
            'total': len(calls),
            'by_stage': {s: sum(1 for c in calls if c.get('stage') == s) for s in {c.get('stage') for c in calls}},
            'attributed': sum(1 for c in calls if c.get('conversation_id')),
            'features': sorted({str(c.get('feature')) for c in calls}),
            'errors': sorted({str(c.get('error')) for c in calls if c.get('error')}),
        }
        decisions = _jsonl(run_dir / 'decisions.jsonl')
        report['unpinned'] = sorted({d['name'] for d in decisions if d.get('source') == 'unpinned'})
        report['admission'] = [d.get('mode') for d in decisions if d.get('name') == 'conversations_v3_admission']
        report['network_refusals'] = [
            {k: d.get(k) for k in ('mode', 'host', 'port', 'kind')}
            for d in decisions
            if d.get('name') == 'network_refused'
        ]
        report['baseline'] = (
            json.loads((run_dir / 'baseline.json').read_text()).get('counts')
            if (run_dir / 'baseline.json').exists()
            else None
        )
        for name in ('chain_errors.log', 'processing_errors.log'):
            if (run_dir / name).exists():
                report[name] = (run_dir / name).read_text()[-4000:]
        srv = server.make_server(base / 'store', base / 'verdicts')
        stop = server.serve_in_thread(srv)
        try:
            port = srv.server_address[1]
            status, overview = _get(port, f'/api/runs/{run["run_id"]}')
            rows = (overview or {}).get('conversations') or []
            report['inspector'] = {
                'overview': status,
                'pipeline': ((overview or {}).get('run') or {}).get('pipeline'),
                'rows': [(r.get('status'), r.get('hidden'), r.get('recordings')) for r in rows],
            }
            replay_rows = [r for r in rows if r.get('kind') == 'replay']
            if replay_rows:
                status, detail = _get(port, f'/api/runs/{run["run_id"]}/conversations/{replay_rows[0]["id"]}')
                report['inspector']['detail'] = status
        finally:
            stop()
        ok = bool(conversations) and report.get('inspector', {}).get('detail') == 200 and run.get('pipeline') == 'v3'
    report['ok'] = ok
    print(json.dumps(report, indent=1, default=str))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
