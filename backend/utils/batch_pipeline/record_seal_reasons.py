"""Closed, counts-only proof diagnostics. Never retain exception text."""

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
