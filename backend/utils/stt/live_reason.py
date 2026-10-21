"""One content-free reason vocabulary for live failovers and health evidence."""

# Local delivery-bound deaths of a live Soniox/Modulate leg: the vendor socket
# stayed open and the listen pod's own send path missed its bound. These were
# all latched as ``capacity_full``, which reads as destination capacity: at
# peak on 2026-10-21 (P32) ~200/h Soniox-leg deaths failing over to Parakeet
# were taken for Parakeet admission refusals while its GPUs sat near idle.
# Like ``capacity_full`` they are censored (never provider evidence).
LOCAL_DELIVERY_SEND_QUEUE_FULL = 'send_queue_full'  # the bounded send queue or tail buffer was full
LOCAL_DELIVERY_REPLAY_SEND_STALLED = 'replay_send_stalled'  # replay could not drain within its wait or wall budget
LOCAL_DELIVERY_EXPIRED = 'delivery_expired'  # a frame's absolute delivery deadline passed before its write confirmed
LOCAL_DELIVERY_DEATH_REASONS = frozenset(
    {LOCAL_DELIVERY_SEND_QUEUE_FULL, LOCAL_DELIVERY_REPLAY_SEND_STALLED, LOCAL_DELIVERY_EXPIRED}
)

LIVE_STT_FAILURE_REASONS = frozenset(
    {
        'initialization_failed',
        'connection_lost',
        'send_failed',
        'socket_unavailable',
        'modulate_serve_error',
        'provider_budget_exhausted',
        'provider_auth_rejected',
        'provider_rate_limited',
        'provider_429',
        'provider_5xx',
        'timeout',
        'soniox_idle_timeout',
        'soniox_request_timeout',
        'soniox_no_audio_teardown',
        'soniox_rotation',
        'capacity_full',
        LOCAL_DELIVERY_SEND_QUEUE_FULL,
        LOCAL_DELIVERY_REPLAY_SEND_STALLED,
        LOCAL_DELIVERY_EXPIRED,
        # The session's capture replay ring outgrew its horizon before the
        # leg emitted; session-local, never provider capacity or failure.
        'replay_ring_overflow',
        'allocation_rejected',
        'capability_mismatch',
        'first_text_deadline',
        'no_text_rescue_complete',
        'empty_streak',
        'soniox_invalid_hint',
        'vad_failed',
        'client_disconnect',
        'normal_close',
        # Listen cancelled the leg's own task (owner close, recovery switch,
        # teardown). Censored: it is not evidence about the provider.
        'cancelled',
        'other',
        'config_incomplete',
        'auth',
        'quota',
    }
)
LIVE_STT_REASONS = LIVE_STT_FAILURE_REASONS | {'text', 'no_text'}


def normalize_live_stt_reason(*reasons: str | None, default: str = 'connection_lost') -> str:
    """Prefer the first known cause; never return or parse free-text diagnostics.

    Callers pass socket-owned causes before observer symptoms. An unknown
    serving-socket death is connection_lost (a provider failure); explicit
    session/account causes retain their own censored token. Text/no-text use
    their own outcome token. Unknown connect configuration uses 'other'.
    """
    for reason in reasons:
        if isinstance(reason, str) and reason in LIVE_STT_REASONS:
            return reason
    return default if default in LIVE_STT_REASONS else 'connection_lost'
