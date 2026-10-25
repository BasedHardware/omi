"""Server policy for cloud live STT: stream (today), when_watched, or off.

`stream` is the default and must reproduce today's behavior exactly: live
provider streams open as configured (language/cost routing, demand routing,
recovery), including the self-hosted Parakeet window leg.

`when_watched` does not add a parallel switch: it forces the existing
live-demand machinery (`config.live_demand`, PR #21481) to admit every
demand-eligible session, so a vendor stream runs only while the transcript is
visible or a server-side real-time consumer is active.

`off` is the batch-only-cloud end state: no cloud streaming STT session opens
at all — neither vendor nor the Parakeet window leg. Audio is still received
and persisted through the ordinary listen/pusher path; transcripts come from
the batch record lane (or an on-device preview the client runs itself and
declares via the `local_preview` handshake field). Invalid values fail safe to
`stream`, and custom (BYOK) STT sessions are never suppressed: the user pays
for and owns that provider.
"""

import os
from typing import Mapping

STREAM = 'stream'
WHEN_WATCHED = 'when_watched'
OFF = 'off'

_MODES = frozenset({STREAM, WHEN_WATCHED, OFF})
_ENV_NAME = 'CLOUD_LIVE_STT_MODE'


def resolve_cloud_live_stt_mode(*, env: Mapping[str, str] | None = None) -> str:
    """Resolve the policy mode; anything unparseable stays `stream`."""

    source = os.environ if env is None else env
    value = str(source.get(_ENV_NAME, STREAM)).strip().lower()
    return value if value in _MODES else STREAM


def suppresses_provider_stream(mode: str, *, use_custom_stt: bool = False) -> bool:
    """True when this mode must not open any cloud streaming STT session."""

    return mode == OFF and not use_custom_stt
