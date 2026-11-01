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

from config.batch_live_preview import local_preview_batch_owned
from config.cloud_live_stt import local_preview_batch_enabled
from utils.metrics import OMI_LISTEN_LOCAL_PREVIEW_SESSIONS_TOTAL
from utils.observability.reasons import LocalPreviewOutcome, ReasonFamily, reason_label
from utils.observability.transcription import bounded_client_platform

logger = logging.getLogger(__name__)

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
        host.local_preview_batch = False
    return bool(getattr(host, 'local_preview_batch', False))
