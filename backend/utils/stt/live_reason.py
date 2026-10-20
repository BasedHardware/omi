"""One content-free reason vocabulary for live failovers and health evidence.

The vocabulary itself lives in ``utils.observability.reasons.LiveSttReason``; the
frozensets below are the unchanged legacy view of it.
"""

from utils.observability.reasons import LiveSttReason, ReasonFamily, reason_values, reason_label

LIVE_STT_REASONS = reason_values(LiveSttReason)
# `text` and `no_text` are outcome tokens, not failures.
LIVE_STT_FAILURE_REASONS = LIVE_STT_REASONS - {'text', 'no_text'}


def normalize_live_stt_reason(*reasons: str | None, default: str = 'connection_lost') -> str:
    """Prefer the first known cause; never return or parse free-text diagnostics.

    Callers pass socket-owned causes before observer symptoms. An unknown
    serving-socket death is connection_lost (a provider failure); explicit
    session/account causes retain their own censored token. Text/no-text use
    their own outcome token. Unknown connect configuration uses 'other'.
    """
    for reason in reasons:
        if isinstance(reason, str) and reason in LIVE_STT_REASONS:
            # Counted too (omi_reason_total only), so the family's unknown ratio is a
            # share of all normalizations, not of the misses alone.
            return reason_label(ReasonFamily.LIVE_STT, reason, LiveSttReason)
    if any(reason is not None for reason in reasons):
        # Behaviour-neutral: the label stays `default`; the miss is counted
        # under family=live_stt (omi_reason_unknown_total and omi_reason_total).
        reason_label(ReasonFamily.LIVE_STT, next(reason for reason in reasons if reason is not None), LiveSttReason)
    return default if default in LIVE_STT_REASONS else 'connection_lost'
