"""Join beta recap dispatch and cache outcomes to existing gateway accounting receipts."""

import hashlib
import hmac
import json
import logging
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from uuid import UUID

from starlette.datastructures import Headers

from config.conversations_v3 import live_recap_enabled

logger = logging.getLogger(__name__)
_WINDOW_SECONDS = 300
_TRIGGERS = frozenset({'first_open', 'retry', 'timed_refresh'})
_BOOL = {'true': True, 'false': False}
_CURRENT: ContextVar['tuple[str, RecapObservation | None] | None'] = ContextVar('live_recap_observation', default=None)


def _header(headers: Headers, name: str) -> str | None:
    values = headers.getlist('x-omi-recap-' + name)
    return values[0] if len(values) == 1 else None


def _uuid(value: str | None) -> str | None:
    if value is None or len(value) != 36:
        return None
    try:
        parsed = UUID(value)
    except ValueError:
        return None
    return str(parsed) if parsed.version == 4 and str(parsed) == value.lower() else None


def _digest(key: bytes, value: str) -> str:
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()[:32]


@dataclass(frozen=True)
class RecapObservation:
    _viewer_key: bytes | None = field(repr=False)
    request: str | None
    interval: str | None
    trigger: str | None
    foreground: bool | None
    speech_eligible: bool | None

    def record(self, outcome: str, *, gateway_request: str | None = None) -> None:
        at = time.time()
        bucket = int(at) // _WINDOW_SECONDS
        # Events less than five minutes apart share an alias even across a
        # boundary. Filter to the actual five-minute window before joining.
        key = self._viewer_key
        aliases = [_digest(key, f'viewer:{epoch}') for epoch in (bucket, bucket - 1)] if key else []
        verified = bool(
            aliases
            and self.request
            and self.interval
            and self.trigger
            and self.foreground is not None
            and self.speech_eligible is not None
        )
        logger.info(
            'event=live_recap_beta %s',
            json.dumps(
                {
                    'at': at,
                    'outcome': outcome,
                    'viewer_aliases': aliases,
                    'request': self.request,
                    'interval': self.interval,
                    'trigger': self.trigger,
                    'foreground': self.foreground,
                    'speech_eligible': self.speech_eligible,
                    'join': 'correlatable' if verified else 'unverified',
                    'gateway_request': gateway_request,
                },
                separators=(',', ':'),
            ),
        )


def observe(uid: str, headers: Headers) -> RecapObservation:
    secret = os.getenv('ENCRYPTION_SECRET')
    key = (
        hmac.digest(secret.encode(), ('omi:live-recap:internal-beta:v1:' + uid).encode(), 'sha256') if secret else None
    )
    request = _uuid(_header(headers, 'request'))
    interval = _uuid(_header(headers, 'interval'))
    trigger = _header(headers, 'trigger')
    return RecapObservation(
        key,
        _digest(key, 'request:' + request) if key and request else None,
        _digest(key, 'interval:' + interval) if key and interval else None,
        trigger if trigger in _TRIGGERS else None,
        _BOOL.get(_header(headers, 'foreground') or ''),
        _BOOL.get(_header(headers, 'speech-eligible') or ''),
    )


@contextmanager
def scoped(uid: str, observation: RecapObservation | None):
    token = _CURRENT.set((uid, observation))
    try:
        yield
    finally:
        _CURRENT.reset(token)


def admit_dispatch() -> RecapObservation | None:
    context = _CURRENT.get()
    if context is None:
        return None
    uid, observation = context
    if not live_recap_enabled(uid):
        if observation is not None:
            observation.record('cohort_revoked')
        raise RuntimeError('live_recap_unavailable')
    return observation


def active() -> bool:
    return _CURRENT.get() is not None
