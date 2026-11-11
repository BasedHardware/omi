"""Content-free provider availability evidence, separate from transcript SLIs."""

from utils.stt.live_reason import LIVE_STT_REASONS

PROVIDER_FAILURE_REASONS = frozenset(
    {
        'connection_lost',
        'send_failed',
        'modulate_serve_error',
        'provider_5xx',
        'provider_429',
        'provider_rate_limited',
        'timeout',
    }
)


def provider_observation(outcome: str, reason: str | None = None) -> bool | None:
    """True is attributable failure, False completed text, None censored audio.

    First-text deadlines/empty streaks cannot distinguish silence/noise from a
    recognizer failure without a successor join. They stay in diagnostic SLIs.
    Account/config/capacity and client/VAD failures have separate protection.
    """
    if reason is not None and reason not in LIVE_STT_REASONS:
        raise ValueError('live health reason must be bounded')
    if outcome in {'failover', 'connect_failure'}:
        return True if reason in PROVIDER_FAILURE_REASONS else None
    if outcome == 'text':
        return False
    return None
