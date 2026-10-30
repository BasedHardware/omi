"""Text-free per-word scoring. Truth is a list of {start, end, speaker}."""

from collections import Counter
import numpy as np
from scipy.optimize import linear_sum_assignment

from utils.conversations.final_pass_assignment import assign_words

IGNORED = {None, '', 'unsure', 'noise', 'mixed', '__unsure__', '__noise__', '__mixed__'}


def score_words(truth, predicted):
    if len(truth) != len(predicted):
        raise ValueError('word counts differ')
    pairs = [(str(t['speaker']), p) for t, p in zip(truth, predicted) if t['speaker'] not in IGNORED]
    actual = sorted({a for a, _ in pairs})
    detected = sorted({p for _, p in pairs if p is not None})
    counts = Counter(pairs)
    matrix = np.array([[counts[a, p] for a in actual] for p in detected], dtype=int)
    if actual and detected:
        row, col = linear_sum_assignment(-matrix)
        one = int(matrix[row, col].sum())
        many = int(matrix.max(axis=1).sum())
    else:
        one = many = 0
    total = len(pairs)
    return {
        'words': total,
        'correct_1to1': one,
        'correct_many_to_1': many,
        'accuracy_1to1': one / total if total else None,
        'accuracy_many_to_1': many / total if total else None,
        'truth_speakers': len(actual),
        'predicted_speakers': len(detected),
    }


def score_turns(truth, turns):
    words = [{'timestamp': [w['start'], w['end']], 'text': ''} for w in truth]
    predicted = [w['speaker'] for w in assign_words(words, turns)]
    return score_words(truth, predicted)
