"""Mobile local-preview lane: batch-lane phones render their own live preview.

A client that declares `local_preview=enabled` renders an on-device streaming
preview and journals every pendant frame through the mobile Standard batch
route (lossless WAL, `/v2/sync-local-files`, batch record). When this session
admits it, listen tells the client so on `ready` / `mobile_batch_admission`,
and defers the cloud provider stream until audio actually reaches the socket.
Audio the journal refuses still arrives here and gets today's live transcript.

Realtime apps and webhooks degrade for these sessions by ruling (David,
2026-10-25): integrations do not keep a cloud stream open.
"""

import logging
import os
import time
from dataclasses import replace

from prometheus_client import Counter, Histogram

from config.batch_live_preview import local_preview_batch_owned
from config.cloud_live_stt import OFF, STREAM, local_preview_batch_enabled
from config.server_batch import owned
from utils.metrics import (
    OMI_CLOUD_LIVE_STT_SAVED_SECONDS_TOTAL,
    OMI_LISTEN_LOCAL_PREVIEW_SESSIONS_TOTAL,
)
from utils.observability.fallback import record_fallback
from utils.observability.reasons import (
    LocalPreviewEngineUnavailableReason,
    LocalPreviewOutcome,
    ReasonFamily,
    reason_label,
)
from utils.observability.transcription import bounded_client_platform
from utils.stt.outcomes import bounded_provider
from utils.stt.provider_stream_end import begin_stream_close
from utils.stt.replay_delivery import abort_replay_socket
from utils.stt.socket import release_live_stt_socket

logger = logging.getLogger(__name__)

# Upper bound on the provider connection time a deferred open costs: an idle
# close can end the provider socket earlier, never later than session teardown.
OMI_LISTEN_DEFERRED_STREAM_OPEN_SECONDS = Histogram(
    'omi_listen_deferred_stream_open_seconds',
    'Seconds from a deferred cloud live STT stream opening to session teardown, by why it was deferred and provider',
    ['deferred_by', 'provider'],
    buckets=(2, 5, 15, 30, 60, 120, 300, 900, 1800, 3600, 7200),
)

OMI_LISTEN_LOCAL_PREVIEW_ENGINE_UNAVAILABLE_TOTAL = Counter(
    'omi_listen_local_preview_engine_unavailable_total',
    'Granted local-preview sockets reporting no usable phone speech engine, by bounded platform and reason',
    ['client_platform', 'reason'],
)

ADMITTED = LocalPreviewOutcome.ADMITTED.value
# Closed reason set; every refusal keeps today's streaming behavior.
REASONS = frozenset(outcome.value for outcome in LocalPreviewOutcome) - {LocalPreviewOutcome.UNKNOWN.value}


def local_preview_reason(host) -> str:
    """Why this session does or does not run the local-preview lane."""

    request = host.request
    if not getattr(request, 'local_preview', False):
        return 'not_requested'
    if not local_preview_batch_enabled():
        return 'kill_switch'
    if getattr(host, 'use_custom_stt', False):
        return 'custom_stt'
    if getattr(host, 'is_multi_channel', False):
        return 'multi_channel'
    if getattr(request, 'onboarding_mode', False):
        return 'onboarding'
    if getattr(request, 'source', None) == 'phone_call':
        return 'phone_call'
    # The batch route archives through private cloud sync; without it there is no record.
    if not getattr(host, 'private_cloud_sync_enabled', False):
        return 'private_sync_off'
    try:
        if not local_preview_batch_owned(request.uid):
            return 'not_batch_lane'
    except Exception as error:
        logger.warning('Local preview batch policy failed type=%s', type(error).__name__)
        return 'policy_error'
    return ADMITTED


def admit_local_preview(host) -> bool:
    """Pin the session's decision once, before STT initialization. Never raises."""

    if getattr(host, '_local_preview_pinned', False):
        return bool(getattr(host, 'local_preview_batch', False))
    try:
        reason = local_preview_reason(host)
    except Exception as error:
        logger.warning('Local preview admission failed type=%s', type(error).__name__)
        reason = 'policy_error'
    host.local_preview_batch = reason == ADMITTED
    host._local_preview_pinned = True
    try:
        platform = getattr(getattr(host, 'client_device_context', None), 'platform', None)
        OMI_LISTEN_LOCAL_PREVIEW_SESSIONS_TOTAL.labels(
            outcome=reason_label(ReasonFamily.LIVE_STT, reason, LocalPreviewOutcome),
            client_platform=bounded_client_platform(platform),
        ).inc()
    except Exception:
        pass  # Telemetry never interrupts session start.
    return host.local_preview_batch


def renew_local_preview(host) -> bool:
    """Lease renewal: the kill switch revokes mid-session; nothing else re-admits."""

    if getattr(host, 'local_preview_batch', False) and not local_preview_batch_enabled():
        revoke_local_preview(host, reason='kill_switch')
    return bool(getattr(host, 'local_preview_batch', False))


def note_deferred_stream_closed(receiver) -> None:
    """At teardown, observe once how long a deferred open kept a stream: a stop-time flush reads seconds."""

    opened_at = getattr(receiver, '_deferred_open_at', None)
    if opened_at is None:
        return
    receiver._deferred_open_at = None
    try:
        OMI_LISTEN_DEFERRED_STREAM_OPEN_SECONDS.labels(
            deferred_by=getattr(receiver, '_cloud_live_deferred_by', None) or 'off',
            provider=bounded_provider(receiver._serving_provider()),
        ).observe(max(0.0, time.monotonic() - opened_at))
    except Exception:
        pass  # Telemetry never blocks teardown.


def rescind_local_preview(host, payload) -> bool:
    """Count once per granted socket and revoke one-way, including lease renewal."""
    if (
        not getattr(host.request, 'local_preview', False)
        or not getattr(host, 'local_preview_batch', False)
        or getattr(host, '_local_preview_engine_reported', False)
    ):
        return False
    host._local_preview_engine_reported = True
    try:
        reason = LocalPreviewEngineUnavailableReason(payload.get('reason'))
    except (TypeError, ValueError):
        reason = LocalPreviewEngineUnavailableReason.OTHER
    if reason == LocalPreviewEngineUnavailableReason.UNKNOWN:
        reason = LocalPreviewEngineUnavailableReason.OTHER
    try:
        platform = getattr(getattr(host, 'client_device_context', None), 'platform', None)
        OMI_LISTEN_LOCAL_PREVIEW_ENGINE_UNAVAILABLE_TOTAL.labels(
            client_platform=bounded_client_platform(platform),
            reason=reason_label(ReasonFamily.LIVE_STT, reason, LocalPreviewEngineUnavailableReason),
        ).inc()
    except Exception:
        pass  # Telemetry never interrupts capture.
    if os.getenv('LOCAL_PREVIEW_ENGINE_RESCIND_ENABLED', 'true').strip().lower() in {'false', '0', 'off', 'no'}:
        return False
    revoke_local_preview(host, reason='engine_error')
    return True


def revoke_local_preview(host, *, reason: str) -> None:
    """Share the one-way state transition for engine failure and lease revocation."""
    host.local_preview_batch = False
    host._local_preview_pinned = True
    host.request = replace(host.request, local_preview=False)
    host._local_preview_engine_rescinded = True
    record_fallback(
        component='stt_live_session',
        from_mode='local_preview',
        to_mode='batch_only' if batch_only_live_path(host) else 'live',
        reason=reason,
        outcome='degraded',
    )


def batch_only_live_path(host) -> bool:
    """Revoked grants suppress the normal stream only with durable batch custody."""
    if getattr(host, '_local_preview_engine_rescinded', False) is True:
        return owned(getattr(host, 'batch_record_capture', None) or {})
    return getattr(host, 'server_batch_only', False) is True


def restore_non_preview_path(receiver) -> None:
    """Keep owned captures batch-only; unowned captures retain their normal live path."""
    if batch_only_live_path(receiver.host):
        close_rescinded_stream(receiver)
    # Otherwise leave any existing provider and demand policy intact. A deferred
    # session opens its normal non-preview stream on the next audio flush.


def record_cloud_live_saved_seconds(receiver, request, decoded_audio_bytes: int) -> None:
    """Provider stream seconds this session's policy mode would not have spent. Telemetry only."""

    try:
        mode = getattr(receiver, '_cloud_live_mode', None) or STREAM
        if mode == STREAM:
            return
        sample_rate = max(1, int(getattr(request, 'sample_rate', 16000)))
        if mode == OFF:
            if not getattr(receiver, 'cloud_live_suppressed', False):
                return  # The deferred stream opened; this audio went to a provider.
            OMI_CLOUD_LIVE_STT_SAVED_SECONDS_TOTAL.labels(mode=mode).inc(decoded_audio_bytes / (sample_rate * 2))
            return
        # when_watched: hidden seconds (background + foreground-not-visible)
        # would leave the paid vendor lane for the Parakeet window leg.
        totals = receiver.host.state.realtime_demand.totals()
        OMI_CLOUD_LIVE_STT_SAVED_SECONDS_TOTAL.labels(mode=mode).inc(
            totals.get('background', 0.0) + totals.get('foreground', 0.0)
        )
    except Exception as error:
        logger.warning('Cloud live mode telemetry failed type=%s', type(error).__name__)


def close_rescinded_stream(receiver) -> None:
    """Retire any journal-refusal carve-out before a visible-only stream can open."""
    receiver.cloud_live_suppressed = True
    monitor = getattr(receiver, '_stt_death_monitor_task', None)
    if monitor is not None:
        monitor.cancel()  # Optional preview has its own non-terminal health monitor.
    recovery = getattr(receiver, '_replay_recovery_task', None)
    if recovery is not None:
        recovery.cancel()
    socket = getattr(receiver, 'stt_socket', None)
    receiver.stt_socket = None
    if socket is None:
        return
    try:
        begin_stream_close(socket)
        socket.finish()
    except Exception as error:
        logger.warning('Rescinded preview stream close failed type=%s', type(error).__name__)
    finally:
        release_live_stt_socket(socket)
        receiver.host.spawn(abort_replay_socket(socket, timeout=2), name='local_preview_rescind_close')
