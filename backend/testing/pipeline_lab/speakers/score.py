"""Speaker scorecards: production's own scorer (``utils.stt.diarization_eval``) on lab truth, plus owner precision.

Truth is per word: the corpus words (on the audio clock) take the truth turn they overlap, through the product's
``assign_words``. Predicted turns are what an arm persisted (segments with ``speaker_id``, ``is_user``,
``person_id``). Numbers only: a scorecard never carries text, names or ids.

Metrics, per conversation and pooled (sums, never averages of rates):

- ``attribution``: Hungarian 1:1 word accuracy of the voices (who spoke with whom), identity-blind;
- ``owner_precision`` / ``owner_recall``: words labelled as the owner that the owner spoke / owner words labelled so;
- ``named_accuracy``: words of enrolled truth speakers (owner and enrolled people) carrying the right identity;
- ``wrong_name_rate``: words labelled with a wrong person or wrongly as the owner, over all scored words;
- ``named_coverage``: words carrying any identity;
- ``speaker_count_error``: predicted voices minus truth voices.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Optional

IGNORED = {None, '', 'unsure', 'noise', 'mixed'}
UNKNOWN_IDENTITY = '?'
COUNTS = (
    'words',
    'attributed_correct',
    'owner_claimed',
    'owner_claimed_correct',
    'owner_truth',
    'owner_truth_found',
    'enrolled_words',
    'enrolled_correct',
    'wrong_name_words',
    'named_words',
)


def truth_words(words: list[dict], truth: dict) -> list[dict]:
    from utils.conversations.final_pass_assignment import assign_words
    from utils.stt.diarization_turns import exclusive_from_activity

    turns = [t for t in truth.get('turns') or [] if t['end'] > t['start']]
    exclusive = exclusive_from_activity(turns) if turns else []
    rows = [{'timestamp': [w['start'], w['end']], 'text': w.get('text', '')} for w in words]
    assigned = assign_words(rows, exclusive) if exclusive else [{**r, 'speaker': None} for r in rows]
    return [
        {'start': w['timestamp'][0], 'end': w['timestamp'][1], 'speaker': w['speaker'], 'text': w['text']}
        for w in assigned
    ]


def identity_table(truth: dict) -> dict[str, dict]:
    table = {}
    for label, identity in (truth.get('identities') or {}).items():
        if identity == 'user':
            table[label] = {'is_user': True}
        elif identity:
            table[label] = {'person_id': identity}
    return table


def _claim(turn: Optional[dict]) -> Optional[str]:
    if turn is None:
        return None
    if turn.get('is_user'):
        return 'user'
    return turn.get('person_id') or None


def _voice(turn: Optional[dict]) -> Optional[str]:
    """An opaque voice key for scoring (never display text): the persisted id within its scope."""
    if turn is None:
        return None
    if turn.get('speaker_id') is not None:
        return json.dumps([turn.get('speaker_id_scope') or '', turn['speaker_id']])
    return turn.get('speaker')


def score_conversation(words: list[dict], truth: dict, turns: list[dict], scope: Optional[set] = None) -> dict:
    """One conversation's counts and rates. ``turns`` are predicted segments on the audio clock. ``scope``
    (word indexes) limits scoring to the words the conversation owns, the same set for every arm."""
    from utils.stt.diarization_eval import persisted_word_turns, score_words

    reference = truth_words(words, truth)
    identities = truth.get('identities') or {}
    valid = sorted(
        (t for t in turns if t['end'] > t['start']), key=lambda t: (t['start'], t['end'])
    )  # zero-length point words cannot hold a word
    chosen = persisted_word_turns(reference, valid) if valid else [None] * len(reference)
    counts = dict.fromkeys(COUNTS, 0)
    pairs = []
    for position, (word, index) in enumerate(zip(reference, chosen)):
        label = word['speaker']
        if label in IGNORED or (scope is not None and position not in scope):
            continue
        turn = valid[index] if index is not None else None
        claim, expected = _claim(turn), identities.get(label)
        counts['words'] += 1
        pairs.append(({'speaker': label}, _voice(turn)))
        if expected == UNKNOWN_IDENTITY:  # silver voice of uncertain identity: attribution only
            continue
        counts['named_words'] += claim is not None
        counts['owner_claimed'] += claim == 'user'
        counts['owner_claimed_correct'] += claim == 'user' and expected == 'user'
        counts['owner_truth'] += expected == 'user'
        counts['owner_truth_found'] += expected == 'user' and claim == 'user'
        counts['enrolled_words'] += expected is not None
        counts['enrolled_correct'] += expected is not None and claim == expected
        counts['wrong_name_words'] += claim is not None and claim != expected
    oracle = score_words([p[0] for p in pairs], [p[1] for p in pairs]) if pairs else None
    counts['attributed_correct'] = oracle['correct_1to1'] if oracle else 0
    truth_voices = len(
        {w['speaker'] for i, w in enumerate(reference) if w['speaker'] not in IGNORED and (scope is None or i in scope)}
    )
    if scope is None:
        # Every output voice, unaligned turns included: counting only matched words would hide over-splitting.
        predicted_voices = len({_voice(t) for t in valid if _voice(t) is not None})
    else:  # the voices that hold any of the conversation's own words
        held = {chosen[i] for i in scope if i < len(chosen) and chosen[i] is not None}
        predicted_voices = len({_voice(valid[i]) for i in held if _voice(valid[i]) is not None})
    card = {**counts, **rates(counts)}
    card['truth_voices'] = truth_voices
    card['predicted_voices'] = predicted_voices
    card['speaker_count_error'] = predicted_voices - truth_voices
    return card


def _ratio(a: int, b: int) -> Optional[float]:
    return round(a / b, 4) if b else None


def rates(counts: dict) -> dict:
    return {
        'attribution': _ratio(counts['attributed_correct'], counts['words']),
        'owner_precision': _ratio(counts['owner_claimed_correct'], counts['owner_claimed']),
        'owner_recall': _ratio(counts['owner_truth_found'], counts['owner_truth']),
        'named_accuracy': _ratio(counts['enrolled_correct'], counts['enrolled_words']),
        'wrong_name_rate': _ratio(counts['wrong_name_words'], counts['words']),
        'named_coverage': _ratio(counts['named_words'], counts['words']),
    }


def pool(cards: Iterable[dict]) -> dict:
    cards = [c for c in cards if c]
    counts = {key: sum(c[key] for c in cards) for key in COUNTS}
    errors = [abs(c['speaker_count_error']) for c in cards]
    return {
        **counts,
        **rates(counts),
        'conversations': len(cards),
        'speaker_count_within_one': sum(e <= 1 for e in errors),
        'mean_abs_speaker_count_error': round(sum(errors) / len(errors), 3) if errors else None,
    }


def agreement(words: list[dict], left: list[dict], right: list[dict]) -> dict[str, Any]:
    """Two arms against each other when there is no truth: identity-blind voice agreement and identity agreement."""
    pseudo = {
        'turns': [
            {'start': t['start'], 'end': t['end'], 'speaker': str(_voice(t))} for t in left if t['end'] > t['start']
        ]
    }
    pseudo['identities'] = {str(_voice(t)): _claim(t) for t in left if t['end'] > t['start']}
    card = score_conversation(words, pseudo, right)
    return {
        'voice_agreement': card['attribution'],
        'identity_agreement': card['named_accuracy'],
        'words': card['words'],
    }
