"""Audio-timeline v2 feature flag (AUDIO_TIMELINE_V2).

Runtime-selected rollout switches keep their env parsing in a pure ``config/``
module and read mutable env at the call boundary, never at import. The flag
admits *new eligible recordings only*: single-channel, server-STT live capture.
Flag off means existing v1 wire and persistence are unchanged.
"""

import os

_TRUTHY = frozenset({'1', 'true', 'yes', 'on'})


def audio_timeline_v2_enabled() -> bool:
    """Read AUDIO_TIMELINE_V2 at the call boundary. Default off."""
    return os.getenv('AUDIO_TIMELINE_V2', '').strip().lower() in _TRUTHY
