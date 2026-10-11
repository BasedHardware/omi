"""Pure cache-aligned history window policy."""

CHAT_HISTORY_BASE_VISIBLE_MESSAGES = 10
CHAT_HISTORY_APPEND_EPOCH_MESSAGES = 8


def cache_aligned_history_limit(total_visible_messages: int) -> int:
    """Return a bounded history size whose start moves only at epoch boundaries.

    A fixed newest-N window changes at the front on every chat turn, invalidating
    Anthropic's cumulative message-prefix cache. This policy keeps at least the
    existing ten-message continuity window and lets it grow append-only for eight
    messages before resetting to ten. The request therefore carries 10..17
    messages, never less history than before and never an unbounded transcript.
    """
    if total_visible_messages < 0:
        raise ValueError('total_visible_messages must be non-negative')
    if total_visible_messages <= CHAT_HISTORY_BASE_VISIBLE_MESSAGES:
        return total_visible_messages
    return CHAT_HISTORY_BASE_VISIBLE_MESSAGES + (
        (total_visible_messages - CHAT_HISTORY_BASE_VISIBLE_MESSAGES) % CHAT_HISTORY_APPEND_EPOCH_MESSAGES
    )
