"""One content-free reason vocabulary for live failovers and health evidence.

The vocabulary itself lives in ``utils.observability.reasons.LiveSttReason``; the
frozensets below are the unchanged legacy view of it.
"""

from utils.observability.reasons import LiveSttReason, ReasonFamily, reason_values, reason_label

LIVE_STT_REASONS = reason_values(LiveSttReason)
# `text` and `no_text` are outcome tokens, not failures.
LIVE_STT_FAILURE_REASONS = LIVE_STT_REASONS - {'text', 'no_text'}

# Local delivery-bound deaths of a live Soniox/Modulate leg: the vendor socket
# stayed open and the listen pod's own send path missed its bound. These were
# all latched as ``capacity_full``, which reads as destination capacity: at
# peak on 2026-10-21 (P32) ~200/h Soniox-leg deaths failing over to Parakeet
# were taken for Parakeet admission refusals while its GPUs sat near idle.
# Like ``capacity_full`` they are censored (never provider evidence).
LOCAL_DELIVERY_SEND_QUEUE_FULL = LiveSttReason.SEND_QUEUE_FULL.value  # the bounded send queue or tail buffer was full
LOCAL_DELIVERY_REPLAY_SEND_STALLED = (
    LiveSttReason.REPLAY_SEND_STALLED.value
)  # replay could not drain within its wait or wall budget
LOCAL_DELIVERY_EXPIRED = (
    LiveSttReason.DELIVERY_EXPIRED.value
)  # a frame's absolute delivery deadline passed before its write confirmed
LOCAL_DELIVERY_DEATH_REASONS = frozenset(
    {LOCAL_DELIVERY_SEND_QUEUE_FULL, LOCAL_DELIVERY_REPLAY_SEND_STALLED, LOCAL_DELIVERY_EXPIRED}
)


def normalize_live_stt_reason(*reasons: str | None, default: str = 'connection_lost') -> str:
    """Prefer the first known cause; never return or parse free-text diagnostics.

    Callers pass socket-owned causes before observer symptoms. An unknown
    serving-socket death is connection_lost (a provider failure); explicit
    session/account causes retain their own censored token. Text/no-text use
    their own outcome token. ``other`` is the fallback metric's bucket, not a
    latchable cause: it may be passed through when a socket already holds it,
    but a miss never degrades to it — that is how untyped Soniox leg deaths
    became the largest ``reason=other`` family after the live-tail catch-up
    train (P59, 2026-10-22).
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
    if default == 'other':
        # The bucket token stays reserved for record_fallback's own bounding.
        return 'connection_lost'
    return default if default in LIVE_STT_REASONS else 'connection_lost'
