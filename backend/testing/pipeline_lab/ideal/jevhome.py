"""Prototype: let Jev make the Home call for cards another pass already cut.

    python -m testing.pipeline_lab.ideal.jevhome --root ROOT --packet DIR --cards CARDS.json \\
        --upstream http://127.0.0.1:19083 --token-file FILE [--thresholds 0.2,0.5,0.8]

For every ``conversation`` or ``voice_work`` card of an ideal-format file (an hour pass, a draft),
ask Jev the production relevance question (``utils/conversations/relevance_jev.py``,
``relevance_b1``: "would the user plausibly want to find this later?") about the card's transcript,
rendered in the shipped ``User:`` / ``Speaker N:`` form. ``media``, ``background`` and ``noise``
cards stay hidden. Writes ``jevhome.json`` (each card's probability) and one ideal-format file per
threshold, ``jevhome-<t>.json``, where a card is on Home when ``p(worth keeping) >= t``.

Production discards when ``p(not worth keeping) >= 0.80``, i.e. keeps at ``p >= 0.20``; that cut
was measured for discard, not for Home, so the threshold is swept here.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
from typing import Any, Mapping, Sequence
import urllib.request

from testing.pipeline_lab.ideal.schema import card_lines, load_lines
from utils.speakers.display import SpeakerLabeler

LANE = 'omi:auto:jev-decisions'
EXPECTED_MODEL = 'typesafe/jev-1.13'
MAX_STATE_CHARS = 24_000
QUESTION = {
    'worth_keeping': {
        'type': 'noul',
        'instructions': (
            "This is an automatically captured snippet from the user's always-on wearable. Would the user "
            'plausibly want to find this later in their memory log? Losing a real memory is much worse than '
            'keeping a bit of noise.'
        ),
        'criteria': {
            'true': (
                'it mentions anything the user could want later: a task, a name, a time, a number, a place, '
                'a plan, an open question, or a personal fact'
            ),
            'false': (
                'it is noise: filler, acknowledgments, garbled fragments, background media, or throwaway '
                'remarks with nothing to remember'
            ),
        },
    }
}
JUDGED_KINDS = ('conversation', 'voice_work')


def transcript(lines: Sequence[Mapping[str, Any]]) -> str:
    """The shipped rendering: ``User:`` for the wearer, the display authority's ``Speaker A/B/...`` for
    unnamed voices in first-appearance order, a person's name as is; joined runs."""
    labeler = SpeakerLabeler()
    out: list[str] = []
    for line in lines:
        label = line['speaker']
        if label == 'ME':
            who = 'User'
        elif label == 'S?':
            who = 'Unknown'
        elif re.match(r'^S\d+$', label):
            who = labeler.label(label)
        else:
            who = label
        if out and out[-1].startswith(who + ':'):
            out[-1] += ' ' + line['text']
        else:
            out.append(f"{who}: {line['text']}")
    return '\n\n'.join(out)


def state(text: str) -> str:
    body = f'Transcript:\n```\n{text}\n```\nWord count: {len(text.split())} words.'
    if len(body) <= MAX_STATE_CHARS:
        return body
    keep = MAX_STATE_CHARS - 24
    return body[: keep * 2 // 3] + '\n[... truncated ...]\n' + body[len(body) - (keep - keep * 2 // 3) :]


def ask(proxy_url: str, card_state: str, tag: str) -> float | None:
    body = {'model': LANE, 'state': card_state, 'questions': QUESTION}
    request = urllib.request.Request(
        proxy_url.rstrip('/') + '/v1/systemone',
        data=json.dumps(body).encode(),
        headers={
            'Content-Type': 'application/json',
            'X-Omi-Service-Caller': 'backend',
            'X-Omi-LLM-Feature': 'jev_conversation_relevance',
            'X-Pipeline-Lab-Stage': 'jevhome',
            'X-Pipeline-Lab-Conversation': tag,
        },
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=60) as response:
        raw = json.loads(response.read())
    answers = raw.get('answers') or {}
    value = (answers.get('worth_keeping') or {}).get('noul')
    return float(value) if isinstance(value, (int, float)) else None


def main(argv: Sequence[str] | None = None) -> int:
    from testing.pipeline_lab import contracts as c
    from testing.pipeline_lab.ledger import SpendLedger
    from testing.pipeline_lab.llm_proxy.server import LlmProxy, ProxyConfig
    from testing.pipeline_lab.store import Store, atomic_write_json, ensure_private_dir

    parser = argparse.ArgumentParser(prog='python -m testing.pipeline_lab.ideal.jevhome')
    parser.add_argument('--root', required=True)
    parser.add_argument('--packet', required=True)
    parser.add_argument('--cards', required=True)
    parser.add_argument('--upstream', required=True)
    parser.add_argument('--token-file', required=True)
    parser.add_argument('--thresholds', default='0.2,0.35,0.5,0.65,0.8')
    parser.add_argument('--budget-usd', type=float, default=1.0)
    args = parser.parse_args(argv)

    by_id = {x['line']: x for x in load_lines(Path(args.packet))}
    source = json.loads(Path(args.cards).read_text(encoding='utf-8'))
    store = Store(root=ensure_private_dir(Path(args.root)), verdicts_root=Path(os.devnull))
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    run_id = f'{stamp}-jevhome-{source.get("day")}-{secrets.token_hex(3)}'
    store.create_run(c.RunRecord(run_id=run_id, day_id=str(source.get('day')), ref=f'jevhome:{LANE}'))
    ledger = SpendLedger(store.ledger_path(run_id), budget_usd=args.budget_usd)
    from testing.pipeline_lab.cli import read_private_value

    token = read_private_value(Path(args.token_file))  # owner-only regular file, never a link
    config = ProxyConfig(upstream=args.upstream, mode='record', run_id=run_id, upstream_token=token)
    scores: dict[str, float | None] = {}
    with LlmProxy(config, store=store, ledger=ledger) as proxy:
        for card in source['cards']:
            if card.get('kind') not in JUDGED_KINDS:
                continue
            lines = [by_id[lid] for lid in card_lines(card) if lid in by_id]
            try:
                scores[card['id']] = ask(proxy.url, state(transcript(lines)), card['id'])
            except Exception as error:  # noqa: BLE001 - one failed card must not stop the sweep
                scores[card['id']] = None
                print(f"card {card['id']}: {type(error).__name__}")
    run_dir = store.run_dir(run_id)
    atomic_write_json(run_dir / 'jevhome.json', {'source': args.cards, 'p_worth_keeping': scores})
    outputs = {}
    for raw in args.thresholds.split(','):
        cut = float(raw)
        out = copy.deepcopy(source)
        out['author'] = f"{source.get('author')}+jev>={cut:g}"
        for card in out['cards']:
            if card.get('kind') not in JUDGED_KINDS:
                continue
            p = scores.get(card['id'])
            if p is None:
                continue  # no answer: keep the source's call
            card['home'] = p >= cut
            if card['home']:
                card['hidden_reason'] = None
                card['key_points'] = card.get('key_points') or [card.get('title') or 'Untitled']
            else:
                card['hidden_reason'] = card.get('hidden_reason') or 'too_short'
        path = run_dir / f'jevhome-{cut:g}.json'
        atomic_write_json(path, out)
        outputs[f'{cut:g}'] = str(path)
    answered = [p for p in scores.values() if p is not None]
    print(
        json.dumps(
            {
                'run_id': run_id,
                'cards_judged': len(scores),
                'answered': len(answered),
                'usd': ledger.snapshot().get('committed_usd'),
                'outputs': outputs,
            },
            indent=1,
        )
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
