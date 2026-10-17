"""Funded-provider admission; legacy root usage counters deliberately stay unchanged."""

import logging
import os
import time
from functools import lru_cache, wraps
from contextvars import ContextVar
from typing import Any
from utils.stt.socket import STTSocket
from utils.stt.live_router import connecting_target

from config.stt_cap_dispatch import enabled, execution_admission_enabled
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
    from utils.subscription import resolve_transcription_allowance, TranscriptionAllowance
    from utils import ladder_v1

    if not enabled() and execution_admission_enabled():
        # Ladder-only activation must not activate legacy monthly-seconds
        # dispatch enforcement. A missing/unreadable budget is never permission
        # to spend; match the funded resolver's fail-closed behavior.
        try:
            snapshot = ladder_v1.budget_snapshot(uid)
            if snapshot is None:
                return TranscriptionAllowance('managed', None, 'legacy_dispatch_disabled', limit_seconds=None)
            exhausted = snapshot['budget_percent'] >= 100
            return TranscriptionAllowance(
                'on_device' if exhausted else 'managed',
                0 if exhausted else None,
                'usage_budget_exhausted' if exhausted else 'usage_budget_available',
                limit_seconds=None,
                remaining_units=max(0, snapshot['budget_units'] - snapshot['used_units']),
                budget_units=snapshot['budget_units'],
            )
        except Exception:
            return TranscriptionAllowance('on_device', 0, 'allowance_unavailable')
    return resolve_transcription_allowance(uid, source=source, byok_active=False, omi_funded=True)


def sync_allowed(uid: str, seconds: float = 0, provider: Any = 'unknown') -> bool:
    if not execution_admission_enabled():
        return True
    allowance = funded_allowance(uid)
    if not allowance.managed:
        record_audio('sync', 'held', provider, seconds, allowance.reason == 'plan_allowance_exhausted')
    return allowance.managed


@lru_cache(maxsize=16)
def _units_per_second(provider='deepgram'):
    from config.rate_card import price_transcription

    return price_transcription(3600, provider=provider, accepted=True)['micro_units'] / 3_600_000_000


class LiveAdmission:
    """One balance shared by every channel, replay and replacement in a session.

    Accepted packets debit a finite seconds or unit snapshot locally. Ladder
    snapshots rescan only near the cap, on invalidation, or after 900 seconds;
    legacy admission keeps main's flush cadence. Provider queues may drain.
    """

    def __init__(self, uid, source=None):
        self.uid, self.source = uid, source
        self.remaining = 0
        self.reason = 'allowance_unavailable'
        self.managed = False
        self.held = []
        self.omi_selected = False
        self.remaining_units = None
        self.budget_units = None
        self.refreshed_at = None

    def refresh_due(self):
        if self.refreshed_at is None or self.remaining_units is None:
            return True  # Preserve main's per-flush legacy admission refresh.
        near = self.remaining_units <= 120 * _units_per_second() or (
            self.budget_units is not None and self.remaining_units <= self.budget_units * 0.1
        )
        return time.monotonic() - self.refreshed_at >= (60 if near else 900)

    async def refresh(self, *, force=True):
        if not force and not self.refresh_due():
            return
        allowance = await run_blocking(db_executor, funded_allowance, self.uid, self.source)
        self.remaining, self.reason, self.managed = allowance.remaining_seconds, allowance.reason, allowance.managed
        self.remaining_units = allowance.remaining_units
        self.budget_units = allowance.budget_units
        self.refreshed_at = time.monotonic()
        if self.remaining_units is not None:
            # A conservative seconds equivalent for existing client warnings.
            self.remaining = self.remaining_units / _units_per_second()
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

    def packet_allowed(self, data, provider, rate):
        if not self.allowed(provider):
            return False
        if self.remaining_units is not None and not customer_funded(provider):
            debit = len(data) / (2 * rate) * _units_per_second(str(getattr(provider, 'value', provider)))
            if debit > self.remaining_units:
                # Suppress before timeline adapters can record an accepted span.
                # Capture/archive owns these bytes independently of the provider.
                self.remaining_units, self.remaining = 0, 0
                self.reason = 'usage_budget_exhausted'
                return False
        return True

    def send(self, raw, data, provider, rate, *args, **kwargs):
        if not self.packet_allowed(data, provider, rate):
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
            if self.remaining_units is not None:
                self.remaining_units = max(
                    0, self.remaining_units - seconds * _units_per_second(str(getattr(provider, 'value', provider)))
                )
                self.remaining = self.remaining_units / _units_per_second()
                if self.remaining_units == 0:
                    self.reason = 'usage_budget_exhausted'
            elif self.remaining is not None:
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
        if self.raw is None or not self.admission.packet_allowed(data, self.provider, self.rate):
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
            admission = current_live_admission.get() if execution_admission_enabled() else None
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
