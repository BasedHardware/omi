"""Cut a whole day with one ref's real v3 outline, planner and visibility code, without Firestore.

    python -m testing.pipeline_lab.ideal.planpass --root ROOT --day DAY --backend <ref worktree>/backend \\
        --upstream http://127.0.0.1:19083 --token-file FILE [--env K=V ...] [--label NAME]

The question this answers: what Home would this ref build from the day's recordings once every stretch
is finished? It runs the product's own ``outline.stretches`` / ``messages`` / ``parse``,
``planner.windows`` and ``visibility.project`` (imported from ``--backend``) over the corpus day's
recordings, with real outline calls through the lab proxy (recorded, cached, capped). It skips what
needs Firestore: the background-sources block and stored wearer-recognition evidence (only
``is_user`` counts), the incremental arrival order, finished-window locking and notes. So it isolates
the cutting policy; the same skips apply to every ref compared.

Output: ``runs/<id>/conversations/*.json`` in contract shape, scored like any replay
(``ideal.score --run``).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from typing import Sequence

CHILD = r'''
import json, os, sys, urllib.request
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.environ['PLANPASS_BACKEND'])
import inspect
from utils.conversations.v3 import outline, planner, policy, visibility
from config import conversations_v3 as cfg

args = json.load(sys.stdin)
recordings = {r['id']: r for r in args['recordings']}
for r in recordings.values():
    for k in ('started_at', 'finished_at', 'recorded_start'):
        if isinstance(r.get(k), str):
            r[k] = outline.utc(r[k])
now = outline.utc(args['now'])
eligible = [r for r in recordings.values() if policy.builder_eligible(r)]
sitdown = bool(getattr(cfg, 'sitdown_enabled', lambda: False)())
kwargs = {}
if 'silence' in inspect.signature(outline.stretches).parameters:
    seconds = getattr(cfg, 'sitdown_silence_seconds', lambda: 900)() if sitdown else outline.SILENCE.total_seconds()
    kwargs['silence'] = timedelta(seconds=seconds)
cohesion = cfg.stretch_cohesion_enabled()
msg_kw = {'cohesion': cohesion}
if hasattr(cfg, 'boundary_seconds'):  # #25794: silence gap and lock delay as settings
    gap, lock = cfg.boundary_seconds(cohesion=cohesion)
    kwargs = {'silence_gap': timedelta(seconds=gap), 'lock_delay': timedelta(seconds=lock)}
    if 'silence_gap' in inspect.signature(outline.messages).parameters:
        msg_kw['silence_gap'] = timedelta(seconds=gap)
if hasattr(cfg, 'max_window_seconds'):
    kwargs['max_window'] = timedelta(seconds=cfg.max_window_seconds())
groups = outline.stretches(eligible, now, **kwargs)
if 'sitdown' in inspect.signature(outline.messages).parameters:
    msg_kw['sitdown'] = sitdown


def ask(messages, tag):
    roles = {'system': 'system', 'human': 'user', 'ai': 'assistant'}
    body = {
        'model': 'omi:auto:conversation-v3-outline',
        'messages': [{'role': roles[r], 'content': c} for r, c in messages],
        'reasoning_effort': 'none',
        'response_format': {'type': 'json_object'},
        'stream': False,
    }
    req = urllib.request.Request(
        args['proxy'] + '/v1/chat/completions',
        data=json.dumps(body).encode(),
        headers={
            'Content-Type': 'application/json',
            'X-Omi-Service-Caller': 'backend',
            'X-Omi-LLM-Feature': 'conversation_v3_outline',
            'X-Pipeline-Lab-Stage': 'planpass',
            'X-Pipeline-Lab-Conversation': tag,
        },
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for attempt in range(3):
        try:
            with opener.open(req, timeout=120) as response:
                return json.loads(response.read())['choices'][0]['message']['content'] or ''
        except Exception:
            if attempt == 2:
                raise


outlines, failed = [], 0
for index, group in enumerate(groups):
    messages = outline.messages(group, timezone.utc, **msg_kw)
    if outlines:
        previous = outlines[-1][-1]
        messages.append(('human', 'Preceding conversation: ' + previous['title'] + '\n' + previous['line']))
    try:
        entries = outline.parse(ask(messages, f'stretch-{index:03d}'), group)
    except Exception:
        failed += 1
        entries = outline.fallback(group)
    outlines.append(entries)
win_kw = {'cohesion': cohesion}
if 'sitdown' in inspect.signature(planner.windows).parameters:
    win_kw['sitdown'] = sitdown
if 'silence_gap' in inspect.signature(planner.windows).parameters and 'silence_gap' in kwargs:
    win_kw['silence_gap'] = kwargs['silence_gap']
windows = planner.windows(groups, outlines, **win_kw)
out = []
for w in windows:
    lines = w['lines']
    ids = {line['conversation_id'] for line in lines}
    words = w.get('_stretch_words', sum(len(line['text'].split()) for line in lines))
    kind, hidden, reason = visibility.project(
        w['kind'], recordings, ids, words=words, finished=w['finished'], manual_end=bool(w.get('manual_end'))
    )
    start = lines[0]['start']
    out.append({
        'id': f'pp-{len(out):04d}',
        'started_at': start.isoformat(),
        'finished_at': max(line['end'] for line in lines).isoformat(),
        'segments': [
            {'text': line['text'], 'start': (line['start'] - start).total_seconds(),
             'end': (line['end'] - start).total_seconds()}
            for line in lines
        ],
        'structured': {'title': w.get('title') or '', 'emoji': w.get('emoji') or ''},
        'v3': {'kind': kind, 'home_hidden': hidden, 'visible': not hidden, 'home_hidden_reason': reason},
    })
json.dump({'conversations': out, 'stretches': len(groups), 'outline_failed': failed, 'sitdown': sitdown,
           'silence_seconds': (kwargs.get('silence') or kwargs.get('silence_gap') or outline.SILENCE).total_seconds()}, sys.stdout)
'''


def main(argv: Sequence[str] | None = None) -> int:
    from testing.pipeline_lab import contracts as c
    from testing.pipeline_lab.ledger import SpendLedger
    from testing.pipeline_lab.llm_proxy.server import LlmProxy, ProxyConfig
    from testing.pipeline_lab.store import Store, atomic_write_json, ensure_private_dir, read_jsonl

    parser = argparse.ArgumentParser(prog='python -m testing.pipeline_lab.ideal.planpass')
    parser.add_argument('--root', required=True)
    parser.add_argument('--day', required=True)
    parser.add_argument('--backend', required=True, help='the ref worktree backend directory')
    parser.add_argument('--upstream', required=True)
    parser.add_argument('--token-file', required=True)
    parser.add_argument('--env', action='append', default=[], help='K=V for the product code (switches)')
    parser.add_argument('--label', default='planpass')
    parser.add_argument('--budget-usd', type=float, default=1.0)
    parser.add_argument('--mode', default='record', help='proxy mode; refresh re-asks the model (repeat runs)')
    args = parser.parse_args(argv)

    root = ensure_private_dir(Path(args.root))
    day = json.loads((root / 'corpus' / args.day / 'day.json').read_text(encoding='utf-8'))
    recordings = list(read_jsonl(root / 'corpus' / args.day / 'v3' / 'recordings.jsonl'))
    store = Store(root=root, verdicts_root=Path(os.devnull))
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    run_id = f'{stamp}-planpass-{args.day}-{args.label}-{secrets.token_hex(3)}'
    sha = subprocess.run(
        ['git', '-C', args.backend, 'rev-parse', 'HEAD'], capture_output=True, text=True
    ).stdout.strip()
    store.create_run(c.RunRecord(run_id=run_id, day_id=args.day, ref=f'planpass:{sha}'))
    ledger = SpendLedger(store.ledger_path(run_id), budget_usd=args.budget_usd)
    from testing.pipeline_lab.cli import read_private_value

    token = read_private_value(Path(args.token_file))  # owner-only regular file, never a link
    config = ProxyConfig(upstream=args.upstream, mode=args.mode, run_id=run_id, upstream_token=token)
    end = datetime.fromisoformat(day['window']['end'].replace('Z', '+00:00'))
    env = {k: v for k, v in os.environ.items() if not k.startswith(('GOOGLE_', 'CLOUDSDK_', 'FIRESTORE_'))}
    env.update(
        PLANPASS_BACKEND=str(Path(args.backend).resolve()),
        ENCRYPTION_SECRET=secrets.token_hex(16),  # imports need one; nothing is decrypted
        PYTHONPATH='',
    )
    for item in args.env:
        key, _, value = item.partition('=')
        env[key] = value
    with LlmProxy(config, store=store, ledger=ledger) as proxy:
        payload = json.dumps(
            {'recordings': recordings, 'now': (end.replace(microsecond=0)).isoformat(), 'proxy': proxy.url},
            default=str,
        )
        # Run from an empty directory so the product's own ``testing`` package cannot shadow anything.
        empty = root / 'private' / 'planpass-cwd'
        empty.mkdir(parents=True, exist_ok=True)
        done = subprocess.run(
            [sys.executable, '-I', '-c', CHILD], input=payload, capture_output=True, text=True, env=env, cwd=empty
        )
    if done.returncode != 0:
        print(done.stderr[-3000:], file=sys.stderr)
        return 2
    result = json.loads(done.stdout)
    run_dir = store.run_dir(run_id)
    conv_dir = ensure_private_dir(run_dir / 'conversations')
    for conv in result.pop('conversations'):
        atomic_write_json(conv_dir / f"{conv['id']}.json", conv)
    summary = {
        'run_id': run_id,
        'sha': sha,
        **result,
        'conversations': len(list(conv_dir.glob('*.json'))),
        'usd': ledger.snapshot().get('committed_usd'),
    }
    atomic_write_json(run_dir / 'planpass.json', summary)
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
