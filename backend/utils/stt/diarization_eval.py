"""Text-free per-word scoring. Truth is a list of {start, end, speaker}."""

from collections import Counter
from typing import Any
import numpy as np
from scipy.optimize import linear_sum_assignment

from utils.conversations.final_pass_assignment import assign_words

IGNORED = {None, '', 'unsure', 'noise', 'mixed', '__unsure__', '__noise__', '__mixed__'}


def score_words(truth, predicted) -> dict[str, Any]:
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


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def _identity(row):
    """Only explicit persisted identity claims count; a channel/name is never an identity."""
    if row.get('is_user') is True:
        if row.get('person_id'):
            raise ValueError('ambiguous declared identity')
        return ('owner',)
    if row.get('person_id'):
        return ('person', str(row['person_id']))
    return None


def _voice(turn):
    # Persisted integer IDs have already passed the conversation allocator.
    # Unit scopes remain provenance and must not split a linked canonical ID.
    if isinstance(turn.get('speaker_id'), int) and not isinstance(turn['speaker_id'], bool):
        return ('conversation', str(turn['speaker_id']))
    voice_id = turn.get('speaker')
    if voice_id is None:
        return None
    scope = turn.get('speaker_id_scope') or turn.get('speaker_scope') or turn.get('scope') or ''
    return (str(scope), str(voice_id))


def _tokens(text):
    # Same normalization as diarizer.batch_pipeline_benchmark.tokens, without
    # importing its GPU/model runtime into this pure, CPU-only scorer.
    import re

    return re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", text.lower())


def _alignment(reference, hypothesis):
    """Deterministic Levenshtein alignment; substitutions, deletions, insertions."""
    # One byte per cell for traceback, rather than a Python integer matrix.
    # This keeps full-recording evaluation bounded in memory on local CPUs.
    width = len(hypothesis) + 1
    directions = [bytearray([2] * width)]
    row = list(range(width))
    for i, left in enumerate(reference, 1):
        following, direction = [i], bytearray(width)
        direction[0] = 1
        for j, right in enumerate(hypothesis, 1):
            choices = (row[j - 1] + (left != right), row[j] + 1, following[-1] + 1)
            best = min(choices)
            following.append(best)
            direction[j] = choices.index(best)
        directions.append(direction)
        row = following
    i, j = len(reference), len(hypothesis)
    counts = {'substitutions': 0, 'deletions': 0, 'insertions': 0, 'matches': 0}
    aligned = set()
    while i or j:
        if i and j and directions[i][j] == 0:
            counts['matches' if reference[i - 1] == hypothesis[j - 1] else 'substitutions'] += 1
            aligned.add(i - 1)
            i, j = i - 1, j - 1
        elif i and directions[i][j] == 1:
            counts['deletions'] += 1
            i -= 1
        else:
            counts['insertions'] += 1
            j -= 1
    return counts, aligned


def model_reference_wer(reference, hypothesis):
    """Model disagreement diagnostic, never human-reference WER or identity truth."""
    left, right = _tokens(reference), _tokens(hypothesis)
    counts, _ = _alignment(left, right)
    errors = sum(counts[k] for k in ('substitutions', 'deletions', 'insertions'))
    return {
        'status': 'EVALUATED' if left else 'NOT_EVALUATED',
        'reference_kind': 'model_reference_not_truth',
        'reference_tokens': len(left),
        'hypothesis_tokens': len(right),
        **counts,
        'wer': _ratio(errors, len(left)),
    }


def persisted_word_turns(truth, turns):
    """Choose persisted turns by overlap, including legacy overlapping groups.

    A transcript group can span another group's clock even when the underlying
    diarizer was exclusive. Preserve those actual groups and their identities;
    never repair output or fit channels to the reference labels for scoring.
    Ties use midpoint containment and then the earliest start/end/input index.
    """
    from math import isfinite

    ordered = sorted(enumerate(turns), key=lambda row: (row[1]['start'], row[1]['end'], row[0]))
    if any(not isfinite(float(t[k])) or t['end'] <= t['start'] for _, t in ordered for k in ('start', 'end')):
        raise ValueError('invalid persisted turn clock')
    selected = []
    for word in truth:
        left, right = float(word['start']), float(word['end'])
        if not isfinite(left) or not isfinite(right) or right < left:
            raise ValueError('invalid reference word clock')
        candidates = []
        for rank, (index, turn) in enumerate(ordered):
            if turn['start'] > right:
                break
            overlap = min(right, turn['end']) - max(left, turn['start'])
            if overlap > 0 or (left == right and turn['start'] <= left < turn['end']):
                midpoint = (left + right) / 2
                candidates.append((overlap, turn['start'] <= midpoint < turn['end'], -rank, index))
        selected.append(max(candidates)[-1] if candidates else None)
    return selected


def score_recording(truth, turns, identity_table, *, crop_start=0.0, excluded_spans=(), model_reference=None):
    """Score fixed reference word clocks against actual persisted, exclusive turns.

    Truth rows: {start, end, speaker, text?}. Turn rows: {start, end,
    speaker, speaker_scope?, is_user?, person_id?, text?}. Truth clocks and
    excluded spans are recording-relative; turns are crop-relative and shifted
    by crop_start. Identity table maps truth labels to explicit {is_user: True}
    or {person_id: ...} declarations, made independently before scoring.
    Returns aggregates only. Never emit labels, names, transcript or identifiers.
    """
    from math import isfinite

    crop_start = float(crop_start)
    if not isfinite(crop_start):
        raise ValueError('invalid crop offset')
    spans = [(float(s), float(e)) for s, e in excluded_spans]
    if any(not isfinite(s) or not isfinite(e) or e <= s for s, e in spans):
        raise ValueError('invalid exclusion span')
    identities = {str(k): _identity(v) for k, v in identity_table.items()}
    if any(value is None for value in identities.values()):
        raise ValueError('identity declarations require explicit owner or person')
    shifted = [
        {'start': float(t['start']) + crop_start, 'end': float(t['end']) + crop_start, 'speaker': i}
        for i, t in enumerate(turns)
    ]
    # Unique temporary indices retain each turn's actual identity metadata even
    # when the same voice is named differently across persisted turns.
    predicted_indices = persisted_word_turns(truth, shifted)
    scored = []
    ignored = enrollment_excluded = 0
    for word, index in zip(truth, predicted_indices):
        if word['speaker'] in IGNORED:
            ignored += 1
        elif any(
            (float(word['start']) < e and float(word['end']) > s)
            or (float(word['start']) == float(word['end']) and s <= float(word['start']) < e)
            for s, e in spans
        ):
            enrollment_excluded += 1
        else:
            scored.append((word, index))
    total = len(scored)
    correct = enrolled_correct = enrolled_total = named = wrong_name = false_owner = abstentions = 0
    predicted_voices, anonymous_voices = set(), set()
    oracle_predictions = []
    for word, index in scored:
        expected = identities.get(str(word['speaker']))
        claim = _identity(turns[index]) if index is not None else None
        match = expected is not None and claim == expected
        correct += match
        enrolled_total += expected is not None
        enrolled_correct += match
        named += claim is not None
        abstentions += claim is None
        wrong_name += claim is not None and claim[0] == 'person' and not match
        false_owner += claim == ('owner',) and not match
        voice = _voice(turns[index]) if index is not None else None
        oracle_predictions.append(repr(voice) if voice is not None else None)
    # Count every output voice, including hallucinated/unaligned turns. Counting
    # only the best-overlap word assignments can hide over-segmentation.
    if total:
        for index, turn in enumerate(turns):
            clock = shifted[index]
            if any(s <= clock['start'] and clock['end'] <= e for s, e in spans):
                continue
            voice = _voice(turn)
            if voice is not None:
                predicted_voices.add(voice)
                if _identity(turn) is None:
                    anonymous_voices.add(voice)
    oracle = score_words([w for w, _ in scored], oracle_predictions)
    text_available = bool(scored) and all('text' in w for w, _ in scored) and all('text' in t for t in turns)
    alignment = {'status': 'NOT_EVALUATED', 'reference_words': total}
    if text_available:
        ref_tokens, word_tokens = [], []
        for word, _ in scored:
            indices = set(range(len(ref_tokens), len(ref_tokens) + len(_tokens(word['text']))))
            word_tokens.append(indices)
            ref_tokens.extend(_tokens(word['text']))
        # Keep unaligned output text too: dropping whole hypothesis turns here
        # would hide hallucinations/insertions from the end-to-end diagnostic.
        hypothesis = _tokens(
            ' '.join(turns[i]['text'] for i in sorted(range(len(turns)), key=lambda i: shifted[i]['start']))
        )
        counts, aligned = _alignment(ref_tokens, hypothesis)
        covered = sum(bool(indices) and indices <= aligned for indices in word_tokens)
        alignment = {
            'status': 'EVALUATED' if ref_tokens else 'NOT_EVALUATED',
            'reference_words': total,
            'reference_tokens': len(ref_tokens),
            'hypothesis_tokens': len(hypothesis),
            'aligned_words': covered,
            'aligned_word_coverage': _ratio(covered, total),
            **counts,
        }
    error_count = wrong_name + false_owner
    count_ok = abs(len(predicted_voices) - oracle['truth_speakers']) <= 1
    enrolled_accuracy = _ratio(enrolled_correct, enrolled_total)
    gate = enrolled_accuracy is not None and enrolled_accuracy >= 0.9 and count_ok and error_count <= 0.01 * total
    return {
        'status': 'EVALUATED' if total else 'NOT_EVALUATED',
        'words': total,
        'input_words': len(truth),
        'ignored_words': ignored,
        'enrollment_excluded_words': enrollment_excluded,
        'scored_word_coverage': _ratio(total, len(truth)),
        'strict_all_word_correct': correct,
        'strict_all_word_accuracy': _ratio(correct, total),
        'owner_enrolled_words': enrolled_total,
        'owner_enrolled_correct': enrolled_correct,
        'owner_enrolled_accuracy': enrolled_accuracy,
        'owner_enrolled_coverage': _ratio(enrolled_total, total),
        'named_words': named,
        'named_word_coverage': _ratio(named, total),
        'abstention_words': abstentions,
        'wrong_name_words': wrong_name,
        'false_owner_words': false_owner,
        'wrong_name_false_owner_rate': _ratio(error_count, total),
        'truth_voices': oracle['truth_speakers'],
        'predicted_voices': len(predicted_voices),
        'anonymous_voices': len(anonymous_voices),
        'speaker_count_within_one': count_ok if total else None,
        'hungarian_oracle_diagnostic': oracle,
        'end_to_end_alignment': alignment,
        'model_reference_wer': (
            model_reference_wer(model_reference, ' '.join(t.get('text', '') for t in turns))
            if model_reference is not None
            else {'status': 'NOT_EVALUATED', 'reference_kind': 'model_reference_not_truth'}
        ),
        'engineering_gate': 'PASS' if gate else ('FAIL' if total and enrolled_total else 'NOT_EVALUATED'),
    }


def aggregate_scorecards(results):
    """Pool counts, requiring the speaker-count constraint on every recording."""
    results = list(results)
    keys = (
        'words',
        'input_words',
        'ignored_words',
        'enrollment_excluded_words',
        'strict_all_word_correct',
        'owner_enrolled_words',
        'owner_enrolled_correct',
        'named_words',
        'abstention_words',
        'wrong_name_words',
        'false_owner_words',
    )
    pooled: dict[str, Any] = {key: sum(r[key] for r in results) for key in keys}
    total, enrolled = pooled['words'], pooled['owner_enrolled_words']
    pooled.update(
        recordings=len(results),
        scored_recordings=sum(r['words'] > 0 for r in results),
        strict_all_word_accuracy=_ratio(pooled['strict_all_word_correct'], total),
        owner_enrolled_accuracy=_ratio(pooled['owner_enrolled_correct'], enrolled),
        owner_enrolled_coverage=_ratio(enrolled, total),
        named_word_coverage=_ratio(pooled['named_words'], total),
        wrong_name_false_owner_rate=_ratio(pooled['wrong_name_words'] + pooled['false_owner_words'], total),
        failure_count=sum(r['engineering_gate'] == 'FAIL' for r in results),
    )
    eligible = bool(results) and all(r['status'] == 'EVALUATED' and r['owner_enrolled_words'] for r in results)
    passed = (
        eligible
        and pooled['owner_enrolled_accuracy'] >= 0.9
        and all(r['speaker_count_within_one'] for r in results)
        and pooled['wrong_name_false_owner_rate'] <= 0.01
    )
    pooled['engineering_gate'] = 'PASS' if passed else ('FAIL' if eligible else 'NOT_EVALUATED')
    oracle: dict[str, Any] = {
        key: sum(r['hungarian_oracle_diagnostic'][key] for r in results)
        for key in ('words', 'correct_1to1', 'correct_many_to_1')
    }
    oracle['accuracy_1to1'] = _ratio(oracle['correct_1to1'], oracle['words'])
    oracle['accuracy_many_to_1'] = _ratio(oracle['correct_many_to_1'], oracle['words'])
    pooled['hungarian_oracle_diagnostic'] = oracle
    for key in ('end_to_end_alignment', 'model_reference_wer'):
        rows = [r[key] for r in results]
        if not rows or any(r['status'] != 'EVALUATED' for r in rows):
            pooled[key] = {'status': 'NOT_EVALUATED'}
            continue
        metrics = ('reference_tokens', 'hypothesis_tokens', 'substitutions', 'deletions', 'insertions', 'matches')
        summary: dict[str, Any] = {metric: sum(r[metric] for r in rows) for metric in metrics}
        summary['status'] = 'EVALUATED'
        if key == 'end_to_end_alignment':
            summary['reference_words'] = sum(r['reference_words'] for r in rows)
            summary['aligned_words'] = sum(r['aligned_words'] for r in rows)
            summary['aligned_word_coverage'] = _ratio(summary['aligned_words'], summary['reference_words'])
        else:
            summary['reference_kind'] = 'model_reference_not_truth'
            summary['wer'] = _ratio(
                sum(summary[k] for k in ('substitutions', 'deletions', 'insertions')), summary['reference_tokens']
            )
        pooled[key] = summary
    return pooled
