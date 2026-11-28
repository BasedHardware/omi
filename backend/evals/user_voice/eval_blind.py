"""Blind evaluation for per-person ``user_voice`` drafts vs real user lines.

Given a user's historical lines to a specific person, a held-out real line, an
unstyled AI draft, and a user-voice polished draft, evaluates whether a blind
style judge can distinguish the draft from the user's real line.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, List

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from utils.llm.user_voice import (  # noqa: E402
    UserVoiceProfile,
    build_user_voice_profile,
    polish_draft_in_user_voice,
)


def style_distance_from_profile(line: str, profile: UserVoiceProfile) -> float:
    """Compute a deterministic style divergence score (0.0 = matches user voice)."""
    single_profile = build_user_voice_profile(
        messages=[line],
        person_id=profile.person_id,
        person_name=profile.person_name,
        recipient=profile.recipient,
    )
    penalty = 0.0
    if single_profile.dominant_ending != profile.dominant_ending:
        penalty += 1.0
    excl_count = line.count('!')
    if excl_count > profile.max_exclamations_per_line:
        penalty += 1.0 * (excl_count - profile.max_exclamations_per_line)
    if profile.emoji_rate == 0.0 and single_profile.emoji_rate > 0.0:
        penalty += 1.0
    if (profile.lowercase_start_rate >= 0.7) != (single_profile.lowercase_start_rate >= 0.7):
        penalty += 0.5
    return round(penalty, 3)


def evaluate_fixtures(fixtures_path: Path) -> Dict[str, Any]:
    cases: List[Dict[str, Any]] = json.loads(fixtures_path.read_text(encoding='utf-8'))
    results: List[Dict[str, Any]] = []
    unstyled_detected = 0
    polished_indistinguishable = 0

    for case in cases:
        profile = build_user_voice_profile(
            messages=case['history'],
            person_id=case['person_id'],
            person_name=case['person_name'],
            recipient=case['recipient'],
        )
        real_line = case['real_held_out_line']
        unstyled = case['ai_unstyled_draft']
        polished = polish_draft_in_user_voice(case['voice_seeded_draft'], profile)

        real_dist = style_distance_from_profile(real_line, profile)
        unstyled_dist = style_distance_from_profile(unstyled, profile)
        polished_dist = style_distance_from_profile(polished, profile)

        # A blind judge flags the candidate with strictly higher style divergence than the real line.
        judge_flags_unstyled = unstyled_dist > real_dist
        judge_cannot_tell_polished = polished_dist <= real_dist

        if judge_flags_unstyled:
            unstyled_detected += 1
        if judge_cannot_tell_polished:
            polished_indistinguishable += 1

        results.append(
            {
                'id': case['id'],
                'real_line': real_line,
                'unstyled_draft': unstyled,
                'polished_draft': polished,
                'real_distance': real_dist,
                'unstyled_distance': unstyled_dist,
                'polished_distance': polished_dist,
                'judge_flags_unstyled_as_ai': judge_flags_unstyled,
                'judge_cannot_tell_polished_from_real': judge_cannot_tell_polished,
            }
        )

    return {
        'total_cases': len(cases),
        'unstyled_detected_as_ai': unstyled_detected,
        'polished_indistinguishable_from_real': polished_indistinguishable,
        'cases': results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Run blind user_voice evaluation.')
    parser.add_argument(
        '--fixtures',
        type=Path,
        default=Path(__file__).with_name('fixtures.json'),
        help='Path to fixtures.json',
    )
    args = parser.parse_args()
    summary = evaluate_fixtures(args.fixtures)
    print(json.dumps(summary, indent=2))
    if summary['polished_indistinguishable_from_real'] != summary['total_cases']:
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
