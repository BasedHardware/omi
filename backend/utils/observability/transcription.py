"""Bounded instrumentation for voice, sync, and live transcription outcomes."""

from __future__ import annotations

import os
import re
from time import monotonic
from typing import Any, Callable, Literal, Mapping

from models.conversation_enums import ConversationSource
from utils.metrics import (
    OMI_LIVE_STT_ACCEPTED_TOTAL,
    OMI_LIVE_STT_TERMINAL_TOTAL,
    OMI_LIVE_STT_TERMINAL_FAILURES_TOTAL,
    OMI_LISTEN_ACCEPTED_TOTAL,
    OMI_LISTEN_AUDIO_OUTCOME_TOTAL,
    OMI_LISTEN_UNKNOWN_CHANNEL_PREFIX_TOTAL,
    OMI_SYNC_TRANSCRIPTION_JOBS_TOTAL,
    OMI_SYNC_TRANSCRIPTION_SEGMENTS_TOTAL,
    OMI_TRANSCRIPTION_ACCEPTED_TOTAL,
    OMI_TRANSCRIPTION_COMPLETED_TOTAL,
    OMI_TRANSCRIPTION_LATENCY_SECONDS,
)
from utils.env_loader import resolve_stage_from_env
from utils.product_telemetry import emit_product_event
from utils.stt.outcomes import TranscriptionOutcome, bounded_provider

_ROUTES = {'voice_chat_sse', 'voice_rest_multipart', 'voice_rest_pcm', 'sync'}
_PLATFORMS = {'android', 'desktop', 'ios', 'linux', 'macos', 'mobile', 'web', 'windows'}
_REVISION_PATTERN = re.compile(r'[^a-zA-Z0-9_.-]')
_SYNC_LANES = {'backfill', 'fresh'}
_SYNC_MODELS = {'nova-3', 'parakeet', 'velma-2'}
_LIVE_PHASES = {'connection', 'initialization', 'send'}
_LIVE_TERMINAL_OUTCOMES = frozenset({'success', 'failure', 'cancelled'})
_LIVE_TERMINAL_PHASES = frozenset({'connection', 'initialization', 'send', 'teardown', 'transcript_delivery'})
_LISTEN_AUDIO_OUTCOMES = frozenset({'first_audio', 'no_audio_teardown'})
LiveSTTTerminalOutcome = Literal['success', 'failure', 'cancelled']
LiveSTTTerminalPhase = Literal['connection', 'initialization', 'send', 'teardown', 'transcript_delivery']


def _bounded_route(route: str) -> str:
    return route if route in _ROUTES else 'other'


def _bounded_platform(platform: str | None) -> str:
    normalized = (platform or '').strip().lower()
    return normalized if normalized in _PLATFORMS else 'unknown'


def _bounded_source(source: str | None) -> str:
    normalized = (source or '').strip()
    try:
        return ConversationSource(normalized).value if normalized else ConversationSource.unknown.value
    except ValueError:
        return ConversationSource.unknown.value


def _deployment_version() -> str:
    raw = os.getenv('K_REVISION') or os.getenv('OMI_DEPLOYMENT_VERSION') or 'unknown'
    sanitized = _REVISION_PATTERN.sub('_', raw.strip())[:80]
    return sanitized or 'unknown'


def _deployment_environment() -> str:
    """Return the closed deployment category, never a revision or image identifier."""

    return resolve_stage_from_env() or 'unknown'


class TranscriptionAttempt:
    """Records one accepted journey and at most one terminal semantic outcome."""

    def __init__(self, *, route: str, provider: str | None, platform: str | None) -> None:
        self.route = _bounded_route(route)
        self.provider = bounded_provider(provider)
        self.platform = _bounded_platform(platform)
        self.deployment_version = _deployment_version()
        self.started_at = monotonic()
        self._outcome: TranscriptionOutcome | None = None
        OMI_TRANSCRIPTION_ACCEPTED_TOTAL.labels(
            route=self.route,
            provider=self.provider,
            client_platform=self.platform,
            deployment_version=self.deployment_version,
        ).inc()

    @property
    def finished(self) -> bool:
        return self._outcome is not None

    @property
    def outcome(self) -> TranscriptionOutcome | None:
        return self._outcome

    def finish(self, outcome: TranscriptionOutcome) -> None:
        if self._outcome is not None:
            return
        self._outcome = outcome
        labels = {
            'route': self.route,
            'provider': self.provider,
            'outcome': outcome.value,
            'client_platform': self.platform,
            'deployment_version': self.deployment_version,
        }
        OMI_TRANSCRIPTION_COMPLETED_TOTAL.labels(**labels).inc()
        OMI_TRANSCRIPTION_LATENCY_SECONDS.labels(**labels).observe(max(0.0, monotonic() - self.started_at))


class LiveSTTAttempt:
    """One listener-local accepted live-STT attempt and at most one terminal outcome."""

    def __init__(
        self,
        *,
        provider: str | None,
        platform: str | None,
        uid: str | None = None,
        recording_id: str | None = None,
        conversation_id: str | None = None,
        source: str | None = None,
        model: str | None = None,
        language: str | None = None,
        emitter: Callable[..., None] = emit_product_event,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.provider = bounded_provider(provider)
        self.platform = _bounded_platform(platform)
        self.deployment_environment = _deployment_environment()
        self.uid = uid
        self.recording_id = recording_id
        self.conversation_id = conversation_id
        self.source = _bounded_source(source)
        self.model = model or 'unknown'
        self.language = language or 'unknown'
        self._emitter = emitter
        self._clock = clock
        self._started_at = clock()
        self._finished = False
        OMI_LIVE_STT_ACCEPTED_TOTAL.labels(
            provider=self.provider,
            client_platform=self.platform,
            deployment_environment=self.deployment_environment,
        ).inc()
        self._emit('Transcript Started', self._base_properties())

    @property
    def finished(self) -> bool:
        return self._finished

    def finish(self, outcome: LiveSTTTerminalOutcome, *, phase: LiveSTTTerminalPhase) -> None:
        if self._finished:
            return
        if outcome not in _LIVE_TERMINAL_OUTCOMES:
            raise ValueError(f'unknown live-STT terminal outcome: {outcome}')
        if phase not in _LIVE_TERMINAL_PHASES:
            raise ValueError(f'unknown live-STT terminal phase: {phase}')
        self._finished = True
        OMI_LIVE_STT_TERMINAL_TOTAL.labels(
            provider=self.provider,
            outcome=outcome,
            client_platform=self.platform,
            deployment_environment=self.deployment_environment,
            phase=phase,
        ).inc()
        properties = {
            **self._base_properties(),
            'duration_seconds': max(0.0, self._clock() - self._started_at),
            'phase': phase,
        }
        event = {
            'success': 'Transcript Completed',
            'failure': 'Transcript Failed',
            'cancelled': 'Transcript Cancelled',
        }[outcome]
        self._emit(event, properties)

    def _base_properties(self) -> dict[str, Any]:
        return {
            'recording_id': self.recording_id,
            'conversation_id': self.conversation_id,
            'transcription_source': self.source,
            'stt_provider': self.provider,
            'stt_model': self.model,
            'transcript_language': self.language,
            'app_platform': self.platform,
        }

    def _emit(self, event: str, properties: Mapping[str, Any]) -> None:
        if not self.uid:
            return
        try:
            self._emitter(uid=self.uid, event=event, properties=properties)
        except Exception:
            # Product analytics is subordinate to the transcription contract.
            return


def record_sync_transcription_outcome(
    *,
    kind: str,
    provider: str | None,
    model: str | None,
    lane: str | None,
    outcome: TranscriptionOutcome,
) -> None:
    """Record a bounded sync job or segment terminal outcome."""

    if kind not in {'job', 'segment'}:
        raise ValueError('kind must be job or segment')
    counter = OMI_SYNC_TRANSCRIPTION_SEGMENTS_TOTAL if kind == 'segment' else OMI_SYNC_TRANSCRIPTION_JOBS_TOTAL
    bounded_model = model if model in _SYNC_MODELS else 'unknown'
    bounded_lane = lane if lane in _SYNC_LANES else 'unknown'
    counter.labels(
        provider=bounded_provider(provider),
        model=bounded_model,
        lane=bounded_lane,
        outcome=outcome.value,
        deployment_version=_deployment_version(),
    ).inc()


def record_live_stt_failure(
    *,
    provider: str | None,
    platform: str | None,
    outcome: TranscriptionOutcome,
    phase: str,
) -> None:
    """Record a bounded terminal live-STT failure without session identifiers."""

    terminal_outcome = (
        outcome
        if outcome
        not in {
            TranscriptionOutcome.SUCCESS,
            TranscriptionOutcome.EXPECTED_SILENCE,
        }
        else TranscriptionOutcome.UPSTREAM_ERROR
    )
    OMI_LIVE_STT_TERMINAL_FAILURES_TOTAL.labels(
        provider=bounded_provider(provider),
        outcome=terminal_outcome.value,
        client_platform=_bounded_platform(platform),
        deployment_environment=_deployment_environment(),
        phase=phase if phase in _LIVE_PHASES else 'unknown',
    ).inc()


def record_listen_session_accepted(*, source: str | None, platform: str | None) -> None:
    """Count one accepted /v4/listen socket with bounded labels only."""

    OMI_LISTEN_ACCEPTED_TOTAL.labels(
        transcription_source=_bounded_source(source),
        client_platform=_bounded_platform(platform),
    ).inc()


def record_listen_audio_outcome(*, source: str | None, outcome: str, platform: str | None) -> None:
    """Record a per-session listen audio funnel outcome (first audio / silent teardown)."""

    if outcome not in _LISTEN_AUDIO_OUTCOMES:
        raise ValueError(f'unknown listen audio outcome: {outcome}')
    OMI_LISTEN_AUDIO_OUTCOME_TOTAL.labels(
        transcription_source=_bounded_source(source),
        outcome=outcome,
        client_platform=_bounded_platform(platform),
    ).inc()


def record_listen_unknown_channel_prefix(*, source: str | None, platform: str | None) -> None:
    """Count a multi-channel frame dropped because its channel prefix was unknown."""

    OMI_LISTEN_UNKNOWN_CHANNEL_PREFIX_TOTAL.labels(
        transcription_source=_bounded_source(source),
        client_platform=_bounded_platform(platform),
    ).inc()
