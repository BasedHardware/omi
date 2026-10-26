"""Funded-provider admission; legacy root counters exclude only receiver-held live audio."""

import logging
import os
import time
from functools import lru_cache, wraps
from contextvars import ContextVar
from typing import Any, Callable
from utils.stt.socket import STTSocket
from utils.stt.live_router import connecting_target

from config.stt_cap_dispatch import (
    enabled,
    execution_admission_enabled,
    execution_admission_configured,
    offline_enforcement_enabled,
    offline_admission_enabled,
    LANES,
)
from config.ladder_v1 import budget_enforcement_enabled
from utils.observability.stt_cap_dispatch import (
    allowance_decision_reason,
    record_audio,
    record_decision,
    DispatchPath,
    DispatchReason,
)
from utils.byok import get_byok_key
from utils.executors import db_executor, run_blocking

logger = logging.getLogger(__name__)


def customer_funded(provider):
    return (
        getattr(provider, 'value', provider) == 'deepgram'
        and os.getenv('DEEPGRAM_SELF_HOSTED_ENABLED', '').lower() != 'true'
        and bool(get_byok_key('deepgram'))
    )


_UNRESOLVED = object()


def funded_allowance(uid, source=None, *, usage_cache=None, subscription=_UNRESOLVED, lane=None):
    # Streaming imports this module even with enforcement off. Load billing
    # policy only at the admission boundary, not during provider-module import.
    from utils.subscription import resolve_transcription_allowance, TranscriptionAllowance
    from utils import ladder_v1

    if lane is not None:
        if lane not in LANES:
            raise ValueError('unknown cap dispatch lane')
        if not offline_admission_enabled(uid, lane):
            return TranscriptionAllowance('managed', None, 'dispatch_scope_disabled', limit_seconds=None)
    if not enabled() and not offline_enforcement_enabled(lane) and execution_admission_configured():
        # Ladder-only activation must not activate legacy monthly-seconds
        # dispatch enforcement. A missing/unreadable budget is never permission
        # to spend; match the funded resolver's fail-closed behavior.
        try:
            budget_kwargs = {'session_cache': usage_cache} if usage_cache is not None else {}
            if subscription is not _UNRESOLVED:
                budget_kwargs['subscription'] = subscription
            snapshot = ladder_v1.budget_snapshot(uid, **budget_kwargs)
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
    kwargs = {'usage_cache': usage_cache} if usage_cache is not None else {}
    if offline_enforcement_enabled(lane):
        kwargs['provision_subscription'] = False
    if subscription is not _UNRESOLVED:
        kwargs['subscription'] = subscription
    return resolve_transcription_allowance(uid, source=source, byok_active=False, omi_funded=True, **kwargs)


class CapAllowanceDenied(Exception):
    """A spend refusal, handled as durable audio custody rather than STT failure."""


def sync_admission(
    uid: str, seconds: float = 0, provider: Any = 'unknown', *, lane: str = 'sync', path: DispatchPath | None = None
) -> tuple[bool, str]:
    """``sync_allowed`` with the bounded DispatchReason surfaced for durable per-unit decisions."""
    if lane not in LANES:
        raise ValueError('unknown cap dispatch lane')
    path = path or (DispatchPath.BATCH_GPU if lane == 'batch' else DispatchPath.SYNC_SEGMENT)
    if not offline_admission_enabled(uid, lane):
        allowed, reason = True, DispatchReason.SCOPE_DISABLED
    elif customer_funded(provider):
        allowed, reason = True, DispatchReason.BYOK
    else:
        from utils import funded_processing

        if not funded_processing.consent_allows(uid):
            allowed, reason = False, DispatchReason.CONSENT_DENIED
        else:
            allowance = funded_allowance(uid, lane=lane)
            if not allowance.managed:
                record_audio(lane, 'held', provider, seconds, allowance.reason == 'plan_allowance_exhausted')
            allowed, reason = allowance.managed, allowance_decision_reason(allowance)
    record_decision(path, allowed, reason)
    return allowed, reason.value


def sync_allowed(
    uid: str, seconds: float = 0, provider: Any = 'unknown', *, lane: str = 'sync', path: DispatchPath | None = None
) -> bool:
    return sync_admission(uid, seconds, provider, lane=lane, path=path)[0]


HELD_SPAN_MERGE_GAP_SECONDS = 0.5
MAX_HELD_SPANS = 256


@lru_cache(maxsize=16)
def _units_per_second(provider='deepgram'):
    from config.rate_card import price_transcription

    return price_transcription(3600, provider=provider, accepted=True)['micro_units'] / 3_600_000_000


class LiveAdmission:
    """One balance shared by every channel, replay and replacement in a session.

    Accepted packets debit a finite seconds or unit snapshot locally. Ladder
    snapshots read open buckets near cap, and rescan on invalidation or at 900 seconds;
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
        self.failures = 0
        self.usage_cache = None
        self.capture_observer: Callable[[bytes, int, int, bool], None] | None = None
        self.active_capture: tuple[bytes, int, list[tuple[int, int]]] | None = None
        # Merged wall-clock receipt spans of receiver-denied audio. The usage flush
        # excludes their overlap with its billable window: held audio is metered
        # once, by recovery, when it is actually transcribed.
        self.held_spans: list[list[float]] = []
        if budget_enforcement_enabled():
            from database.usage_units_session import UsageUnitsSession

            self.usage_cache = UsageUnitsSession()

    def refresh_due(self):
        if self.refreshed_at is None:
            return True
        if self.reason == 'allowance_unavailable' and self.usage_cache is not None:
            delay = min(900, 60 * 2 ** min(max(self.failures - 1, 0), 4))
            return time.monotonic() - self.refreshed_at >= delay
        if (
            self.usage_cache is not None
            and self.usage_cache.full_at is not None
            and time.monotonic() - self.usage_cache.full_at >= 900
        ):
            return True
        if self.remaining_units is None:
            # A known non-ladder account needs only a long membership refresh
            # when legacy dispatch is off. Invalidation still forces a read.
            # Enabled legacy dispatch retains main's per-flush refresh.
            return self.reason != 'legacy_dispatch_disabled' or time.monotonic() - self.refreshed_at >= 900
        near = self.remaining_units <= 120 * _units_per_second() or (
            self.budget_units is not None and self.remaining_units <= self.budget_units * 0.1
        )
        return time.monotonic() - self.refreshed_at >= (60 if near else 900)

    async def refresh(self, *, force=True, subscription=_UNRESOLVED):
        if not force and not self.refresh_due():
            return
        kwargs = {}
        if self.usage_cache is not None:
            if force:
                self.usage_cache.invalidate()
            kwargs['usage_cache'] = self.usage_cache
            if subscription is not _UNRESOLVED:
                kwargs['subscription'] = subscription
        allowance = await run_blocking(db_executor, funded_allowance, self.uid, self.source, lane='live', **kwargs)
        self.failures = min(self.failures + 1, 5) if allowance.reason == 'allowance_unavailable' else 0
        self.remaining, self.reason, self.managed = allowance.remaining_seconds, allowance.reason, allowance.managed
        self.remaining_units = allowance.remaining_units
        self.budget_units = allowance.budget_units
        if self.usage_cache is not None and self.remaining_units is None and self.reason != 'allowance_unavailable':
            self.usage_cache.invalidate()
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

    def note_held(self, received_at, seconds):
        """Record the receipt span of audio the receiver denied before any provider.

        Spans are wall clock, so channels overlap and bursts collapse to their
        arrival time. Socket-level suppression of already-admitted queued audio is
        not recorded: its receipt window may already be billed.
        """
        start, end = received_at - seconds, received_at
        spans = self.held_spans
        if spans and start <= spans[-1][1] + HELD_SPAN_MERGE_GAP_SECONDS:
            spans[-1][0] = min(spans[-1][0], start)
            spans[-1][1] = max(spans[-1][1], end)
            return
        spans.append([start, end])
        if len(spans) > MAX_HELD_SPANS:
            del spans[0]  # Dropping a span bills it as before; never subtracts more.

    def held_seconds_between(self, start, end):
        """Held wall-clock seconds in [start, end]; spans ending by `end` are released."""
        held = sum(max(0.0, min(end, b) - max(start, a)) for a, b in self.held_spans)
        self.held_spans = [[max(a, end), b] for a, b in self.held_spans if b > end]
        return held

    def record_suppressed(self, provider, seconds):
        record_audio('live', 'suppressed', provider, seconds, self.reason == 'plan_allowance_exhausted')

    def send(self, raw, data, provider, rate, *args, **kwargs):
        if not self.packet_allowed(data, provider, rate):
            self.record_suppressed(provider, len(data) / (2 * rate))
            self.observe_capture(False)
            # Policy absorption is not a transport failure. The receive/archive
            # paths continue, and recovery must not fail over or close capture.
            return True
        accepted = raw.send(data, *args, **kwargs)
        if accepted is not False:
            self.observe_capture(True)
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

    def observe_capture(self, admitted):
        capture, self.active_capture = self.active_capture, None
        if capture is not None and self.capture_observer is not None:
            data, rate, spans = capture
            offset = 0
            for start, samples in spans:
                self.capture_observer(data[offset : offset + samples * 2], rate, start, admitted)
                offset += samples * 2


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

    def set_cap_capture(self, data, spans):
        self.admission.active_capture = (data, self.rate, tuple(spans)) if spans else None

    def suppress(self, data, start_sample=None):
        if start_sample is not None:
            self.admission.active_capture = (data, self.rate, ((start_sample, len(data) // 2),))
        if self.raw is None or not self.admission.packet_allowed(data, self.provider, self.rate):
            self.admission.record_suppressed(self.provider, len(data) / (2 * self.rate))
            self.admission.observe_capture(False)
            return True
        return False

    def send(self, data, *args, **kwargs):
        if self.raw is None:
            self.admission.record_suppressed(self.provider, len(data) / (2 * self.rate))
            self.admission.observe_capture(False)
            return True
        return self.admission.send(self.raw, data, self.provider, self.rate, *args, **kwargs)

    def finish(self):
        self.closed = True
        if self.raw is not None:
            return self.raw.finish()

    def finalize(self, *args, **kwargs):
        if self.raw is not None:
            # The proxy exposes the provider's class, so managed window VAD
            # calls finalize(vad_pause=True) through it. Preserve that protocol
            # just as send() does; otherwise a local TypeError kills the leg.
            if os.getenv('STT_CAP_FINALIZE_FORWARD_ENABLED', 'true').strip().lower() not in {'false', '0', 'off'}:
                return self.raw.finalize(*args, **kwargs)
            # Emergency generic-finalize mode retains the provider's no-arg
            # behavior without reintroducing the proxy signature exception.
            return self.raw.finalize()


def live_provider(provider, rate_index):
    """Applied at actual provider constructors, including fallback constructors."""

    def decorate(fn):
        @wraps(fn)
        async def connect(*args, **kwargs):
            admission = current_live_admission.get()
            if admission is not None and not execution_admission_enabled(admission.uid, 'live'):
                admission = None
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


def suppress_socket_audio(socket, data, start_sample=None):
    # Explicit identity avoids treating test doubles or unrelated adapters as
    # cap owners. Suppress before VAD/timeline adapters record provider spans.
    return getattr(socket, 'cap_dispatch_socket', False) is True and socket.suppress(data, start_sample=start_sample)


def set_cap_capture(socket, data, spans):
    if getattr(socket, 'cap_dispatch_socket', False) is True:
        socket.set_cap_capture(data, spans)
