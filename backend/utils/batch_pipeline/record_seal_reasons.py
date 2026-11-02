"""Closed, counts-only proof diagnostics. Never retain exception text."""

import math

TAIL_GAP_BUCKETS = frozenset({'under_1s', '1_to_5s', '5_to_30s', '30_to_120s', 'over_120s', 'negative_or_unknown'})


def tail_gap_bucket(finished_at, end):
    """Diagnostic only: no timestamps or exact gaps leave the proof process.

    Boundaries are [0, 1), [1, 5), [5, 30), [30, 120], (120, infinity).
    """
    try:
        gap = finished_at.timestamp() - end
        if not math.isfinite(gap) or gap < 0:
            return 'negative_or_unknown'
    except (AttributeError, TypeError, ValueError, OverflowError):
        return 'negative_or_unknown'
    for ceiling, bucket in ((1, 'under_1s'), (5, '1_to_5s'), (30, '5_to_30s')):
        if gap < ceiling:
            return bucket
    return '30_to_120s' if gap <= 120 else 'over_120s'


class TailGapRefusal(ValueError):
    def __init__(self, bucket):
        super().__init__('retained capture tail not durable yet')
        self.tail_gap_bucket = bucket if bucket in TAIL_GAP_BUCKETS else 'negative_or_unknown'


PROOF_REASONS = frozenset(
    {
        'tail_lagging',
        'tail_lost_or_unproven',
        'overlap_conflict',
        'decode_or_checksum',
        'budget_limit',
        'finish_missing',
        'registration_refused',
        'other',
    }
)

_MESSAGES = {
    'retained capture tail not durable yet': 'tail_lagging',
    'retained capture not durable yet': 'tail_lost_or_unproven',
    'conflicting retained audio overlap': 'overlap_conflict',
    'retained capture unit budget exceeded': 'budget_limit',
    'retained capture reference budget exceeded': 'budget_limit',
    'retained audio source exceeds size budget': 'budget_limit',
    'invalid retained audio size': 'budget_limit',
    'retained capture finish missing': 'finish_missing',
    'registration refused': 'registration_refused',
    **dict.fromkeys(
        (
            'retained source has no aligned audio',
            'truncated encrypted audio length',
            'invalid encrypted audio frame',
            'retained capture checksum mismatch',
            'invalid retained PCM',
            'retained PCM digest changed',
            'invalid WAL packet',
            'capture decoder produced no PCM',
        ),
        'decode_or_checksum',
    ),
}


def proof_reason(error):
    # Exact fixed messages only; arbitrary provider text never becomes state or
    # a label, even if it embeds one of these phrases.
    return _MESSAGES.get(str(error), 'other')


def proof_diagnostics(error):
    reason = proof_reason(error)
    result = {'proof_reason': reason}
    if reason == 'tail_lagging':
        bucket = getattr(error, 'tail_gap_bucket', None)
        result['tail_gap_bucket'] = bucket if bucket in TAIL_GAP_BUCKETS else 'negative_or_unknown'
    return result
