"""Synthetic owner corpora and independent, cheap candidate shortlists."""

from __future__ import annotations

import random
import re
import time
from collections import defaultdict
from difflib import SequenceMatcher
from itertools import combinations
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from evals.dream_verifier.gateway import Routes

from evals.dream_verifier.contracts import Snapshot, digest, project
from evals.dream_verifier.generate import SEED, LONG, conversation, memory

Candidate = tuple[str, str, str]


def corpora(seed: int = SEED, count: int = 24) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    owners: list[dict[str, Any]] = []
    for _ in range(count):
        key = f'{rng.getrandbits(80):020x}'
        records = {
            'conversations/typo': conversation('typo', f'Please send the tray to Qelorri {key}.'),
            'conversations/rare': conversation('rare', f'Qelori and Qeloria are different people {key}.'),
            'conversations/a': conversation('a', LONG + key),
            'conversations/b': conversation('b', LONG + key),
            'conversations/c': conversation('c', LONG + key),
            'memory_items/old': memory('I work at Vellum Glass.', slot='workplace'),
            'memory_items/new': memory('I now work at Opal Kiln.', slot='workplace', created_at='2026-09-09T10:00:00Z'),
            'memory_items/other_slot': memory(
                'I live in Mistra Bay.', slot='home_city', created_at='2026-09-09T10:00:00Z'
            ),
            'memory_items/same': memory('I work at Vellum Glass.', slot='workplace', created_at='2026-09-09T10:00:00Z'),
            'memory_items/junk': memory('[silence] [inaudible]'),
            'memory_items/small': memory('I like small stones.'),
            'people/junk': {'name': 'um um'},
            'people/real': {'name': 'Um Vale'},
        }
        records['conversations/c'].update(started_at='2026-09-10T11:00:00Z', finished_at='2026-09-10T11:10:00Z')
        planted = [
            ('known_spelling', 'conversations/typo', 'Qelori'),
            ('duplicate_capture', 'conversations/a', 'conversations/b'),
            ('stale_fact', 'memory_items/old', 'memory_items/new'),
            ('junk', 'memory_items/junk', ''),
            ('junk', 'people/junk', ''),
        ]
        owners.append(
            {
                'id': key,
                'corpus': {'records': records, 'known_spellings': ['Qelori']},
                'planted': [list(candidate) for candidate in planted],
            }
        )
    return owners


def shortlists(corpus: dict[str, Any]) -> dict[str, set[Candidate]]:
    """Candidate hints only, never edits; intentionally retain ambiguous matches."""
    records = corpus['records']
    found: dict[str, set[Candidate]] = defaultdict(set)
    for ref, row in records.items():
        if ref.startswith('conversations/'):
            words = re.findall(r'[^\W_]+', ' '.join(s['text'] for s in row['transcript_segments']))
            for spelling in corpus['known_spellings']:
                if any(
                    word != spelling and 0.8 <= SequenceMatcher(None, word.casefold(), spelling.casefold()).ratio() < 1
                    for word in words
                ):
                    found['known_spelling'].add(('known_spelling', ref, spelling))
        text = (row.get('content') or row.get('name') or '').casefold().strip()
        if text and not re.sub(r'\[.*?\]|\b(?:um|uh|hmm)\b|[.\s]', '', text):
            found['junk'].add(('junk', ref, ''))
    conversations = [(ref, row) for ref, row in records.items() if ref.startswith('conversations/')]
    for (left_ref, left), (right_ref, right) in combinations(conversations, 2):
        # A cheap shortlist may retain nonoverlapping repeats; verifier still
        # owns exact time overlap and permission checks.
        a = ' '.join(s['text'] for s in left['transcript_segments'])
        b = ' '.join(s['text'] for s in right['transcript_segments'])
        if SequenceMatcher(None, a.casefold(), b.casefold()).ratio() >= 0.92:
            found['duplicate_capture'].add(('duplicate_capture', left_ref, right_ref))
    memories = [(ref, row) for ref, row in records.items() if ref.startswith('memory_items/')]
    for left_ref, left in memories:
        for right_ref, right in memories:
            if left_ref == right_ref or not left.get('slot') or left.get('slot') != right.get('slot'):
                continue
            if left.get('subject_entity_id') != right.get('subject_entity_id'):
                continue
            if left['created_at'] < right['created_at'] and left['content'] != right['content']:
                found['stale_fact'].add(('stale_fact', left_ref, right_ref))
    return dict(found)


def candidate_item(corpus: dict[str, Any], candidate: Candidate) -> dict[str, Any]:
    kind, target, other = candidate
    refs = [target] + ([other] if other in corpus['records'] else [])
    # Known spelling hints are untrusted evidence, not hidden oracle metadata.
    records = {ref: corpus['records'][ref] for ref in refs}
    records['dream_vocabulary/hints'] = {'spellings': corpus['known_spellings']}
    refs.append('dream_vocabulary/hints')
    item_id = digest(candidate)[:28]
    operation = {'candidate_kind': kind, 'target': target, 'other': other}
    snapshot = Snapshot(item_id, 'detection_candidate', operation, tuple(refs), records)
    verifier_input = project(snapshot)
    return {
        'id': item_id,
        'staged': {'kind': snapshot.kind, 'operation': operation, 'refs': refs, 'records': records},
        'verifier_input': verifier_input,
        'evidence_sha256': digest(verifier_input),
    }


async def evaluate_detection(*, jev: bool = False, routes: Routes | None = None) -> dict[str, Any]:
    from evals.dream_verifier.gateway import Routes, jev_call

    totals: dict[str, dict[str, Any]] = {}
    started = time.monotonic()
    for owner in corpora():
        # Ground truth never enters a candidate generator or model state.
        generated = shortlists(owner['corpus'])
        planted = {tuple(candidate) for candidate in owner['planted']}
        for kind in ('known_spelling', 'duplicate_capture', 'stale_fact', 'junk'):
            candidates = generated.get(kind, set())
            selected = candidates
            cost, unknown, calls, abstentions = 0.0, 0, 0, 0
            if jev:
                selected: set[Candidate] = set()
                for candidate in sorted(candidates):
                    outcome = await jev_call(
                        candidate_item(owner['corpus'], candidate), routes or Routes(), detection=True
                    )
                    calls += outcome.calls
                    unknown += outcome.cost_usd is None
                    cost += outcome.cost_usd or 0.0
                    abstentions += outcome.decision in {'review', 'unverified'}
                    if outcome.decision == 'agree':
                        selected.add(candidate)
            truth = {candidate for candidate in planted if candidate[0] == kind}
            row = totals.setdefault(
                kind,
                {
                    'tp': 0,
                    'fp': 0,
                    'fn': 0,
                    'planted': 0,
                    'shortlisted': 0,
                    'gateway_calls': 0,
                    'known_cost_subtotal_usd': 0.0,
                    'unknown_cost_calls': 0,
                    'abstentions': 0,
                },
            )
            row['tp'] += len(selected & truth)
            row['fp'] += len(selected - truth)
            row['fn'] += len(truth - selected)
            row['planted'] += len(truth)
            row['shortlisted'] += len(candidates)
            row['gateway_calls'] += calls
            row['known_cost_subtotal_usd'] += cost
            row['unknown_cost_calls'] += unknown
            row['abstentions'] += abstentions
    for row in totals.values():
        row['precision'] = row['tp'] / (row['tp'] + row['fp']) if row['tp'] + row['fp'] else None
        row['recall'] = row['tp'] / row['planted'] if row['planted'] else None
        row['cost_usd'] = None if row['unknown_cost_calls'] else row['known_cost_subtotal_usd']
    return {
        'arm': 'shortlist_then_jev' if jev else 'local_shortlists',
        'synthetic_owners': 24,
        'metrics': totals,
        'latency_ms_total': (time.monotonic() - started) * 1000,
        'promotion_eligible': False,
    }
