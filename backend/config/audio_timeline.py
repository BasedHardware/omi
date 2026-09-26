"""Audio-timeline v2 feature flag (AUDIO_TIMELINE_V2) and speaker-clock switch.

Runtime-selected rollout switches keep their env parsing in a pure ``config/``
module and read mutable env at the call boundary, never at import. The flag
admits *new eligible recordings only*: single-channel, server-STT live capture.
Flag off means existing v1 wire and persistence are unchanged.
"""

import os

_TRUTHY = frozenset({'1', 'true', 'yes', 'on'})
_FALSY = frozenset({'0', 'false', 'no', 'off'})


def audio_timeline_v2_enabled() -> bool:
    """Read AUDIO_TIMELINE_V2 at the call boundary. Default off."""
    return os.getenv('AUDIO_TIMELINE_V2', '').strip().lower() in _TRUTHY


def live_speaker_capture_clock_enabled() -> bool:
    """Read LIVE_SPEAKER_CAPTURE_CLOCK at the call boundary. Default on.

    Runtime kill switch for the always-on capture-clock speaker-ID path (the
    §9 addition that positions live speaker clips and the ring buffer on the
    capture clock for every server-STT session, flag or not). Prod can revert
    speaker-ID windows to the legacy first-audio + provider-time formula
    without a deploy by setting this to a falsy value; persisted fields and
    the wire are on the v2 flag, not this switch. Unbound stays default-on.
    """
    return os.getenv('LIVE_SPEAKER_CAPTURE_CLOCK', '').strip().lower() not in _FALSY
