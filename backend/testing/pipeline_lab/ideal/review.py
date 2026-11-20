"""Merge two independent ideal drafts and list where they disagree, for a person to decide.

    python -m testing.pipeline_lab.ideal.review --packet DIR --a A.json --b B.json \\
        [--baseline PROD.jsonl] [--run RUN_DIR] --out DIR

Two drafts are aligned by the lines their cards hold. A **span** is a connected group of cards:
cards from either draft that share a line belong to the same span. A span is **agreed** when
both drafts cut it into the same cards (each card's line set matches with IoU >= 0.8) and make
the same Home call for each; otherwise it is **disputed**.

Writes ``review.json`` (every span, with both drafts' cards, the candidates' cards on the same lines
for context, and a transcript excerpt) and ``review.md`` (the disputed spans, readable).
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from testing.pipeline_lab.ideal.schema import card_lines, load_lines
from testing.pipeline_lab.ideal.score import Partition, conversations_partition
from testing.pipeline_lab.store import atomic_write_bytes, atomic_write_json, ensure_private_dir

AGREE_IOU = 0.8
EXCERPT_LINES = 40


def _cards(ideal: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(c['id']): {**c, '_lines': set(card_lines(c))} for c in ideal.get('cards') or []}


def spans(a: Mapping[str, Any], b: Mapping[str, Any]) -> list[dict[str, Any]]:
    cards_a, cards_b = _cards(a), _cards(b)
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    owner_b = {lid: cid for cid, c in cards_b.items() for lid in c['_lines']}
    for cid, card in cards_a.items():
        find(f'a:{cid}')
        for lid in card['_lines']:
            if lid in owner_b:
                parent[find(f'a:{cid}')] = find(f'b:{owner_b[lid]}')
    for cid in cards_b:
        find(f'b:{cid}')
    groups: dict[str, dict[str, list[str]]] = defaultdict(lambda: {'a': [], 'b': []})
    for key in list(parent):
        side, cid = key.split(':', 1)
        groups[find(key)][side].append(cid)
    out = []
    for members in groups.values():
        a_cards = [cards_a[c] for c in members['a']]
        b_cards = [cards_b[c] for c in members['b']]
        lines = set().union(*[c['_lines'] for c in a_cards + b_cards])
        agreed = len(a_cards) == len(b_cards) and all(
            any(
                _iou(x['_lines'], y['_lines']) >= AGREE_IOU and bool(x.get('home')) == bool(y.get('home'))
                for y in b_cards
            )
            for x in a_cards
        )
        out.append({'lines': sorted(lines), 'a': a_cards, 'b': b_cards, 'agreed': agreed})
    out.sort(key=lambda s: s['lines'][0])
    return out


def _iou(x: set[str], y: set[str]) -> float:
    return len(x & y) / len(x | y) if x | y else 1.0


def _public(card: Mapping[str, Any]) -> dict[str, Any]:
    keep = ('id', 'lines', 'kind', 'home', 'hidden_reason', 'title', 'key_points', 'tasks', 'confidence', 'why')
    return {k: card.get(k) for k in keep}


def _context(part: Partition | None, ids: Sequence[str]) -> list[dict[str, Any]]:
    if part is None:
        return []
    held: dict[str, int] = defaultdict(int)
    for lid in ids:
        if lid in part.card_of:
            held[part.card_of[lid]] += 1
    return [
        {'title': part.title.get(cid, ''), 'home': part.home.get(cid, False), 'lines': n}
        for cid, n in sorted(held.items(), key=lambda kv: -kv[1])
    ]


def build_review(
    packet: Path,
    a: Mapping[str, Any],
    b: Mapping[str, Any],
    *,
    production: Sequence[Mapping[str, Any]] = (),
    replay: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    lines = load_lines(packet)
    by_id = {line['line']: line for line in lines}
    prod = conversations_partition(production, lines) if production else None
    rep = conversations_partition(replay, lines) if replay else None
    items = []
    for index, span in enumerate(spans(a, b), start=1):
        ids = span['lines']
        excerpt = [by_id[lid] for lid in ids[:EXCERPT_LINES] if lid in by_id]
        items.append(
            {
                'span': f's{index:03d}',
                'first': ids[0],
                'last': ids[-1],
                'local': f"{by_id[ids[0]]['local']}-{by_id[ids[-1]]['local']}",
                'lines': len(ids),
                'agreed': span['agreed'],
                'a': [_public(c) for c in span['a']],
                'b': [_public(c) for c in span['b']],
                'production': _context(prod, ids),
                'replay': _context(rep, ids),
                'excerpt': [f"{x['line']} {x['local']} {x['speaker']}: {x['text']}" for x in excerpt],
            }
        )
    return {
        'authors': {'a': a.get('author'), 'b': b.get('author')},
        'spans': len(items),
        'disputed': sum(1 for item in items if not item['agreed']),
        'items': items,
    }


def render_markdown(review: Mapping[str, Any]) -> str:
    names = review['authors']
    out = [
        f"# Ideal review: {review['disputed']} disputed of {review['spans']} spans",
        f"A = {names['a']}, B = {names['b']}",
        '',
    ]
    for item in review['items']:
        if item['agreed']:
            continue
        out.append(f"## {item['span']} {item['local']} ({item['first']}-{item['last']}, {item['lines']} lines)")
        for side in ('a', 'b'):
            for card in item[side]:
                where = 'HOME' if card['home'] else f"hidden: {card['hidden_reason']}"
                out.append(
                    f"- **{side.upper()}** {card['title'] or '(untitled)'} [{card['kind']}, {where}, {card['confidence']}] {', '.join(card['lines'])}"
                )
                out.append(f"  - why: {card['why']}")
        for name in ('production', 'replay'):
            if item[name]:
                desc = '; '.join(
                    f"{c['title'] or '(untitled)'} ({'HOME' if c['home'] else 'hidden'}, {c['lines']} lines)"
                    for c in item[name]
                )
                out.append(f'- {name}: {desc}')
        out.append('')
    return '\n'.join(out) + '\n'


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(row) for row in Path(path).read_text(encoding='utf-8').splitlines() if row.strip()]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m testing.pipeline_lab.ideal.review')
    parser.add_argument('--packet', required=True)
    parser.add_argument('--a', required=True)
    parser.add_argument('--b', required=True)
    parser.add_argument('--baseline')
    parser.add_argument('--run')
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    production = _read_jsonl(Path(args.baseline)) if args.baseline else []
    replay = (
        [json.loads(p.read_text(encoding='utf-8')) for p in sorted((Path(args.run) / 'conversations').glob('*.json'))]
        if args.run
        else []
    )
    review = build_review(
        Path(args.packet),
        json.loads(Path(args.a).read_text(encoding='utf-8')),
        json.loads(Path(args.b).read_text(encoding='utf-8')),
        production=production,
        replay=replay,
    )
    out = ensure_private_dir(Path(args.out))
    atomic_write_json(out / 'review.json', review)
    atomic_write_bytes(out / 'review.md', render_markdown(review).encode('utf-8'))
    print(json.dumps({'spans': review['spans'], 'disputed': review['disputed'], 'out': str(out)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
