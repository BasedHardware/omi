"""Blind evaluation comparing real per-person user lines vs generic and user-voice drafts.

Evaluates whether drafts produced/polished with ``utils.llm.user_voice`` match
held-out real lines from the user to each person closer than generic assistant
drafts across casing, ending punctuation, exclamation rate, emoji rate, and
typical length.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from utils.llm.user_voice import (
    UserVoiceProfile,
    build_user_voice_profile,
    polish_draft_in_user_voice,
)


def compute_style_distance(candidate: str, reference_profile: UserVoiceProfile) -> float:
    """Compute a normalized style distance in [0, 1] between a draft and a reference voice profile."""
    cand_profile = build_user_voice_profile(
        reference_profile.uid,
        reference_profile.person_name,
        [candidate],
        person_key=reference_profile.person_key,
    )
    if cand_profile.sample_count == 0 or reference_profile.sample_count == 0:
        return 1.0

    # 1. Ending punctuation distance
    ending_mismatch = 0.0 if cand_profile.dominant_ending == reference_profile.dominant_ending else 1.0
    # 2. Casing distance
    casing_diff = abs(cand_profile.all_lowercase_rate - reference_profile.all_lowercase_rate)
    lower_start_diff = abs(cand_profile.lowercase_rate - reference_profile.lowercase_rate)
    # 3. Exclamation distance
    excl_diff = min(1.0, abs(cand_profile.exclamation_rate - reference_profile.exclamation_rate))
    # 4. Emoji distance
    emoji_diff = abs(cand_profile.emoji_rate - reference_profile.emoji_rate)

    return round(
        0.35 * ending_mismatch + 0.25 * casing_diff + 0.15 * lower_start_diff + 0.15 * excl_diff + 0.10 * emoji_diff,
        4,
    )


def run_blind_user_voice_eval() -> dict[str, Any]:
    """Run blind evaluation comparing held-out real lines against generic vs user-voice drafts."""
    fixtures = [
        {
            'person_name': 'Alex',
            'persona_description': 'Casual best friend — lowercase fragments, no trailing period, no exclamations',
            'training_lines': [
                'yo running 5 mins late',
                'be there soon',
                'grabbing coffee on the way',
                'you still at the spot',
                'sounds good see u in a bit',
            ],
            'held_out_real_lines': [
                'on my way now',
                'stuck in traffic be there in 10',
                'let me know when u get here',
            ],
            'generic_assistant_draft': 'Hi Alex, I am running a few minutes late! I will be there soon.',
        },
        {
            'person_name': 'Dr. Patel',
            'persona_description': 'Formal supervisor — capitalized sentences, ends with period, no exclamations or emojis',
            'training_lines': [
                'Hello Dr. Patel, I have uploaded the revised quarterly figures.',
                'Please let me know if the Thursday afternoon slot still works for you.',
                'Thank you for reviewing the draft ahead of the board meeting.',
                'I will send the updated slides before 5 PM today.',
            ],
            'held_out_real_lines': [
                'I am running about ten minutes late for our 2 PM meeting.',
                'The final report is ready for your review.',
            ],
            'generic_assistant_draft': 'i am running about ten minutes late for our 2 PM meeting! 😊',
        },
        {
            'person_name': 'Mateo',
            'persona_description': 'Spanish-speaking cousin — lowercase Spanish fragments without periods',
            'training_lines': [
                'hola mateo ya voy en camino',
                'nos vemos en la casa de mamá',
                'todo bien gracias',
                'vamos mañana temprano',
            ],
            'held_out_real_lines': [
                'ya casi llego nos vemos',
                'estoy saliendo del trabajo',
            ],
            'generic_assistant_draft': 'Hola Mateo, ya casi llego a la casa!',
        },
    ]

    cases: list[dict[str, Any]] = []
    wins = 0

    for item in fixtures:
        train_profile = build_user_voice_profile('eval-uid', item['person_name'], item['training_lines'])
        held_out_profile = build_user_voice_profile('eval-uid', item['person_name'], item['held_out_real_lines'])

        generic_draft = item['generic_assistant_draft']
        voiced_draft = polish_draft_in_user_voice(generic_draft, train_profile)

        generic_distance = compute_style_distance(generic_draft, held_out_profile)
        voiced_distance = compute_style_distance(voiced_draft, held_out_profile)
        voiced_wins = voiced_distance < generic_distance
        if voiced_wins:
            wins += 1

        cases.append(
            {
                'person_name': item['person_name'],
                'generic_draft': generic_draft,
                'voiced_draft': voiced_draft,
                'generic_distance_to_real': generic_distance,
                'voiced_distance_to_real': voiced_distance,
                'blind_preference': 'user_voice' if voiced_wins else 'generic',
            }
        )

    return {
        'total_cases': len(cases),
        'user_voice_wins': wins,
        'win_rate': round(wins / len(cases), 4) if cases else 0.0,
        'cases': cases,
    }


if __name__ == '__main__':
    report = run_blind_user_voice_eval()
    print(json.dumps(report, indent=2))
    assert report['win_rate'] == 1.0, f"Expected 100% blind eval win rate, got {report['win_rate']}"
