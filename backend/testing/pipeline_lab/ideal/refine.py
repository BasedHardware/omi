"""Prototype: a merge-only refinement pass over cards another pass already cut, with Jev as the judge.

    python -m testing.pipeline_lab.ideal.refine --root ROOT --packet DIR --cards CARDS.json \\
        --upstream http://127.0.0.1:19083 --token-file FILE

Three steps, none of which ever splits a card:

1. **Absorb** (rule): a run of ``background`` or ``noise`` lines with conversation lines on both sides,
   less than ``ABSORB`` apart, joins the conversation before it. Media is left alone.
2. **Same sit-down?** (Jev): each pair of neighbouring conversation cards less than ``PAIR_GAP`` apart
   is asked ``same_sitdown``; pairs at or above the merge threshold join.
3. **Home** (Jev, on the merged cards): ``worth_keeping`` (production's relevance question) and
   ``wearer_takes_part``, asked together per card.

Jev is asked once per pair and once per distinct merged card over the merge thresholds in
``MERGE_SWEEP``, so ``build()`` can rebuild any configuration offline from ``refine.json``.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
from typing import Any, Callable, Iterable, Mapping, Sequence
import urllib.request

from testing.pipeline_lab.ideal.hourpass import _ranges
from testing.pipeline_lab.ideal.jevhome import QUESTION as WORTH_KEEPING
from testing.pipeline_lab.ideal.jevhome import state, transcript
from testing.pipeline_lab.ideal.schema import card_lines, load_lines

LANE = 'omi:auto:jev-decisions'
ABSORB = timedelta(minutes=5)
PAIR_GAP = timedelta(minutes=15)
PAIR_LINES = 12
MERGE_SWEEP = (None, 0.3, 0.5, 0.7, 'all')
WEARER_MIN_WORDS = 150

SAME_SITDOWN = {
    'same_sitdown': {
        'type': 'noul',
        'instructions': (
            "These are two consecutive stretches from one person's always-on wearable. Is the second stretch the "
            'same sit-down as the first: the same people, in the same place, doing the same thing?'
        ),
        'criteria': {
            'true': (
                'the same people carry on in the same place or activity. A pause, a new topic or a tangent does '
                'not make it a new sit-down.'
            ),
            'false': (
                'the people, the place or the activity changed: someone left or arrived, they got up and went '
                'somewhere else, a call ended, or the second stretch is a different kind of speech (dictation to '
                'software, a broadcast, strangers talking).'
            ),
        },
    }
}
WEARER = {
    'wearer_takes_part': {
        'type': 'noul',
        'instructions': (
            'This was captured by a microphone the user wears all day. Is the user one of the people talking '
            'here, or is this other people\'s talk that the microphone overheard? Speaker labels are unreliable; '
            'judge by what is said.'
        ),
        'criteria': {
            'true': (
                'someone is addressed and answers as the device\'s owner would: plans, questions and answers '
                'between people who are together, a call, an order at a counter, or companions talking to each '
                'other while moving through the same places.'
            ),
            'false': (
                'a self-contained discussion among others with nobody addressing the listener, a talk or '
                'broadcast, or scattered fragments with no exchange.'
            ),
        },
    }
}
SPOKEN = ('conversation', 'voice_work')
LUNA_LANE = 'omi:auto:conversation-v3-outline'
LUNA_EDGE_LINES = 6

LUNA_PAIRS = """You review cards already cut from one person's day, transcribed from an always-on wearable. The cards
are fixed; you only decide whether some neighbouring conversation cards are really one sit-down.

{spec}

## Input and output

DAY lists every card in time order (id, local start and end, kind, words, title). CANDIDATE PAIRS lists
neighbouring conversation cards less than 15 minutes apart, with the end of the first card and the start of
the second. For each pair decide whether the second card is the same sit-down as the first: the same people,
in the same place, doing the same thing. Pauses under 15 minutes, new topics and tangents do not end a
sit-down. A change of place, people leaving or arriving, a call ending, or getting up to go elsewhere does.

Return one JSON object, {{"pairs": [{{"a": "<id>", "b": "<id>", "same": true or false, "why": "<a few words>"}}]}},
with one entry for every candidate pair. Answer with the JSON object only."""


def _times(lines: Sequence[Mapping[str, Any]]) -> tuple[dict[str, datetime], dict[str, datetime]]:
    return (
        {x['line']: datetime.fromisoformat(x['at']) for x in lines},
        {x['line']: datetime.fromisoformat(x['end']) for x in lines},
    )


def absorb(
    cards: Sequence[Mapping[str, Any]], lines: Sequence[Mapping[str, Any]], gap: timedelta = ABSORB
) -> dict[str, str]:
    """``line id -> card id`` after background/noise runs inside a conversation rejoin it."""
    at, end = _times(lines)
    kind = {str(c['id']): c.get('kind') for c in cards}
    owner = {lid: str(c['id']) for c in cards for lid in card_lines(c)}
    order = sorted((lid for lid in owner), key=lambda lid: (at[lid], lid))
    i = 0
    while i < len(order):
        if kind[owner[order[i]]] not in ('background', 'noise'):
            i += 1
            continue
        j = i
        while j < len(order) and kind[owner[order[j]]] in ('background', 'noise'):
            j += 1
        if i > 0 and j < len(order):
            left, right = order[i - 1], order[j]
            if (
                kind[owner[left]] == 'conversation'
                and kind[owner[right]] == 'conversation'
                and at[right] - end[left] <= gap
            ):
                for k in range(i, j):
                    owner[order[k]] = owner[left]
        i = j
    return owner


def pairs(
    cards: Sequence[Mapping[str, Any]], owner: Mapping[str, str], lines: Sequence[Mapping[str, Any]]
) -> list[tuple[str, str, float]]:
    """Neighbouring conversation cards (in line order) less than ``PAIR_GAP`` apart, with the gap in minutes."""
    at, end = _times(lines)
    kind = {str(c['id']): c.get('kind') for c in cards}
    conv = sorted((lid for lid, cid in owner.items() if kind[cid] == 'conversation'), key=lambda lid: (at[lid], lid))
    out: dict[tuple[str, str], float] = {}
    for a, b in zip(conv, conv[1:]):
        ca, cb = owner[a], owner[b]
        if ca == cb:
            continue
        gap = at[b] - end[a]
        if gap <= PAIR_GAP:
            key = (ca, cb)
            out[key] = min(out.get(key, 1e9), max(gap.total_seconds(), 0) / 60)
    return [(a, b, g) for (a, b), g in out.items()]


def groups(card_ids: Iterable[str], merges: Iterable[tuple[str, str]]) -> dict[str, list[str]]:
    parent = {cid: cid for cid in card_ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in merges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    out: dict[str, list[str]] = defaultdict(list)
    for cid in parent:
        out[find(cid)].append(cid)
    return dict(out)


def merges_at(pair_p: Sequence[Mapping[str, Any]], threshold: Any) -> list[tuple[str, str]]:
    if threshold is None:
        return []
    if threshold == 'luna':
        return [(p['a'], p['b']) for p in pair_p if p.get('luna') is True]
    return [(p['a'], p['b']) for p in pair_p if threshold == 'all' or (p.get('p') is not None and p['p'] >= threshold)]


def group_key(members: Iterable[str]) -> str:
    return hashlib.sha256(','.join(sorted(members)).encode()).hexdigest()[:12]


def _pair_state(a_lines, b_lines, title_a: str, title_b: str, gap_min: float) -> str:
    return (
        f'First stretch, "{title_a}" (last lines):\n```\n{transcript(a_lines[-PAIR_LINES:])}\n```\n'
        f'Then {gap_min:.0f} min later, second stretch, "{title_b}" (first lines):\n```\n'
        f'{transcript(b_lines[:PAIR_LINES])}\n```'
    )


def luna_pairs_prompt(
    cards: Mapping[str, Mapping[str, Any]],
    lines_of: Mapping[str, Sequence[str]],
    by_id: Mapping[str, Mapping[str, Any]],
    found: Sequence[tuple[str, str, float]],
) -> str:
    from testing.pipeline_lab.ideal.hourpass import render

    order = sorted((cid for cid in lines_of if lines_of[cid]), key=lambda cid: by_id[lines_of[cid][0]]['at'])
    day = ['DAY:']
    for cid in order:
        ids = lines_of[cid]
        words = sum(len(str(by_id[x]['text']).split()) for x in ids)
        day.append(
            f'- {cid} {by_id[ids[0]]["local"]}-{by_id[ids[-1]]["local"]} [{cards[cid].get("kind")}] {words} words: '
            f'"{cards[cid].get("title") or ""}"'
        )
    out = ['\n'.join(day), '', 'CANDIDATE PAIRS:']
    for a, b, gap in found:
        out.append(f'\n### {a} -> {b} ({gap:.0f} min between them)')
        out.append(f'End of {a}:\n' + render([by_id[x] for x in lines_of[a][-LUNA_EDGE_LINES:]]))
        out.append(f'Start of {b}:\n' + render([by_id[x] for x in lines_of[b][:LUNA_EDGE_LINES]]))
    return '\n'.join(out)


def ask_jev(proxy_url: str, card_state: str, questions: Mapping[str, Any], tag: str) -> dict[str, float | None]:
    body = {'model': LANE, 'state': card_state, 'questions': questions}
    request = urllib.request.Request(
        proxy_url.rstrip('/') + '/v1/systemone',
        data=json.dumps(body).encode(),
        headers={
            'Content-Type': 'application/json',
            'X-Omi-Service-Caller': 'backend',
            'X-Omi-LLM-Feature': 'jev_conversation_relevance',
            'X-Pipeline-Lab-Stage': 'refine',
            'X-Pipeline-Lab-Conversation': tag,
        },
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=60) as response:
        raw = json.loads(response.read())
    answers = raw.get('answers') or {}
    out: dict[str, float | None] = {}
    for name in questions:
        value = (answers.get(name) or {}).get('noul')
        out[name] = float(value) if isinstance(value, (int, float)) else None
    return out


HOME_RULES: dict[str, Callable[[Mapping[str, Any]], bool]] = {
    'jev.3': lambda g: (g.get('p_keep') or 0) >= 0.3,
    'jev.3&(w250|jev.5)': lambda g: (g.get('p_keep') or 0) >= 0.3
    and (g['kind'] == 'voice_work' or g['words'] >= 250 or (g.get('p_keep') or 0) >= 0.5),
}


def build(
    source: Mapping[str, Any],
    refined: Mapping[str, Any],
    *,
    merge: Any = 0.5,
    home: str = 'jev.3&(w250|jev.5)',
    wearer: float | None = 0.3,
    absorb_lines: bool = True,
) -> dict[str, Any]:
    """An ideal-format file for one configuration, from the stored Jev answers."""
    cards = {str(c['id']): c for c in source['cards']}
    owner = refined['owner'] if absorb_lines else {lid: str(c['id']) for c in source['cards'] for lid in card_lines(c)}
    merged = groups(cards, merges_at(refined['pairs'], merge))
    lines_of: dict[str, list[str]] = defaultdict(list)
    for lid, cid in owner.items():
        lines_of[cid].append(lid)
    out = []
    for root, members in sorted(merged.items(), key=lambda kv: min(min(lines_of[m] or ['L9999']) for m in kv[1])):
        ids = sorted(lid for m in members for lid in lines_of[m])
        if not ids:
            continue
        head = cards[root]
        info = refined['groups'].get(group_key(members), {})
        card = {
            'id': root,
            'lines': _ranges(ids),
            'kind': head.get('kind'),
            'title': head.get('title') or '',
            'people': head.get('people') or [],
            'key_points': [],
            'tasks': [],
            'confidence': head.get('confidence') or 'medium',
            'why': f'refine: {len(members)} card(s)',
        }
        on = False
        if head.get('kind') in SPOKEN:
            g = {'kind': head.get('kind'), 'words': info.get('words', 0), 'p_keep': info.get('p_keep')}
            on = HOME_RULES[home](g)
            if (
                on
                and wearer is not None
                and head.get('kind') == 'conversation'
                and info.get('words', 0) >= WEARER_MIN_WORDS
                and info.get('p_wearer') is not None
                and info['p_wearer'] < wearer
            ):
                on = False
        card['home'] = on
        card['hidden_reason'] = None if on else ('too_short' if head.get('kind') in SPOKEN else head.get('kind'))
        if on:
            card['key_points'] = [card['title'] or 'Untitled']
        out.append(card)
    return {
        'day': source.get('day'),
        'author': f"{source.get('author')}+refine(merge={merge},home={home},wearer={wearer})",
        'spec_version': source.get('spec_version', 2),
        'cards': out,
    }


def main(argv: Sequence[str] | None = None) -> int:
    from testing.pipeline_lab import contracts as c
    from testing.pipeline_lab.ledger import SpendLedger
    from testing.pipeline_lab.llm_proxy.server import LlmProxy, ProxyConfig
    from testing.pipeline_lab.store import Store, atomic_write_json, ensure_private_dir

    parser = argparse.ArgumentParser(prog='python -m testing.pipeline_lab.ideal.refine')
    parser.add_argument('--root', required=True)
    parser.add_argument('--packet', required=True)
    parser.add_argument('--cards', required=True)
    parser.add_argument('--upstream', required=True)
    parser.add_argument('--token-file', required=True)
    parser.add_argument('--budget-usd', type=float, default=1.0)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--spec', help='spec for the Luna pair judge; without it the judge is skipped')
    parser.add_argument('--luna-effort', default='low')
    args = parser.parse_args(argv)

    lines = load_lines(Path(args.packet))
    by_id = {x['line']: x for x in lines}
    source = json.loads(Path(args.cards).read_text(encoding='utf-8'))
    cards = {str(card['id']): card for card in source['cards']}
    owner = absorb(source['cards'], lines)
    lines_of: dict[str, list[str]] = defaultdict(list)
    for lid, cid in owner.items():
        lines_of[cid].append(lid)
    for ids in lines_of.values():
        ids.sort(key=lambda lid: (by_id[lid]['at'], lid))
    found = pairs(source['cards'], owner, lines)

    store = Store(root=ensure_private_dir(Path(args.root)), verdicts_root=Path(os.devnull))
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    run_id = f'{stamp}-refine-{source.get("day")}-{secrets.token_hex(3)}'
    store.create_run(c.RunRecord(run_id=run_id, day_id=str(source.get('day')), ref=f'refine:{LANE}'))
    ledger = SpendLedger(store.ledger_path(run_id), budget_usd=args.budget_usd)
    from testing.pipeline_lab.cli import read_private_value

    token = read_private_value(Path(args.token_file))  # owner-only regular file, never a link
    config = ProxyConfig(upstream=args.upstream, mode='record', run_id=run_id, upstream_token=token)
    failures = 0
    with LlmProxy(config, store=store, ledger=ledger) as proxy, ThreadPoolExecutor(args.workers) as pool:

        def safe(card_state: str, questions: Mapping[str, Any], tag: str) -> dict[str, float | None]:
            nonlocal failures
            try:
                return ask_jev(proxy.url, card_state, questions, tag)
            except Exception as error:  # noqa: BLE001 - one failed question must not stop the sweep
                failures += 1
                print(f'{tag}: {type(error).__name__}')
                return {name: None for name in questions}

        def pair_job(item):
            a, b, gap = item
            text = _pair_state(
                [by_id[x] for x in lines_of[a]],
                [by_id[x] for x in lines_of[b]],
                str(cards[a].get('title') or ''),
                str(cards[b].get('title') or ''),
                gap,
            )
            return {
                'a': a,
                'b': b,
                'gap_min': round(gap, 1),
                'p': safe(text, SAME_SITDOWN, f'pair-{a}-{b}')['same_sitdown'],
            }

        pair_p = list(pool.map(pair_job, found))
        sweep = list(MERGE_SWEEP)
        if args.spec and found:
            from testing.pipeline_lab.ideal.hourpass import gateway_call

            messages = [
                {
                    'role': 'system',
                    'content': LUNA_PAIRS.format(spec=Path(args.spec).read_text(encoding='utf-8').strip()),
                },
                {'role': 'user', 'content': luna_pairs_prompt(cards, lines_of, by_id, found)},
            ]
            try:
                answer = gateway_call(proxy.url, messages, effort=args.luna_effort, tag='luna-pairs')
                verdict = {
                    (str(x.get('a')), str(x.get('b'))): x for x in answer.get('pairs') or [] if isinstance(x, Mapping)
                }
            except Exception as error:  # noqa: BLE001
                failures += 1
                print(f'luna-pairs: {type(error).__name__}')
                verdict = {}
            for p in pair_p:
                v = verdict.get((p['a'], p['b']))
                p['luna'] = bool(v.get('same')) if v and isinstance(v.get('same'), bool) else None
                p['luna_why'] = str(v.get('why') or '')[:200] if v else ''
            sweep.append('luna')
        distinct: dict[str, list[str]] = {}
        for threshold in sweep:
            for root, members in groups(cards, merges_at(pair_p, threshold)).items():
                if cards[root].get('kind') in SPOKEN:
                    distinct.setdefault(group_key(members), members)

        def group_job(item):
            key, members = item
            ids = sorted((lid for m in members for lid in lines_of[m]), key=lambda lid: (by_id[lid]['at'], lid))
            text = transcript([by_id[x] for x in ids])
            words = len(text.split())
            questions = dict(WORTH_KEEPING)
            if cards[members[0]].get('kind') == 'conversation' and words >= WEARER_MIN_WORDS:
                questions.update(WEARER)
            answer = safe(state(text), questions, f'group-{key}')
            return key, {
                'members': sorted(members),
                'words': words,
                'p_keep': answer.get('worth_keeping'),
                'p_wearer': answer.get('wearer_takes_part'),
            }

        group_p = dict(pool.map(group_job, distinct.items()))
    run_dir = store.run_dir(run_id)
    refined = {'source': args.cards, 'owner': owner, 'pairs': pair_p, 'groups': group_p}
    atomic_write_json(run_dir / 'refine.json', refined)
    print(
        json.dumps(
            {
                'run_id': run_id,
                'absorbed_lines': sum(
                    1 for c0 in source['cards'] for lid in card_lines(c0) if owner.get(lid) != str(c0['id'])
                ),
                'pairs': len(pair_p),
                'luna_same': sum(1 for p in pair_p if p.get('luna') is True),
                'luna_unanswered': sum(1 for p in pair_p if 'luna' in p and p['luna'] is None),
                'groups_judged': len(group_p),
                'failures': failures,
                'usd': ledger.snapshot().get('committed_usd'),
                'out': str(run_dir / 'refine.json'),
            },
            indent=1,
        )
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
