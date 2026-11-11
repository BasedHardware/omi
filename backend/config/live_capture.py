"""Bounded vocabulary for transient live capture-window attribution."""

CAPTURE_WINDOW_REASONS = frozenset(
    {
        'known_window',
        'missing_window',
        'translator_zero_length',
        'translator_outside_accepted_sends',
        'translator_discontinuous_interval',
        'translator_collapsed_interval',
        'translator_non_numeric',
        'translator_non_finite',
        'anchor_compacted',
        'send_map_evicted',
        'merge_unknown_side',
        'merge_gap',
        'merge_invalid_window',
        'partial_redistribution',
        'custom_stt',
        'multi_channel',
        'kill_switch',
        'inherited_unknown',
    }
)


def capture_window_reason(value):
    return value if isinstance(value, str) and value in CAPTURE_WINDOW_REASONS else 'missing_window'
