#!/usr/bin/env python3
"""Operator-only weekly judge-calibration export for one authorized owner.

Run in an isolated operator pod (like dream-replay.py) for the owner who agreed to
label their own Dream changes. Reads that owner's recent Dream-journaled changes,
samples them (every rare high-stakes kind first, then common kinds), judges each
with the production value judge on the same owner-visible projection, and prints
decision-mill proposal items (JSONL) to operator stdout. The owner's labels then
measure the judge's agreement. It writes nothing to product storage; decrypted
content leaves the pod only on operator stdout, into a labels directory that is
never in git.
"""

import argparse
import asyncio
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google.cloud import firestore

from config.dream_agent import dream_journal_key, enabled
from database import review_store
from utils import dream_harness_transport, dream_judge
from utils.rollout_cohorts import configure_rollout_runtime

QUESTION = 'Is the owner better off for this change Dream applied?'
POLICY = [
    'Good: correct and the owner would notice or care.',
    'Neutral: correct but not worth noticing.',
    'Harmful: wrong, misattributed to the owner, or it destroyed something the owner wanted.',
]


def changes(uid, days):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        review_store.user(uid)
        .collection('review_changes')
        .where(filter=firestore.FieldFilter('created_at', '>=', since))
        .order_by('created_at', direction='DESCENDING')
        .limit(500)
        .stream()
    )
    for snapshot in rows:
        data = review_store.decode_doc(uid, snapshot.to_dict()) or {}
        if not dream_journal_key(data.get('edit_key')) or data.get('phase', 'applied') != 'applied':
            continue
        change = data.get('change') or {}
        kind = change.get('edit_kind') or data['edit_key'].split(':')[1]
        yield kind, data, change


def sample(rows, count, seed):
    rare = [row for row in rows if row[0] in dream_judge.ALWAYS]
    common = [row for row in rows if row[0] not in dream_judge.ALWAYS]
    random.Random(seed).shuffle(common)
    return [(row, 'always') for row in rare[:count]] + [(row, 'random') for row in common[: max(0, count - len(rare))]]


def item(kind, data, change, stratum, judgment):
    projection = dream_judge.projection(change)
    context = projection['context']
    evidence = []
    if context:
        speech = ' '.join(part for part in (context.get('before'), context.get('quote'), context.get('after')) if part)
        evidence.append({'title': 'Cited speech', 'tag': 'Context', 'text': speech})
    if projection['refs']:
        evidence.append({'title': 'Records involved', 'tag': 'Refs', 'text': '\n'.join(projection['refs'])})
    return {
        'id': change.get('change_id') or data.get('edit_key'),
        'stratum': stratum,
        'title': kind.replace('_', ' ').capitalize(),
        'meta': {'applied_at': str(data.get('created_at')), 'source': kind},
        'content': {
            'type': 'proposal',
            'question': QUESTION,
            'change': {
                'kind': kind.replace('_', ' ').capitalize(),
                'before': change.get('before') or '',
                'after': change.get('after') or '',
            },
            'evidence': evidence,
            'policy': POLICY,
        },
        'hidden': {
            'judge': {
                'verdict': judgment.verdict if judgment else None,
                'grounded': judgment.grounded if judgment else None,
                'owner_appropriate': judgment.owner_appropriate if judgment else None,
                'useful': judgment.useful if judgment else None,
            },
            'undone': bool(change.get('undone')),
        },
    }


async def judged(uid, rows):
    async def turn(mount, messages):
        return await dream_harness_transport.model_turn(uid, dream_harness_transport.VERIFY_LANE, mount, messages)

    verdicts = {}
    for start in range(0, len(rows), dream_judge.MAX_ITEMS):
        chunk = rows[start : start + dream_judge.MAX_ITEMS]
        batch = [(str(index), dream_judge.projection(row[0][2])) for index, row in enumerate(chunk, start)]
        verdicts.update(
            await dream_judge.judge(batch, turn, tokens=dream_judge.token_allowance(), deadline_seconds=180)
        )
    return verdicts


def main():
    configure_rollout_runtime()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uid', required=True, help='The authorized owner labeling their own changes')
    parser.add_argument('--days', type=int, default=7)
    parser.add_argument('--count', type=int, default=30)
    parser.add_argument('--no-judge', action='store_true', help='Export items without judge verdicts')
    args = parser.parse_args()
    if not enabled():
        parser.error('DREAM_AGENT_ENABLED must be true; the global kill switch also stops exports')
    week = datetime.now(timezone.utc).strftime('%G-W%V')
    rows = sample(list(changes(args.uid, args.days)), args.count, seed=week)
    verdicts = {} if args.no_judge else asyncio.run(judged(args.uid, rows))
    for index, ((kind, data, change), stratum) in enumerate(rows):
        # Deliberate operator stdout into a labels directory, never a log or metric.
        print(json.dumps(item(kind, data, change, stratum, verdicts.get(str(index))), ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()
