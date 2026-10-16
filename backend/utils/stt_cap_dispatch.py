"""Funded-provider admission; legacy root usage counters deliberately stay unchanged."""

import logging
import os
from functools import wraps
from contextvars import ContextVar
from typing import Any
from utils.stt.socket import STTSocket
from utils.stt.live_router import connecting_target

from config.stt_cap_dispatch import enabled
from utils.observability.stt_cap_dispatch import record_audio
from utils.byok import get_byok_key
from utils.executors import db_executor, run_blocking

logger = logging.getLogger(__name__)


def customer_funded(provider):
    return (
        getattr(provider, 'value', provider) == 'deepgram'
        and os.getenv('DEEPGRAM_SELF_HOSTED_ENABLED', '').lower() != 'true'
        and bool(get_byok_key('deepgram'))
    )


def funded_allowance(uid, source=None):
    # Streaming imports this module even with enforcement off. Load billing
    # policy only at the admission boundary, not during provider-module import.
    from utils.subscription import resolve_transcription_allowance

    return resolve_transcription_allowance(uid, source=source, byok_active=False, omi_funded=True)


def sync_allowed(uid: str, seconds: float = 0, provider: Any = 'unknown') -> bool:
    if not enabled():
        return True
    allowance = funded_allowance(uid)
    if not allowance.managed:
        record_audio('sync', 'held', provider, seconds, allowance.reason == 'plan_allowance_exhausted')
    return allowance.managed


class LiveAdmission:
    """One balance shared by every channel, replay and replacement in a session.

    Refresh uses the existing usage flush cadence. Accepted packets debit the
    finite snapshot locally, so no further packet starts after it reaches zero.
    Provider queues already accepting audio remain free to drain.
    """

    def __init__(self, uid, source=None):
        self.uid, self.source = uid, source
        self.remaining = 0
        self.reason = 'allowance_unavailable'
        self.managed = False
        self.held = []
        self.omi_selected = False

    async def refresh(self):
        allowance = await run_blocking(db_executor, funded_allowance, self.uid, self.source)
        self.remaining, self.reason, self.managed = allowance.remaining_seconds, allowance.reason, allowance.managed
        if self.managed:
            for socket in list(self.held):
                try:
                    await socket.resume()
                except Exception as error:
                    logger.warning(
                        'event=stt_cap_dispatch outcome=resume_deferred exception_type=%s', type(error).__name__
                    )

    @property
    def funded_paused(self) -> bool:
        return self.omi_selected and not (self.managed and (self.remaining is None or self.remaining > 0))

    def allowed(self, provider):
        return customer_funded(provider) or self.managed and (self.remaining is None or self.remaining > 0)

    def send(self, raw, data, provider, rate, *args, **kwargs):
        if not self.allowed(provider):
            record_audio(
                'live', 'suppressed', provider, len(data) / (2 * rate), self.reason == 'plan_allowance_exhausted'
            )
            # Policy absorption is not a transport failure. The receive/archive
            # paths continue, and recovery must not fail over or close capture.
            return True
        accepted = raw.send(data, *args, **kwargs)
        if accepted is not False and not customer_funded(provider):
            seconds = len(data) / (2 * rate)
            record_audio('live', 'accepted', provider, seconds, self.reason == 'plan_allowance_exhausted')
            if self.remaining is not None:
                self.remaining = max(0, self.remaining - seconds)
                if self.remaining == 0:
                    self.reason = 'plan_allowance_exhausted'
        return accepted


current_live_admission = ContextVar('stt_cap_live_admission', default=None)


class CapSocket(STTSocket):
    """Keep receiving at cap, without opening a paid provider or ending capture."""

    def __init__(self, admission, provider, rate, factory, raw=None):
        self.admission, self.provider, self.rate = admission, provider, rate
        self.factory, self.raw = factory, raw
        self.closed = False
        self.cap_dispatch_socket = True
        self._open_callbacks = []
        if not customer_funded(provider):
            admission.omi_selected = True
        if raw is None:
            admission.held.append(self)
            logger.info('event=stt_cap_dispatch path=live outcome=held provider=%s', provider)

    async def resume(self):
        if self.raw is None and not self.closed and self.admission.allowed(self.provider):
            raw = await self.factory()
            if raw is None:
                raise RuntimeError('held provider constructor returned no socket')
            # Registry constructors can invoke another decorated provider. A
            # resumed leg must retain exactly one debit/metric boundary, just
            # like the initial construction path below.
            while isinstance(raw, CapSocket):
                self.provider, self.rate, self.factory = raw.provider, raw.rate, raw.factory
                if not customer_funded(self.provider):
                    self.admission.omi_selected = True
                if raw in self.admission.held:
                    self.admission.held.remove(raw)
                if raw.raw is None:
                    self._open_callbacks.extend(raw._open_callbacks)
                    return  # Actual fallback remains denied; keep this leg held.
                raw = raw.raw
            self.raw = raw
            for callback in self._open_callbacks:
                callback(raw)
            self.admission.held.remove(self)

    def on_open(self, callback):
        self._open_callbacks.append(callback)
        if self.raw is not None:
            callback(self.raw)

    def set_wire_ledger(self, ledger):
        self.on_open(lambda transport: transport.set_wire_ledger(ledger))

    def set_capture_axis_ledger(self, ledger):
        self.on_open(lambda transport: transport.set_capture_axis_ledger(ledger))

    @property
    def __class__(self) -> type:
        return self.raw.__class__ if self.raw is not None else type(self)

    @__class__.setter
    def __class__(self, value: type) -> None:
        raise TypeError('provider proxy class is read only')

    def __getattr__(self, name):
        if self.raw is None:
            raise AttributeError(name)
        return getattr(self.raw, name)

    @property
    def is_connection_dead(self):
        if not self.admission.allowed(self.provider):
            return False  # A paused provider cannot end ongoing capture.
        return self.raw.is_connection_dead if self.raw is not None else False

    @property
    def death_reason(self):
        return self.raw.death_reason if self.raw is not None else None

    def suppress(self, data):
        if self.raw is None or not self.admission.allowed(self.provider):
            record_audio(
                'live',
                'suppressed',
                self.provider,
                len(data) / (2 * self.rate),
                self.admission.reason == 'plan_allowance_exhausted',
            )
            return True
        return False

    def send(self, data, *args, **kwargs):
        if self.raw is None:
            record_audio(
                'live',
                'suppressed',
                self.provider,
                len(data) / (2 * self.rate),
                self.admission.reason == 'plan_allowance_exhausted',
            )
            return True
        return self.admission.send(self.raw, data, self.provider, self.rate, *args, **kwargs)

    def finish(self):
        self.closed = True
        if self.raw is not None:
            return self.raw.finish()

    def finalize(self):
        if self.raw is not None:
            return self.raw.finalize()


def live_provider(provider, rate_index):
    """Applied at actual provider constructors, including fallback constructors."""

    def decorate(fn):
        @wraps(fn)
        async def connect(*args, **kwargs):
            admission = current_live_admission.get() if enabled() else None
            if admission is None:
                return await fn(*args, **kwargs)
            rate = kwargs.get('sample_rate') or args[rate_index]
            target = connecting_target.get()

            async def factory():
                token = connecting_target.set(target)
                try:
                    return await fn(*args, **kwargs)
                finally:
                    connecting_target.reset(token)

            allowed = admission.allowed(provider)
            try:
                raw = await factory() if allowed else None
            except Exception:
                if admission.allowed(provider):
                    raise
                raw = None  # Permission changed while the dial was in flight.
            if allowed and raw is None:
                return None
            if isinstance(raw, CapSocket):
                return raw
            return CapSocket(admission, provider, rate, factory, raw)

        return connect

    return decorate


def session_admission(fn):
    @wraps(fn)
    async def connect(self, *args, **kwargs):
        admission = getattr(self.receiver, 'cap_admission', None)
        token = current_live_admission.set(admission)
        try:
            return await fn(self, *args, **kwargs)
        finally:
            current_live_admission.reset(token)

    return connect


def suppress_socket_audio(socket, data):
    # Explicit identity avoids treating test doubles or unrelated adapters as
    # cap owners. Suppress before VAD/timeline adapters record provider spans.
    return getattr(socket, 'cap_dispatch_socket', False) is True and socket.suppress(data)
