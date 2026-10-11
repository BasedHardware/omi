"""One content-free reason vocabulary for live failovers and health evidence."""

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
        'allocation_rejected',
        'capability_mismatch',
        'first_text_deadline',
        'no_text_rescue_complete',
        'empty_streak',
        'soniox_invalid_hint',
        'vad_failed',
        'client_disconnect',
        'normal_close',
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
