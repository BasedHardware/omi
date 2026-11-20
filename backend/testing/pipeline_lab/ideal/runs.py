"""Compare full replays of one day: a score table against the day's ideal, and a per-card diff.

    python -m testing.pipeline_lab.ideal.runs score DAY LABEL=RUN_ID [LABEL=RUN_ID ...] [--ignore-kind voice_work]
    python -m testing.pipeline_lab.ideal.runs diff  LABEL=RUN_ID LABEL=RUN_ID [...]

Paths come from the run store (``$OMI_PIPELINE_LAB_ROOT``, or ``--root``):

- ``score`` reads ``ideal/DAY/packet``, ``ideal/DAY/ideal.json``, production's
  ``corpus/DAY/baseline/v3_conversations.jsonl`` (printed first when present) and each
  ``runs/RUN_ID/conversations/*.json``.
- ``diff`` compares every run with the first one: cards whose (start, end) match exactly,
  cards only one side has, and Home flips on matching cards.

A card still open when the run ended (no ``finished_at``) ends at its last segment and is marked
``open``. Output is times (UTC), minutes, word counts, the Home flag and its reason: never transcript text
or titles, so it is safe to paste into a PR or an issue.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from testing.pipeline_lab.baseline.compare import home_reason, on_home
from testing.pipeline_lab.ideal.schema import load_lines
from testing.pipeline_lab.ideal.score import conversations_partition, ideal_partition, score
from testing.pipeline_lab.store import lab_root

Card = tuple[datetime, datetime, int, bool, str]  # start, end, words, on Home, reason ('+open' if open)


def _when(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def load_run(root: Path, run_id: str) -> list[dict[str, Any]]:
    return [
        json.loads(p.read_text(encoding='utf-8'))
        for p in sorted((root / 'runs' / run_id / 'conversations').glob('*.json'))
    ]


def card(conversation: Mapping[str, Any]) -> Card:
    segments = conversation.get('segments') or conversation.get('transcript_segments') or []
    words = sum(len((s.get('text') or '').split()) for s in segments)
    home = on_home(conversation)  # the scorer's predicate: v3 visibility, else not discarded (classic)
    start = _when(conversation['started_at'])
    reason = '' if home else home_reason(conversation)
    if conversation.get('finished_at'):
        end = _when(conversation['finished_at'])
    else:
        last = max((float(s.get('end') or s.get('start') or 0) for s in segments), default=0.0)
        end = start + timedelta(seconds=last)
        reason = (reason + ' +open').strip()
    return (start, end, words, bool(home), reason)


def card_diff(a: Iterable[Card], b: Iterable[Card]) -> dict[str, Any]:
    a, b = sorted(a), sorted(b)
    b_by_span = {(c[0], c[1]): c for c in b}
    a_spans = {(c[0], c[1]) for c in a}
    same = [c for c in a if (c[0], c[1]) in b_by_span]
    return {
        'identical': len(same),
        'only_a': [c for c in a if (c[0], c[1]) not in b_by_span],
        'only_b': [c for c in b if (c[0], c[1]) not in a_spans],
        'home_flips': [(x, b_by_span[(x[0], x[1])]) for x in same if b_by_span[(x[0], x[1])][3] != x[3]],
    }


def fmt(c: Card) -> str:
    start, end, words, home, why = c
    minutes = int((end - start).total_seconds() / 60)
    return f"{start:%H:%M:%S}-{end:%H:%M:%S} {minutes:>4}m {words:>6}w {'HOME' if home else 'hid '} {why}".rstrip()


def score_row(name: str, result: Mapping[str, Any]) -> str:
    home = result['home']
    n = home['ideal']
    return (
        f"{name:26} cards {result['cards']['candidate']:>4} split {result['split']:>4} merge {result['merge']:>3} "
        f"F1 {result['boundary']['f1']:.2f} | home {home['candidate']:>3} rec {round(home['recall'] * n)}/{n} "
        f"whole {round(home['whole'] * n)}/{n} prec {home['precision']:.2f} wprec {home['word_precision']:.2f}"
    )


def _pairs(values: Sequence[str]) -> list[tuple[str, str]]:
    out = []
    for value in values:
        label, sep, run_id = value.partition('=')
        if not sep or not label or not run_id:
            raise SystemExit(f'expected LABEL=RUN_ID, got {value!r}')
        out.append((label, run_id))
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m testing.pipeline_lab.ideal.runs')
    parser.add_argument('--root', help='run store (default $OMI_PIPELINE_LAB_ROOT)')
    sub = parser.add_subparsers(dest='command', required=True)
    p_score = sub.add_parser('score')
    p_score.add_argument('day')
    p_score.add_argument('runs', nargs='+')
    p_score.add_argument('--ignore-kind', action='append', default=None, help='default: voice_work (dictation)')
    p_diff = sub.add_parser('diff')
    p_diff.add_argument('runs', nargs='+')
    args = parser.parse_args(argv)
    root = lab_root(args.root)
    runs = _pairs(args.runs)

    if args.command == 'score':
        day = root / 'ideal' / args.day
        lines = load_lines(day / 'packet')
        kinds = tuple(args.ignore_kind) if args.ignore_kind is not None else ('voice_work',)
        ideal = ideal_partition(json.loads((day / 'ideal.json').read_text(encoding='utf-8')), ignore_kinds=kinds)
        print(args.day)
        baseline = root / 'corpus' / args.day / 'baseline' / 'v3_conversations.jsonl'
        if baseline.exists():
            rows = [json.loads(r) for r in baseline.read_text(encoding='utf-8').splitlines() if r.strip()]
            print('  ' + score_row('production', score(ideal, conversations_partition(rows, lines), lines)))
        for label, run_id in runs:
            convs = load_run(root, run_id)
            print('  ' + score_row(label, score(ideal, conversations_partition(convs, lines), lines)))
        return 0

    if len(runs) < 2:
        parser.error('diff needs at least two LABEL=RUN_ID')
    loaded = {label: [card(c) for c in load_run(root, run_id)] for label, run_id in runs}
    base, *others = [label for label, _ in runs]
    for other in others:
        d = card_diff(loaded[base], loaded[other])
        print(
            f"== {base} vs {other}: identical boundaries {d['identical']}, only in {base} {len(d['only_a'])}, "
            f"only in {other} {len(d['only_b'])}, Home flips on identical cards {len(d['home_flips'])}"
        )
        print(f'-- only in {base}:')
        for c in d['only_a']:
            print('  ' + fmt(c))
        print(f'-- only in {other}:')
        for c in d['only_b']:
            print('  ' + fmt(c))
        for x, y in d['home_flips']:
            print(f"  flip {fmt(x)} -> {'HOME' if y[3] else 'hid'} {y[4]}".rstrip())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
