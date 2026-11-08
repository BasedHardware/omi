"""Client-reported app channel (``X-Omi-App-Channel``). Pure module: stdlib only.

The mobile app sends ``beta`` from TestFlight installs and non-production build
profiles and ``store`` otherwise (``app/lib/utils/app_channel.dart``). Any client
can send any header, so this is a client assertion: use it to show read-only or
preview UI, never to unlock money, entitlements or data.
"""

from __future__ import annotations

from typing import Any

APP_CHANNEL_HEADER = 'X-Omi-App-Channel'
APP_CHANNELS = frozenset({'beta', 'store'})


def app_channel(raw: str | None) -> str:
    """The request's ``X-Omi-App-Channel`` as a bounded label: ``beta``, ``store`` or ``unknown``."""
    value = (raw or '').strip().lower()
    return value if value in APP_CHANNELS else 'unknown'


def is_testflight(request: Any) -> bool:
    """True when the request (anything with ``.headers``) comes from a TestFlight/beta app build."""
    return app_channel(request.headers.get(APP_CHANNEL_HEADER)) == 'beta'
