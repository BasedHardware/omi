"""Bounded instrumentation for voice, sync, and live transcription outcomes."""

from __future__ import annotations

import os
import re
from time import monotonic

from utils.metrics import (
    OMI_LIVE_STT_TERMINAL_FAILURES_TOTAL,
    OMI_SYNC_TRANSCRIPTION_JOBS_TOTAL,
    OMI_SYNC_TRANSCRIPTION_SEGMENTS_TOTAL,
    OMI_TRANSCRIPTION_ACCEPTED_TOTAL,
    OMI_TRANSCRIPTION_COMPLETED_TOTAL,
    OMI_TRANSCRIPTION_LATENCY_SECONDS,
)
from utils.stt.outcomes import TranscriptionOutcome, bounded_provider

_ROUTES = {'voice_chat_sse', 'voice_rest_multipart', 'voice_rest_pcm', 'sync'}
_PLATFORMS = {'android', 'desktop', 'ios', 'linux', 'macos', 'mobile', 'web', 'windows'}
_REVISION_PATTERN = re.compile(r'[^a-zA-Z0-9_.-]')
_SYNC_LANES = {'backfill', 'fresh'}
_SYNC_MODELS = {'nova-3', 'parakeet', 'velma-2'}
_LIVE_PHASES = {'connection', 'initialization', 'send'}


def _bounded_route(route: str) -> str:
    return route if route in _ROUTES else 'other'


def _bounded_platform(platform: str | None) -> str:
    normalized = (platform or '').strip().lower()
    return normalized if normalized in _PLATFORMS else 'unknown'


def _deployment_version() -> str:
    raw = os.getenv('K_REVISION') or os.getenv('OMI_DEPLOYMENT_VERSION') or 'unknown'
    sanitized = _REVISION_PATTERN.sub('_', raw.strip())[:80]
    return sanitized or 'unknown'


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
        deployment_version=_deployment_version(),
        phase=phase if phase in _LIVE_PHASES else 'unknown',
    ).inc()
