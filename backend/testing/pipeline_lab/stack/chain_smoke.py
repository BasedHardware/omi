"""LOCAL-STACK SMOKE (not a unit test): the real product chain on a synthetic day.

Runs the CLI exactly as the lead would, against a local Firestore emulator and Redis, with the
lab's scripted fake LLM upstream behind the real proxy and the fake embedder:

    corpus add-day (synthetic snapshot) -> run --in-place --engine product --from-stage discard
    -> baseline.json -> inspector API (day overview + one conversation)

Nothing leaves the host: the network guard admits loopback peers only, the LLM upstream is the
fake, Typesense is absent unless ``OMI_PIPELINE_LAB_TYPESENSE`` points at one (product dual-writes
fail open). Synthetic data only. Prints one JSON report; exit 0 when the chain finalized at least
one conversation and the inspector served it, else 1.

    # with a Firestore emulator and redis-server already listening on loopback ports:
    FIRESTORE_EMULATOR_HOST=127.0.0.1:8295 OMI_PIPELINE_LAB_REDIS=127.0.0.1:6391 \\
      python -m testing.pipeline_lab.stack.chain_smoke [--keep DIR]

``testing/pipeline_lab/stack/run_chain_smoke.sh`` starts both on non-default ports, runs this,
and stops what it started by PID.
"""

from __future__ import annotations

import argparse
import http.client
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

DAY = '2026-03-14'


def _cli(*argv: str) -> tuple[int, Any]:
    from testing.pipeline_lab import cli

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = cli.main(['--json', *argv])
    lines = buffer.getvalue().strip().splitlines()
    return code, json.loads(lines[-1]) if lines else None


def _get(port: int, path: str) -> tuple[int, Any]:
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=30)
    conn.request('GET', path)
    res = conn.getresponse()
    body = res.read()
    conn.close()
    return res.status, json.loads(body) if body else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m testing.pipeline_lab.stack.chain_smoke')
    parser.add_argument('--keep', help='store root to write (default: a fresh temp dir)')
    args = parser.parse_args(argv)
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        print(json.dumps({'ok': False, 'error': 'FIRESTORE_EMULATOR_HOST must name a loopback emulator'}))
        return 1
    base = Path(args.keep or tempfile.mkdtemp(prefix='plab-chain-smoke-'))
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
    # Production flags from this checkout's runtime env (the lab clears the process env otherwise).
    code, built = _cli('overlay', 'from-runtime-env', '--out', str(base / 'overlay.json'))
    report['overlay'] = {k: built.get(k) for k in ('kept', 'cohorts', 'unresolved', 'dropped')} if built else code
    snapshot = write_synthetic_snapshot(base / 'snapshot', day=DAY)
    code, added = _cli('corpus', 'add-day', '--snapshot', str(snapshot), '--date', DAY, '--timezone', 'UTC')
    report['add_day'] = {'code': code, 'conversations': (added or {}).get('conversations')}
    upstream = FakeUpstream().start()
    try:
        code, run = _cli(
            'run',
            '--day',
            DAY,
            '--ref',
            'HEAD',
            '--in-place',
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
        'error': run.get('error'),
        'spend_usd': run.get('spend_usd'),
        'stages': {name: state.get('status') for name, state in (run.get('stages') or {}).items()},
        'timings': run.get('timings'),
        'warnings': run.get('warnings'),
    }
    report['upstream_paths'] = sorted({r['path'] for r in upstream.requests})
    ok = False
    if run.get('run_id'):
        run_dir = base / 'store' / 'runs' / run['run_id']
        chain = json.loads((run_dir / 'chain.json').read_text()) if (run_dir / 'chain.json').exists() else {}
        report['chain'] = {
            'summary': chain.get('summary'),
            'conversations': [
                {k: c.get(k) for k in ('conversation_id', 'status', 'disposition', 'error', 'background_failures')}
                for c in chain.get('conversations') or []
            ],
        }
        calls = (
            [json.loads(line) for line in (run_dir / 'llm_calls.jsonl').read_text().splitlines()]
            if (run_dir / 'llm_calls.jsonl').exists()
            else []
        )
        report['llm_calls'] = {
            'total': len(calls),
            'by_stage': {s: sum(1 for c in calls if c.get('stage') == s) for s in {c.get('stage') for c in calls}},
            'attributed': sum(1 for c in calls if c.get('conversation_id')),
            'features': sorted({str(c.get('feature')) for c in calls}),
            'errors': sorted({str(c.get('error')) for c in calls if c.get('error')}),
        }
        decisions = (
            [json.loads(line) for line in (run_dir / 'decisions.jsonl').read_text().splitlines()]
            if (run_dir / 'decisions.jsonl').exists()
            else []
        )
        report['network_refusals'] = [
            {k: d.get(k) for k in ('mode', 'host', 'port', 'kind')}
            for d in decisions
            if d.get('name') == 'network_refused'
        ]
        for name in ('baseline.json', 'day.json', 'chain_entry.json'):
            report[name] = (run_dir / name).exists()
        if (run_dir / 'chain_errors.log').exists():
            report['chain_errors_tail'] = (run_dir / 'chain_errors.log').read_text()[-3000:]
        srv = server.make_server(base / 'store', base / 'verdicts')
        stop = server.serve_in_thread(srv)
        try:
            port = srv.server_address[1]
            status, overview = _get(port, f'/api/runs/{run["run_id"]}')
            rows = (overview or {}).get('conversations') or []
            report['inspector'] = {'overview': status, 'rows': [(r.get('id'), r.get('status')) for r in rows]}
            if rows:
                status, detail = _get(port, f'/api/runs/{run["run_id"]}/conversations/{rows[0]["id"]}')
                report['inspector']['detail'] = status
                report['inspector']['pairs'] = sorted((detail or {}).get('pairs') or {})
                report['inspector']['title'] = ((detail or {}).get('replay') or {}).get('structured', {}).get('title')
        finally:
            stop()
        finalized = sum(1 for c in report['chain']['conversations'] if c.get('status') == 'ok')
        ok = finalized > 0 and report.get('inspector', {}).get('detail') == 200
    report['ok'] = ok
    print(json.dumps(report, indent=1, default=str))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
