"""Deterministic, content-free privacy state-machine transitions (synthetic only)."""

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import random

from testing.replay_harness.privacy_faults import not_applicable_reason

SEED = 20261104
KINDS = {
    'deletion_marker': (
        'grace_intent',
        'grace_actions_complete',
        'restore',
        'promote',
        'wipe_intent',
        'wipe_started',
        'wipe_running',
        'wipe_completed',
        'wipe_failed',
        'billing_failed',
        'cancel',
    ),
    'tombstone': ('create', 'retry_after_purge'),
    'legal_hold': ('place', 'release', 'acquire', 'finish', 'takeover'),
    'batch_privacy': ('advance', 'block', 'finish'),
    'subscription': ('byok_enable', 'byok_disable', 'upgrade', 'downgrade'),
    'data_protection': ('enhanced_to_e2ee', 'e2ee_to_enhanced', 'finalize_migration'),
}
FAULTS = ('none', 'redis_down', 'drop_invalidation', 'begin_loss', 'concurrent', 'request_memo', 'reader_during_writer')


def generate(*, seed=SEED, transitions=1400, mix=None, faults=FAULTS):
    if type(transitions) is not int or not 1 <= transitions <= 10000:
        raise ValueError('transitions must be between 1 and 10000')
    faults = tuple(faults)
    if not faults or set(faults) - set(FAULTS):
        raise ValueError('unknown privacy fault')
    mix = dict.fromkeys(KINDS, 1) if mix is None else mix
    if not mix or set(mix) - set(KINDS) or any(type(w) is not int or not 1 <= w <= 100 for w in mix.values()):
        raise ValueError('mix must contain known families with integer weights 1..100')
    eligible_faults = {
        family: [fault for fault in faults if not not_applicable_reason(family, fault)] for family in mix
    }
    if any(not values for values in eligible_faults.values()):
        raise ValueError('each family requires an applicable fault or baseline')
    rng = random.Random(seed)
    # Coverage prefix: every kind, plus every family/fault pair, before random
    # weighted repetition. The smoke includes the entire prefix.
    rows = [(family, kind, eligible_faults[family][0]) for family in mix for kind in KINDS[family]]
    rows += [
        (family, KINDS[family][0], fault)
        for family, fault in itertools.product(mix, faults)
        if fault != eligible_faults[family][0] and not not_applicable_reason(family, fault)
    ]
    rng.shuffle(rows)
    while len(rows) < transitions:
        family = rng.choices(list(mix), weights=list(mix.values()))[0]
        rows.append((family, rng.choice(KINDS[family]), rng.choice(eligible_faults[family])))
    return {
        'privacy_cache': {
            'seed': seed,
            'transitions': [
                {'family': family, 'kind': kind, 'fault': fault} for family, kind, fault in rows[:transitions]
            ],
        }
    }


def write_case(directory, **kwargs):
    from testing.replay_harness.manifest import validate_manifest

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    timeline = generate(**kwargs)
    corpus = (json.dumps(timeline, indent=2) + '\n').encode()
    manifest = {
        'schema_version': 1,
        'id': directory.name,
        'tier': 'S',
        'scrub': 'synthetic-metadata-only',
        'created': '2026-11-05T00:00:00Z',
        'prod_evidence': {},
        'seed_blob_sha256': [hashlib.sha256(corpus).hexdigest()],
        'stages': {
            'privacy_cache': {
                'expect': 'pass',
                'min_verified_transitions': 1000 if len(timeline['privacy_cache']['transitions']) >= 1000 else 0,
            }
        },
        'notes': 'Fixed-seed synthetic privacy transitions; no production frequency or live-shadow evidence.',
    }
    validate_manifest(manifest)
    (directory / 'corpus.json').write_bytes(corpus)
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=SEED)
    parser.add_argument('--transitions', type=int, default=1400)
    parser.add_argument('--mix', type=json.loads)
    parser.add_argument('--faults', default=','.join(FAULTS))
    args = parser.parse_args()
    write_case(args.output, seed=args.seed, transitions=args.transitions, mix=args.mix, faults=args.faults.split(','))


if __name__ == '__main__':
    main()
