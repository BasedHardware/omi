#!/usr/bin/env python3
"""Blind code-judge eval for propose_message user voice (see evals/user_voice/README.md)."""

import argparse
import json
import random
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from utils.llm.user_voice import (  # noqa: E402
    RARE_ENDING_PERCENT,
    UserVoiceProfile,
    allowed_exclamations,
    build_profile,
    letter_scripts,
    line_ending,
    polish_draft,
)

FIXTURES = BACKEND / 'evals' / 'user_voice' / 'fixtures.json'
RESULTS = BACKEND / 'evals' / 'user_voice' / 'results.json'
SEED = 23541


def mark_mismatches(line: str, profile: UserVoiceProfile) -> int:
    """How many of the line's marks the user would not use with this person."""
    misses = 0
    ending = line_ending(line)
    if ending and ending in ('.', '!') and profile.endings.get(ending, 0) < RARE_ENDING_PERCENT:
        misses += 1
    if sum(line.count(c) for c in '!！') > allowed_exclamations(profile):
        misses += 1
    scripts = letter_scripts(line)
    if scripts and profile.scripts.get(scripts.most_common(1)[0][0], 0) < 20:
        misses += 1
    if profile.emoji_rate == 0 and line_ending(line) == 'emoji':
        misses += 1
    return misses


def spot_rate(pairs: list[tuple[str, str]], profile: UserVoiceProfile, rng: random.Random) -> float:
    """Share of pairs where the blind judge picks the draft; a tie counts as a coin flip."""
    score = 0.0
    for real, draft in pairs:
        shown = [('real', real), ('draft', draft)]
        rng.shuffle(shown)
        (label_a, a), (label_b, b) = shown
        miss_a, miss_b = mark_mismatches(a, profile), mark_mismatches(b, profile)
        if miss_a == miss_b:
            score += 0.5
        elif (label_a if miss_a > miss_b else label_b) == 'draft':
            score += 1
    return score / len(pairs)


def run() -> dict:
    data = json.loads(FIXTURES.read_text(encoding='utf-8'))
    rng = random.Random(SEED)
    report = {'people': [], 'pairs': 0}
    before_total = after_total = 0.0
    for person in data['people']:
        profile = build_profile(person['id'], person['name'], person['user_lines'], [])
        polished = [polish_draft(d, profile).text for d in person['drafts']]
        raw_pairs = [(real, draft) for real in person['held_out'] for draft in person['drafts']]
        polished_pairs = [(real, draft) for real in person['held_out'] for draft in polished]
        before = spot_rate(raw_pairs, profile, rng)
        after = spot_rate(polished_pairs, profile, rng)
        before_total += before * len(raw_pairs)
        after_total += after * len(polished_pairs)
        report['pairs'] += len(raw_pairs)
        report['people'].append(
            {
                'person': person['id'],
                'spotted_before': round(before, 2),
                'spotted_after': round(after, 2),
                'polished': dict(zip(person['drafts'], polished)),
            }
        )
    report['spotted_before'] = round(before_total / report['pairs'], 2)
    report['spotted_after'] = round(after_total / report['pairs'], 2)
    report['pass'] = report['spotted_after'] <= 0.5 and report['spotted_after'] < report['spotted_before']
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='record the run in evals/user_voice/results.json')
    args = parser.parse_args()
    report = run()
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.write:
        RESULTS.write_text(text + '\n', encoding='utf-8')
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
