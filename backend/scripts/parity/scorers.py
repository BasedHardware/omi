"""Pure scorers shared by the parity gate and the quality corpus.

Text and speaker labels stay in memory. Every function returns aggregate
numbers only, so callers can put the result in a report without leaking
content.
"""

from __future__ import annotations

from collections import Counter
import math
import re
from typing import Any, Iterable, Mapping, Sequence
import unicodedata

import numpy as np
from scipy.optimize import linear_sum_assignment

try:
    import jiwer  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - jiwer is in the backend and batch-image locks
    jiwer = None

_PUNCT = re.compile(r"[^\w\s']", re.UNICODE)
_SPACE = re.compile(r'\s+')
# Fillers that both pipelines may or may not emit; neither should be charged.
_FILLERS = frozenset({'uh', 'um', 'erm', 'hmm', 'mm', 'mhm', 'ah', 'eh', 'uhm'})


def normalize_text(text: str) -> str:
    """Contract (j) "jiwer, normalized": NFKC, lowercase, no punctuation, no fillers."""
    text = unicodedata.normalize('NFKC', text or '').lower().replace('’', "'")
    text = _PUNCT.sub(' ', text)
    tokens = [t.strip("'") for t in _SPACE.split(text)]
    return ' '.join(t for t in tokens if t and t not in _FILLERS)


def word_errors(reference: str, hypothesis: str) -> tuple[int, int]:
    """Return ``(edit_errors, reference_words)`` on normalized text.

    Uses jiwer when importable (the contract's tool) and an identical
    Levenshtein fallback otherwise, so CI and the GPU image agree.
    """
    ref = normalize_text(reference).split()
    hyp = normalize_text(hypothesis).split()
    if not ref:
        return len(hyp), 0
    if jiwer is None:  # pragma: no cover
        return _levenshtein(ref, hyp), len(ref)
    try:
        out = jiwer.process_words(' '.join(ref), ' '.join(hyp) if hyp else '')
    except ValueError:
        # jiwer rejects an empty hypothesis on some versions: every reference word is a deletion.
        return len(ref), len(ref)
    return int(out.substitutions + out.deletions + out.insertions), len(ref)


def _levenshtein(ref: Sequence[str], hyp: Sequence[str]) -> int:
    previous = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        current = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            current[j] = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (r != h))
        previous = current
    return previous[-1]


def pooled_wer(pairs: Iterable[tuple[str, str]]) -> dict[str, Any]:
    """Pooled WER: total errors over total reference words (never a mean of rates)."""
    errors = words = items = 0
    for reference, hypothesis in pairs:
        e, n = word_errors(reference, hypothesis)
        errors, words, items = errors + e, words + n, items + 1
    return {'items': items, 'errors': errors, 'reference_words': words, 'wer': errors / words if words else None}


def percentile(values: Sequence[float], q: float) -> float | None:
    """Nearest-rank percentile (q in [0, 100]); None for an empty sample."""
    clean = sorted(float(v) for v in values if v is not None and math.isfinite(float(v)))
    if not clean:
        return None
    rank = max(1, math.ceil(q / 100.0 * len(clean)))
    return clean[min(rank, len(clean)) - 1]


def median(values: Sequence[float]) -> float | None:
    clean = sorted(float(v) for v in values if v is not None and math.isfinite(float(v)))
    if not clean:
        return None
    mid = len(clean) // 2
    return clean[mid] if len(clean) % 2 else (clean[mid - 1] + clean[mid]) / 2


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def align_words_by_time(reference: Sequence[Mapping[str, Any]], hypothesis: Sequence[Mapping[str, Any]]):
    """Pair each hypothesis word with the reference word of largest time overlap.

    Words are ``{'start', 'end', 'speaker', 'is_user'?}``. Returns index pairs.
    A hypothesis word with no overlapping reference word is unmatched; the two
    pipelines' ASR clocks differ, so text equality is not required.
    """
    order = sorted(range(len(reference)), key=lambda i: float(reference[i]['start']))
    starts = [float(reference[i]['start']) for i in order]
    pairs = []
    for h_index, word in enumerate(hypothesis):
        h0, h1 = float(word['start']), float(word['end'])
        lo = int(np.searchsorted(starts, h0 - 30.0))  # words are never longer than 30s
        best, best_overlap = None, 0.0
        for k in range(lo, len(order)):
            r = reference[order[k]]
            r0 = float(r['start'])
            if r0 > h1:
                break
            r1 = float(r['end'])
            if h0 == h1:  # a point word pairs with the reference word containing it
                ov = 1e-9 if r0 <= h0 <= r1 else 0.0
            else:
                ov = _overlap(h0, h1, r0, r1)
            if ov > best_overlap:
                best, best_overlap = order[k], ov
        if best is not None:
            pairs.append((best, h_index))
    return pairs


def optimal_label_mapping(pairs: Sequence[tuple[str, str]]) -> dict[str, str]:
    """Hungarian 1:1 mapping hypothesis label -> reference label maximizing co-occurrence."""
    counts = Counter(pairs)
    ref_labels = sorted({r for r, _ in pairs})
    hyp_labels = sorted({h for _, h in pairs})
    if not ref_labels or not hyp_labels:
        return {}
    matrix = np.array([[counts[r, h] for r in ref_labels] for h in hyp_labels], dtype=float)
    rows, cols = linear_sum_assignment(-matrix)
    return {hyp_labels[r]: ref_labels[c] for r, c in zip(rows, cols)}


def owner_agreement(legacy_words, batch_words) -> dict[str, Any]:
    """Row 2 (replay half): owner-word agreement with legacy after optimal mapping.

    1. Pair batch words with legacy words by time overlap.
    2. Map batch speaker labels 1:1 onto legacy labels (Hungarian).
    3. The owner is the legacy label carrying ``is_user`` (majority vote).
       Agreement is binary owner/not-owner accuracy over paired words whose
       legacy speaker is labelled; unlabelled legacy words are excluded.

    Returns counts so callers pool across conversations (sum, then divide).
    """
    pairs = align_words_by_time(legacy_words, batch_words)
    labelled = [
        (legacy_words[r], batch_words[h])
        for r, h in pairs
        if legacy_words[r].get('speaker') not in (None, '') and batch_words[h].get('speaker') not in (None, '')
    ]
    mapping = optimal_label_mapping([(str(r['speaker']), str(h['speaker'])) for r, h in labelled])
    owner_votes = Counter(str(w['speaker']) for w in legacy_words if w.get('is_user') and w.get('speaker'))
    owner = owner_votes.most_common(1)[0][0] if owner_votes else None
    agree = mapped_agree = 0
    for r, h in labelled:
        mapped = mapping.get(str(h['speaker']))
        mapped_agree += mapped == str(r['speaker'])
        if owner is not None:
            agree += (str(r['speaker']) == owner) == (mapped == owner)
    total = len(labelled)
    return {
        'paired_words': total,
        'legacy_words': len(legacy_words),
        'batch_words': len(batch_words),
        'owner_known': owner is not None,
        'owner_agree_words': agree if owner is not None else 0,
        'owner_scored_words': total if owner is not None else 0,
        'label_agree_words': mapped_agree,
    }


def speaker_accuracy(truth_words, predicted_labels) -> dict[str, Any]:
    """Word-speaker attribution accuracy (the #22358 bench metric) via the shared scorer."""
    from utils.stt.diarization_eval import score_words

    return score_words(truth_words, predicted_labels)


def words_text(words: Sequence[Mapping[str, Any]]) -> str:
    return ' '.join(str(w.get('text') or w.get('word') or '') for w in words)
