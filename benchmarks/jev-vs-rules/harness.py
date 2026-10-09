#!/usr/bin/env python3
"""Stdlib-only synthetic keep-rescue replay. No provider/database imports or I/O.

The ambiguous model tier is a KEEP fake, not a measured nano prediction.
R16 counterfactuals disable only the injected calendar fake, never a live rule.
"""

import argparse
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
from types import ModuleType
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FIXTURES = HERE / 'fixtures/manifest.jsonl'
LABEL_STATUS = 'agent_proposed_unreviewed'
BASE_HEAD = '7ba0b9a8e94093f553f902f24b74cff4e30a1558'


def _forbidden(*args, **kwargs):
    raise RuntimeError('offline adapter forbids provider calls')


@lru_cache(maxsize=1)
def runtime():
    """Load real pinned-path stdlib modules with scoped import seams via runpy.

    Restore sys.modules on exit, including when invoked inside backend pytest.
    Only relevance_jev's unused model/transport imports are faked.
    """
    names = [
        'config',
        'utils',
        'utils.conversations',
        'models',
        'models.transcript_segment',
        'utils.llm',
        'utils.llm.jev_client',
    ]
    modules = {name: ModuleType(name) for name in names}
    modules['models.transcript_segment'].TranscriptSegment = object
    modules['utils.llm.jev_client'].ask_jev = _forbidden
    with patch.dict(sys.modules, modules):
        for name, relative in [
            ('config.jev_decisions', 'config/jev_decisions.py'),
            ('utils.conversations.processing_trigger', 'utils/conversations/processing_trigger.py'),
            ('utils.conversations.relevance_rules', 'utils/conversations/relevance_rules.py'),
            ('utils.conversations.relevance_rescue', 'utils/conversations/relevance_rescue.py'),
            ('utils.conversations.relevance_jev', 'utils/conversations/relevance_jev.py'),
            ('utils.conversations.relevance', 'utils/conversations/relevance.py'),
        ]:
            module = ModuleType(name)
            module.__dict__.update(runpy.run_path(str(ROOT / 'backend' / relative)))
            sys.modules[name] = module
            modules[name] = module
            parent, child = name.rsplit('.', 1)
            setattr(sys.modules[parent], child, module)
    return modules


def calendar_retains(row):
    """Fixture-only calendar fake: explicit overlap/coverage, no title inference."""
    calendar = row.get('calendar')
    if not calendar:
        return False
    return (
        calendar['overlap_seconds'] >= 10
        and max(calendar['event_coverage'], calendar['conversation_coverage']) >= 0.5
        and calendar.get('status', 'confirmed') != 'cancelled'
        and calendar.get('response', 'accepted') != 'declined'
    )


def baseline(row, *, without_calendar=False):
    modules = runtime()
    relevance = modules['utils.conversations.relevance']
    trigger = modules['utils.conversations.processing_trigger'].ProcessingTrigger(row['trigger'])
    with patch.dict(os.environ, {'CONVERSATION_RELEVANCE_JEV_RESCUE': 'off'}):
        decision = relevance.decide_relevance(
            trigger=trigger,
            texts=row['segments'],
            speech_seconds=None,
            has_photos=False,
            user_kept=False,
            exempt=False,
            trusted_wake_word=False,
            model_discards=lambda error, neighbor: False,
            calendar_retains=lambda: False if without_calendar else calendar_retains(row),
        )
    return {'verdict': decision.verdict, 'decided_by': decision.decided_by, 'reason': decision.reason}


def prompt(segments):
    modules = runtime()
    jev = modules['utils.conversations.relevance_jev']
    rescue = modules['utils.conversations.relevance_rescue']
    return jev.relevance_state(rescue.transcript_for_rescue(segments)), jev.QUESTIONS


def load_fixtures(path=FIXTURES):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    seen = set()
    for row in rows:
        if row['family_id'] in seen:
            raise ValueError('duplicate family_id')
        seen.add(row['family_id'])
        if row.get('label_status') != LABEL_STATUS:
            raise ValueError(f"fixture {row['family_id']}: label_status must be {LABEL_STATUS}")
        if row['provenance'] != 'synthetic' or row['keep_label'] not in {'keep', 'discard', 'uncertain'}:
            raise ValueError('pilot accepts synthetic labeled fixtures only')
        if row['source_kind'] not in {'live', 'sync'} or row['trigger'] != 'capture_end':
            raise ValueError('invalid fixture source/trigger')
        if not isinstance(row['segments'], list) or not all(isinstance(t, str) for t in row['segments']):
            raise ValueError('segments must be raw strings')
        if row['expected_baseline'] != baseline(row):
            raise ValueError(f"baseline drift: {row['family_id']}")
        if 'R16' in row['rule_ids'] and row['expected_without_calendar'] != baseline(row, without_calendar=True):
            raise ValueError(f"counterfactual drift: {row['family_id']}")
    return rows


class MockJevClient:
    """Fabricated P(discard) scores keyed only by family ID, never labels."""

    def __init__(self, scores=None):
        self.scores = scores or {}
        self.calls = []

    def score(self, family_id, state, questions):
        self.calls.append({'family_id': family_id, 'state': state, 'questions': questions})
        value = self.scores.get(family_id, 0.9)
        if value == 'error':
            raise TimeoutError('synthetic timeout')
        return value


def _second_opinion(row, decision, client):
    rescue = runtime()['utils.conversations.relevance_rescue']
    eligible = decision['verdict'] == 'discard' and rescue.should_rescue(row['segments'], decision['reason'])
    if not eligible:
        return {'baseline': decision, 'score': None, 'rescued': False, 'outcome': 'not_eligible', 'final': decision}
    state, questions = prompt(row['segments'])
    result = rescue.rescue_decision(lambda: client.score(row['family_id'], state, questions))
    final = (
        dict(decision, verdict='keep', decided_by='jev', reason=f"rescue_{decision['reason']}")
        if result.rescued
        else decision
    )
    return {
        'baseline': decision,
        'score': result.score,
        'rescued': result.rescued,
        'outcome': result.outcome,
        'final': final,
    }


def evaluate(rows, client):
    results = []
    for row in rows:
        result = dict(
            family_id=row['family_id'],
            rule_ids=row['rule_ids'],
            keep_label=row['keep_label'],
            language=row['language'],
            source_kind=row['source_kind'],
            label_status=row['label_status'],
        )
        result.update(_second_opinion(row, baseline(row), client))
        if 'R16' in row['rule_ids']:
            counterfactual = baseline(row, without_calendar=True)
            result['without_calendar'] = (
                _second_opinion(row, counterfactual, client)
                if counterfactual != result['baseline']
                else {key: result[key] for key in ('baseline', 'score', 'rescued', 'outcome', 'final')}
            )
        result['agreement'] = (
            None if row['keep_label'] == 'uncertain' else result['final']['verdict'] == row['keep_label']
        )
        results.append(result)
    return results


def _counts(rows):
    stats = {
        'families': len(rows),
        'rescued': sum(r['rescued'] for r in rows),
        'abstentions': sum(r['outcome'] == 'error_keep' for r in rows),
    }
    for tier in ('baseline', 'final'):
        for verdict in ('keep', 'discard'):
            stats[f'{tier}_{verdict}'] = sum(r[tier]['verdict'] == verdict for r in rows)
        stats[f'{tier}_false_discard'] = sum(
            r['keep_label'] == 'keep' and r[tier]['verdict'] == 'discard' for r in rows
        )
        stats[f'{tier}_false_keep'] = sum(r['keep_label'] == 'discard' and r[tier]['verdict'] == 'keep' for r in rows)
    for metric in ('false_discard', 'false_keep'):
        stats[f'{metric}_delta'] = stats[f'final_{metric}'] - stats[f'baseline_{metric}']
    stats['labeled_keep'] = sum(r['keep_label'] == 'keep' for r in rows)
    stats['labeled_discard'] = sum(r['keep_label'] == 'discard' for r in rows)
    stats['uncertain'] = sum(r['keep_label'] == 'uncertain' for r in rows)
    stats['agreements'] = sum(r['agreement'] is True for r in rows)
    for tier in ('baseline', 'final'):
        for metric, denominator in [('false_discard', 'labeled_keep'), ('false_keep', 'labeled_discard')]:
            stats[f'{tier}_{metric}_rate'] = (
                stats[f'{tier}_{metric}'] / stats[denominator] if stats[denominator] else None
            )
    return stats


def summarize(results):
    matrix = []
    for rule in sorted({rule for row in results for rule in row['rule_ids']}):
        for label in ('keep', 'discard', 'uncertain'):
            rows = [r for r in results if rule in r['rule_ids'] and r['keep_label'] == label]
            if rows:
                matrix.append(dict(rule=rule, label=label, **_counts(rows)))
    counterfactual = [
        dict(
            row,
            **row['without_calendar'],
            agreement=(
                None
                if row['keep_label'] == 'uncertain'
                else row['without_calendar']['final']['verdict'] == row['keep_label']
            ),
        )
        for row in results
        if 'without_calendar' in row
    ]
    return {
        'label_status': LABEL_STATUS,
        'totals': _counts(results),
        'matrix': matrix,
        'R16_without_calendar': _counts(counterfactual),
    }


def print_summary(summary):
    print(f"Synthetic {summary['scoring']} replay; provisional agent labels; NOT population accuracy.")
    print('rule label     families baseline(K/D) final(K/D) rescued FD_delta FK_delta')
    for cell in summary['matrix']:
        print(
            f"{cell['rule']} {cell['label']:9} {cell['families']:8} "
            f"{cell['baseline_keep']:3}/{cell['baseline_discard']:<3}       "
            f"{cell['final_keep']:3}/{cell['final_discard']:<3}    {cell['rescued']:7} "
            f"{cell['false_discard_delta']:8} {cell['false_keep_delta']:8}"
        )
    print('totals:', json.dumps(summary['totals'], sort_keys=True))
    print('R16 without calendar:', json.dumps(summary['R16_without_calendar'], sort_keys=True))


def run(client, *, fixtures=FIXTURES, output=HERE / '.outputs'):
    rows = load_fixtures(fixtures)
    results = evaluate(rows, client)
    summary = summarize(results)
    summary['scoring'] = getattr(client, 'scoring', 'mock')
    summary['pins'] = {
        'base_head': BASE_HEAD,
        'model': runtime()['config.jev_decisions'].JEV_MODEL,
        'question': runtime()['utils.conversations.relevance_jev'].QUESTION_VERSION,
        'threshold': 0.80,
        'ambiguous_model_fake': 'keep',
        'fixture_sha256': hashlib.sha256(Path(fixtures).read_bytes()).hexdigest(),
        'source_sha256': {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in [
                'backend/utils/conversations/relevance.py',
                'backend/utils/conversations/relevance_rules.py',
                'backend/utils/conversations/relevance_jev.py',
                'backend/utils/conversations/relevance_rescue.py',
            ]
        },
    }
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'results.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in results))
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print_summary(summary)
    print(f'Wrote {len(results)} families to {output / "results.jsonl"}')
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', type=Path, default=FIXTURES)
    parser.add_argument('--output', type=Path, default=HERE / '.outputs')
    parser.add_argument('--mock-scores', type=Path, help='JSON object: family ID -> P(discard), null, or "error"')
    args = parser.parse_args(argv)
    scores = (
        json.loads(args.mock_scores.read_text())
        if args.mock_scores
        else {
            f'{rule}-{i:02}': [0.79, 0.80, 0.9, None, 'error'][i % 5]
            for rule in ('R03', 'R08', 'R16')
            for i in range(1, 31)
        }
    )
    run(MockJevClient(scores), fixtures=args.fixtures, output=args.output)


if __name__ == '__main__':
    main()
