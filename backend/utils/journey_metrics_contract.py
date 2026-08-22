"""Bounded label contract for client-segmented product journey metrics.

``X-App-Platform`` is authoritative when present. User-Agent matching is only
a compatibility fallback for clients that have not adopted that header.

The macOS and Windows pi-mono extensions currently send the identical
``OpenAI/JS 6.26.0`` User-Agent without a platform header. They are deliberately
reported as ``pi_mono_unknown_os``; inferring an operating system would turn an
unattributable population into misleading telemetry. Once those clients send
``X-App-Platform``, the header resolves them to the corresponding desktop kind.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

ClientJourneyName = Literal[
    'desktop_chat',
    'mobile_chat',
    'live_transcription',
    'conversation_finalization',
    'memory_retrieval',
    'desktop_proactivity',
    'app_webhook_delivery',
    'realtime_voice',
    'unknown',
]
ClientJourneyOutcome = Literal['success', 'failure', 'degraded', 'cancelled', 'unknown']
ClientJourneyIssueClass = Literal[
    'upstream_rejected',
    'upstream_timeout',
    'provider_error',
    'empty_answer',
    'invalid_response',
    'dependency_unavailable',
    'quota_capped',
    'canned_fallback',
    'incomplete_attempt',
    'incomplete_stream',
    'unknown',
]
ClientKind = Literal[
    'mobile_android',
    'mobile_ios',
    'desktop_macos',
    'desktop_windows',
    'desktop_linux',
    'desktop_unknown_os',
    'web',
    'dart_mobile_unknown_os',
    'pi_mono_unknown_os',
    'unknown',
]

CLIENT_JOURNEYS: tuple[ClientJourneyName, ...] = (
    'desktop_chat',
    'mobile_chat',
    'live_transcription',
    'conversation_finalization',
    'memory_retrieval',
    'desktop_proactivity',
    'app_webhook_delivery',
    'realtime_voice',
    'unknown',
)
CLIENT_JOURNEY_OUTCOMES: tuple[ClientJourneyOutcome, ...] = (
    'success',
    'failure',
    'degraded',
    'cancelled',
    'unknown',
)
CLIENT_JOURNEY_ISSUE_CLASSES: tuple[ClientJourneyIssueClass, ...] = (
    'upstream_rejected',
    'upstream_timeout',
    'provider_error',
    'empty_answer',
    'invalid_response',
    'dependency_unavailable',
    'quota_capped',
    'canned_fallback',
    'incomplete_attempt',
    'incomplete_stream',
    'unknown',
)
CLIENT_KINDS: tuple[ClientKind, ...] = (
    'mobile_android',
    'mobile_ios',
    'desktop_macos',
    'desktop_windows',
    'desktop_linux',
    'desktop_unknown_os',
    'web',
    'dart_mobile_unknown_os',
    'pi_mono_unknown_os',
    'unknown',
)

_CLIENT_JOURNEY_SET = frozenset(CLIENT_JOURNEYS)
_CLIENT_JOURNEY_OUTCOME_SET = frozenset(CLIENT_JOURNEY_OUTCOMES)
_CLIENT_JOURNEY_ISSUE_CLASS_SET = frozenset(CLIENT_JOURNEY_ISSUE_CLASSES)
_CLIENT_KIND_SET = frozenset(CLIENT_KINDS)
_PLATFORM_CLIENT_KIND: dict[str, ClientKind] = {
    'android': 'mobile_android',
    'ios': 'mobile_ios',
    'macos': 'desktop_macos',
    'windows': 'desktop_windows',
    'linux': 'desktop_linux',
    'desktop': 'desktop_unknown_os',
    'mobile': 'dart_mobile_unknown_os',
    'web': 'web',
}


def _bounded(value: object | None, *, max_length: int = 128) -> str:
    """Normalize and truncate a possible label value before allowlist lookup."""

    raw_value = getattr(value, 'value', value)
    if raw_value is None:
        return 'unknown'
    normalized = str(raw_value).strip().lower().replace(' ', '_').replace('-', '_')
    return normalized[:max_length] if normalized else 'unknown'


def bounded_client_journey(value: object | None) -> ClientJourneyName:
    normalized = _bounded(value)
    return normalized if normalized in _CLIENT_JOURNEY_SET else 'unknown'


def bounded_client_journey_outcome(value: object | None) -> ClientJourneyOutcome:
    normalized = _bounded(value)
    return normalized if normalized in _CLIENT_JOURNEY_OUTCOME_SET else 'unknown'


def bounded_client_journey_issue_class(value: object | None) -> ClientJourneyIssueClass:
    normalized = _bounded(value)
    return normalized if normalized in _CLIENT_JOURNEY_ISSUE_CLASS_SET else 'unknown'


def bounded_client_kind(value: object | None) -> ClientKind:
    normalized = _bounded(value)
    return normalized if normalized in _CLIENT_KIND_SET else 'unknown'


def resolve_client_kind(*, x_app_platform: object | None, user_agent: object | None) -> ClientKind:
    """Resolve a closed client population, preferring the explicit platform.

    An unrecognized non-empty platform remains ``unknown`` instead of falling
    through to a potentially contradictory User-Agent. Header values of the
    wrong type also collapse to ``unknown`` instead of raising or falling back.
    """

    if x_app_platform is not None and not isinstance(x_app_platform, str):
        return 'unknown'
    if isinstance(x_app_platform, str) and x_app_platform.strip():
        return _PLATFORM_CLIENT_KIND.get(_bounded(x_app_platform), 'unknown')
    if user_agent is not None and not isinstance(user_agent, str):
        return 'unknown'

    normalized_user_agent = _bounded(user_agent, max_length=256)
    if 'openai/js' in normalized_user_agent:
        return 'pi_mono_unknown_os'
    if 'cfnetwork/' in normalized_user_agent or 'darwin/' in normalized_user_agent:
        return 'desktop_macos'
    if 'electron/' in normalized_user_agent and 'windows' in normalized_user_agent:
        return 'desktop_windows'
    if normalized_user_agent.startswith('dart/') or 'dart:io' in normalized_user_agent:
        return 'dart_mobile_unknown_os'
    return 'unknown'


def resolve_client_kind_from_headers(headers: Mapping[str, str]) -> ClientKind:
    """Resolve client kind from a case-insensitive HTTP header mapping."""

    normalized_headers = {key.lower(): value for key, value in headers.items()}
    return resolve_client_kind(
        x_app_platform=normalized_headers.get('x-app-platform'),
        user_agent=normalized_headers.get('user-agent'),
    )
