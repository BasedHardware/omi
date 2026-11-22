"""Score conversations against an ideal, on structure: card boundaries and Home.

    python -m testing.pipeline_lab.ideal.score --packet DIR --ideal IDEAL.json \\
        (--run RUN_DIR | --baseline FILE.jsonl | --other OTHER_IDEAL.json) [--json]

The candidate is turned into a partition of the packet's lines:

- **conversations** (a run's ``conversations/*.json`` or production's ``v3_conversations.jsonl``,
  contract shape): each segment is matched to the line with the same text within 2 s of its
  absolute start (``started_at + segment.start``). A segment matching a duplicate line counts
  for the line it duplicates. Lines no conversation holds are unassigned.
- **another ideal** (``--other``): its cards, as written. Use it to find where two drafts disagree.

Metrics (lines in time order, duplicates left out):

- ``split``: neighbouring lines the ideal keeps in one card and the candidate separates.
- ``merge``: neighbouring lines the ideal separates and the candidate keeps together.
- ``boundary_f1``: F1 of "a new card starts here" between neighbouring lines.
- ``home``: ``recall`` (ideal Home cards whose lines are mostly on Home in the candidate),
  ``whole`` (... mostly inside a single candidate Home card), ``precision`` (candidate Home cards
  whose scored lines are mostly in ideal Home cards; a candidate card made mostly of don't-care
  lines, such as dictation, is left out), the misses and false adds by title, and ``word_recall``
  and ``word_precision``, the same weighted by words.
- ``cards``: per ideal card, how the candidate covers it (for review lists).
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from testing.pipeline_lab.baseline.compare import on_home
from testing.pipeline_lab.ideal.schema import card_lines, load_lines
from testing.pipeline_lab.stack.io import parse_time

MATCH_SLACK = timedelta(seconds=2)
MOSTLY = 0.5
WHOLE = 0.8


def _norm(text: Any) -> str:
    return ' '.join(str(text or '').casefold().split())


class Partition:
    """``line id -> (card id, on Home)`` plus card titles, over one packet's lines."""

    def __init__(self) -> None:
        self.card_of: dict[str, str] = {}
        self.home: dict[str, bool] = {}
        self.title: dict[str, str] = {}

    def lines_of(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = defaultdict(list)
        for lid, cid in self.card_of.items():
            out[cid].append(lid)
        return out


def ideal_partition(ideal: Mapping[str, Any], *, ignore_kinds: Sequence[str] = ()) -> Partition:
    """``ignore_kinds``: cards of these kinds are "don't care": their lines leave the score entirely."""
    part = Partition()
    for card in ideal.get('cards') or []:
        if card.get('kind') in ignore_kinds:
            continue
        cid = str(card['id'])
        part.home[cid] = bool(card.get('home'))
        part.title[cid] = str(card.get('title') or '')
        for lid in card_lines(card):
            part.card_of.setdefault(lid, cid)
    return part


def conversations_partition(
    conversations: Sequence[Mapping[str, Any]], lines: Sequence[Mapping[str, Any]]
) -> Partition:
    by_text: dict[str, list[tuple[datetime, str]]] = defaultdict(list)
    for line in lines:
        target = str(line.get('dup_of') or line['line'])
        by_text[_norm(line['text'])].append((datetime.fromisoformat(line['at']), target))
    part = Partition()
    # A line two conversations both hold goes to the earlier-starting one (then lower id), never to
    # whichever file a directory listing returned first.
    for conv in sorted(conversations, key=lambda c: (str(c.get('started_at') or ''), str(c.get('id')))):
        cid = str(conv.get('id'))
        origin = parse_time(conv.get('started_at'))
        part.home[cid] = on_home(conv)
        part.title[cid] = str((conv.get('structured') or {}).get('title') or '')
        if origin is None:
            continue
        for segment in conv.get('segments') or conv.get('transcript_segments') or []:
            at = origin + timedelta(seconds=float(segment.get('start') or 0))
            candidates = by_text.get(_norm(segment.get('text')), [])
            best = min(candidates, key=lambda c: abs((c[0] - at).total_seconds()), default=None)
            if best is not None and abs(best[0] - at) <= MATCH_SLACK:
                part.card_of.setdefault(best[1], cid)
    return part


def score(ideal: Partition, candidate: Partition, lines: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    order = [str(line['line']) for line in lines if not line.get('dup_of') and str(line['line']) in ideal.card_of]
    unassigned = [lid for lid in order if lid not in candidate.card_of]

    def cand(lid: str) -> str:
        return candidate.card_of.get(lid) or f'unassigned:{lid}'

    split = merge = both = 0
    ideal_starts = cand_starts = 0
    split_at: list[str] = []
    merge_at: list[str] = []
    for prev, cur in zip(order, order[1:]):
        same_ideal = ideal.card_of[prev] == ideal.card_of[cur]
        same_cand = cand(prev) == cand(cur)
        ideal_starts += not same_ideal
        cand_starts += not same_cand
        if same_ideal and not same_cand:
            split += 1
            split_at.append(cur)
        elif not same_ideal and same_cand:
            merge += 1
            merge_at.append(cur)
        elif not same_ideal and not same_cand:
            both += 1
    precision = both / cand_starts if cand_starts else 1.0
    recall = both / ideal_starts if ideal_starts else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    ideal_cards = ideal.lines_of()
    cand_cards = candidate.lines_of()
    cards: list[dict[str, Any]] = []
    home_hit = home_whole = 0
    misses: list[str] = []
    for cid, ids in sorted(ideal_cards.items(), key=lambda kv: min(kv[1])):
        held = Counter(cand(lid) for lid in ids)
        on_home_lines = sum(n for c, n in held.items() if candidate.home.get(c))
        top, top_n = held.most_common(1)[0]
        entry = {
            'card': cid,
            'title': ideal.title.get(cid, ''),
            'home': ideal.home.get(cid, False),
            'lines': len(ids),
            'pieces': len([c for c in held if not c.startswith('unassigned:')])
            + (1 if any(c.startswith('unassigned:') for c in held) else 0),
            'largest_share': round(top_n / len(ids), 3),
            'candidate_home_share': round(on_home_lines / len(ids), 3),
            'candidate_titles': [
                candidate.title.get(c, '') for c, _ in held.most_common(4) if not c.startswith('unassigned:')
            ],
        }
        if entry['home']:
            if on_home_lines / len(ids) >= MOSTLY:
                home_hit += 1
            else:
                misses.append(entry['title'])
            if candidate.home.get(top) and top_n / len(ids) >= WHOLE:
                home_whole += 1
        cards.append(entry)
    ideal_home = sum(1 for c in ideal_cards if ideal.home.get(c))
    false_adds: list[str] = []
    cand_home_cards = 0
    cand_home_good = 0
    for cid, ids in cand_cards.items():
        if not candidate.home.get(cid):
            continue
        scored = [lid for lid in ids if lid in ideal.card_of]  # lines the ideal cares about
        if not scored or len(scored) < MOSTLY * len(ids):
            continue  # mostly don't-care lines (e.g. dictation): neither a hit nor a false add
        cand_home_cards += 1
        in_ideal_home = sum(1 for lid in scored if ideal.home.get(ideal.card_of[lid], False))
        if in_ideal_home / len(scored) >= MOSTLY:
            cand_home_good += 1
        else:
            false_adds.append(candidate.title.get(cid, cid))
    words = {str(line['line']): len(str(line.get('text') or '').split()) for line in lines}
    ideal_home_words = sum(words[lid] for lid in order if ideal.home.get(ideal.card_of[lid], False))
    recalled_words = sum(
        words[lid] for lid in order if ideal.home.get(ideal.card_of[lid], False) and candidate.home.get(cand(lid))
    )
    cand_home_words = sum(words[lid] for lid in order if candidate.home.get(cand(lid)))
    return {
        'lines': len(order),
        'unassigned_lines': len(unassigned),
        'cards': {
            'ideal': len(ideal_cards),
            'candidate': sum(1 for ids in cand_cards.values() if any(lid in ideal.card_of for lid in ids)),
        },
        'split': split,
        'merge': merge,
        'boundary': {'precision': round(precision, 3), 'recall': round(recall, 3), 'f1': round(f1, 3)},
        'home': {
            'ideal': ideal_home,
            'candidate': cand_home_cards,
            'recall': round(home_hit / ideal_home, 3) if ideal_home else 1.0,
            'whole': round(home_whole / ideal_home, 3) if ideal_home else 1.0,
            'precision': round(cand_home_good / cand_home_cards, 3) if cand_home_cards else 1.0,
            'misses': misses,
            'word_recall': round(recalled_words / ideal_home_words, 3) if ideal_home_words else 1.0,
            'word_precision': round(recalled_words / cand_home_words, 3) if cand_home_words else 1.0,
            'false_adds': false_adds,
        },
        'split_at': split_at,
        'merge_at': merge_at,
        'per_card': cards,
    }


def _load_conversations(run: Path | None, baseline: Path | None) -> list[dict[str, Any]]:
    if run is not None:
        return [json.loads(p.read_text(encoding='utf-8')) for p in sorted((Path(run) / 'conversations').glob('*.json'))]
    assert baseline is not None
    return [json.loads(row) for row in Path(baseline).read_text(encoding='utf-8').splitlines() if row.strip()]


def summary_text(result: Mapping[str, Any]) -> str:
    home = result['home']
    lines = [
        f"cards: ideal {result['cards']['ideal']}, candidate {result['cards']['candidate']}",
        f"boundaries: split {result['split']}, merge {result['merge']}, F1 {result['boundary']['f1']}",
        f"home: ideal {home['ideal']}, candidate {home['candidate']}, recall {home['recall']}, "
        f"whole {home['whole']}, precision {home['precision']}",
    ]
    if home['misses']:
        lines.append('missing from Home: ' + '; '.join(home['misses']))
    if home['false_adds']:
        lines.append('wrongly on Home: ' + '; '.join(home['false_adds']))
    if result['unassigned_lines']:
        lines.append(f"lines in no candidate card: {result['unassigned_lines']}")
    return '\n'.join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m testing.pipeline_lab.ideal.score')
    parser.add_argument('--packet', required=True)
    parser.add_argument('--ideal', required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--run')
    group.add_argument('--baseline')
    group.add_argument('--other')
    parser.add_argument('--json', action='store_true')
    parser.add_argument(
        '--ignore-kind', action='append', default=[], help='ideal card kind to leave out (e.g. voice_work)'
    )
    args = parser.parse_args(argv)
    lines = load_lines(Path(args.packet))
    ideal = ideal_partition(
        json.loads(Path(args.ideal).read_text(encoding='utf-8')), ignore_kinds=tuple(args.ignore_kind)
    )
    if args.other:
        candidate = ideal_partition(json.loads(Path(args.other).read_text(encoding='utf-8')))
    else:
        convs = _load_conversations(
            Path(args.run) if args.run else None, Path(args.baseline) if args.baseline else None
        )
        candidate = conversations_partition(convs, lines)
    result = score(ideal, candidate, lines)
    print(json.dumps(result, ensure_ascii=False, indent=1) if args.json else summary_text(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
