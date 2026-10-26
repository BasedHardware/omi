"""Server policy for cloud live STT: stream (today), when_watched, or off.

`stream` is the default and must reproduce today's behavior exactly: live
provider streams open as configured (language/cost routing, demand routing,
recovery), including the self-hosted Parakeet window leg.

`when_watched` does not add a parallel switch: it forces the existing
live-demand machinery (`config.live_demand`, PR #21481) to admit every
demand-eligible session, so a vendor stream runs only while the transcript is
visible or a server-side real-time consumer is active.

`off` defers the provider stream instead of dropping it: no cloud streaming
STT session opens at session start (neither vendor nor the Parakeet window
leg), and one opens only when audio actually reaches the socket. A listen
conversation is kept alive and finalized only by live segments, so audio
received with no stream at all would be deleted as an empty conversation and
never registered for batch. Invalid values fail safe to `stream`, and custom
(BYOK) STT sessions are never deferred: the user pays for and owns that
provider.

`LOCAL_PREVIEW_BATCH_ENABLED` is the kill switch (on unless set off) for the
mobile local-preview lane: a batch-lane client that declares `local_preview`
journals all pendant audio for batch through the mobile Standard batch route
and renders its own on-device preview, so its listen session defers the cloud
stream the same way.
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
    """True when this mode must not open a cloud streaming STT session before audio arrives."""

    return mode == OFF and not use_custom_stt


_LOCAL_PREVIEW_ENV_NAME = 'LOCAL_PREVIEW_BATCH_ENABLED'


def local_preview_batch_enabled(*, env: Mapping[str, str] | None = None) -> bool:
    """Kill switch for the mobile local-preview batch lane: on unless explicitly off."""

    source = os.environ if env is None else env
    return str(source.get(_LOCAL_PREVIEW_ENV_NAME, 'true')).strip().lower() not in {'false', '0', 'off', 'no'}
