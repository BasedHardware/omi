"""Archival acknowledgement for legacy handles retired by the 2026-10-15..17 expiry path.

Expiry retirement removed accepted uploads' Redis jobs and left their content
claims ``retryable`` without a job id, so ``GET /v2/sync-local-files/{id}``
returns 404 for those handles forever. The phone confirms a missing handle only
after a second 404 at least five minutes later in the same process, which a
large dead backlog never reaches. The rows stay "On the Way", and the poll
budget they consume starves status checks for new uploads.

The server already holds every retired content in custody: restored and on a
temporary hold. An operator records each retired handle in
``sync_retired_handles/{handle}`` with its owner and content, and admits the
owner in ``sync_retired_handle_owners/{uid}`` (``enabled: true``). For an
admitted owner's handle with no Redis job and no proven completion, the status
route answers ``completed`` with an empty result and
``reason_code='sync_retired_preserved'``. Released apps accept only
``completed`` as terminal-without-retry. ``failed`` re-uploads, and an unknown
status polls forever.

This is an archival acknowledgement, not a transcription result. The content
ledger is left untouched: the content stays ``retryable`` and remains eligible
for an operator redrive from the custody copy. A later real completion found
through the existing reconciliation paths always wins, because this read runs
only after they decline.

Kill switch: ``SYNC_RETIRED_HANDLE_ACK_ENABLED``. Unset or blank means on, and
any value other than an on-token means off. Without owner documents nothing is
acknowledged, so the per-owner allowlist (no UIDs in the manifest) is the
rollout control.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from google.cloud import firestore

from database._client import get_firestore_client
from database.batch_pipeline_privacy import BatchPrivacyBlocked, assert_batch_write_allowed
from utils.observability.fallback import record_fallback
from utils.sync.stage import collection_name

logger = logging.getLogger(__name__)

ENABLED_ENV = 'SYNC_RETIRED_HANDLE_ACK_ENABLED'
HANDLES = 'sync_retired_handles'
OWNERS = 'sync_retired_handle_owners'
REASON_CODE = 'sync_retired_preserved'
_ON_VALUES = frozenset({'1', 'true', 'on', 'yes', 'enabled'})


def retired_handle_ack_enabled() -> bool:
    raw = os.getenv(ENABLED_ENV, '').strip().lower()
    return not raw or raw in _ON_VALUES


def _valid_id(value: object, limit: int) -> bool:
    return isinstance(value, str) and 0 < len(value) <= limit and '/' not in value and value.strip() == value


def get_retired_handle_ack(job_id: str, uid: str, *, firestore_client: Any = None) -> dict[str, Any] | None:
    """Terminal archival status for an admitted owner's custody handle, else None.

    Called only when Redis has no job and no durable completion was proven.
    Unknown handles, other owners, unadmitted owners, malformed records and
    privacy-fenced accounts all decline, so the route keeps its 404.
    """
    if not retired_handle_ack_enabled():
        return None
    if not _valid_id(job_id, 128) or job_id.startswith('bp_') or not _valid_id(uid, 256):
        return None
    client = firestore_client if firestore_client is not None else get_firestore_client()

    @firestore.transactional
    def read(transaction: Any) -> dict[str, Any] | None:
        handle = client.collection(collection_name(HANDLES)).document(job_id).get(transaction=transaction)
        record = handle.to_dict() if getattr(handle, 'exists', False) else None
        if not isinstance(record, dict) or record.get('uid') != uid or record.get('job_id') != job_id:
            return None
        if not _valid_id(record.get('content_id'), 256):
            return None
        owner = client.collection(collection_name(OWNERS)).document(uid).get(transaction=transaction)
        admitted = owner.to_dict() if getattr(owner, 'exists', False) else None
        if not isinstance(admitted, dict) or admitted.get('enabled') is not True:
            return None
        # Same account fence as durable completion: a deleted or blocked
        # account never receives a synthetic terminal status.
        assert_batch_write_allowed(client, transaction, uid, conversation_ids=())
        return {
            'job_id': job_id,
            'status': 'completed',
            'lane': 'backfill',
            'total_segments': 0,
            'processed_segments': 0,
            'successful_segments': 0,
            'failed_segments': 0,
            'reason_code': REASON_CODE,
            'result': {
                'new_memories': [],
                'updated_memories': [],
                'failed_segments': 0,
                'total_segments': 0,
                'errors': [],
            },
        }

    try:
        status = read(client.transaction())
    except BatchPrivacyBlocked as error:
        logger.warning('event=sync_retired_handle_ack outcome=privacy_blocked fence_reason=%s', error.reason.value)
        return None
    if not isinstance(status, dict):
        return None
    if status.get('status') == 'completed':
        logger.info('event=sync_retired_handle_ack outcome=acknowledged')
        record_fallback(
            component='sync_dispatch',
            from_mode='redis_status',
            to_mode='retired_custody_ack',
            reason='unavailable',
            outcome='recovered',
        )
    return status


def acknowledge_retired_handle(job_id: str, uid: str) -> dict[str, Any] | None:
    """Route boundary: lookup errors fail open to the pre-existing 404, never a 5xx."""
    try:
        return get_retired_handle_ack(job_id, uid)
    except Exception as error:
        logger.error('event=sync_retired_handle_ack outcome=lookup_failed exception_type=%s', type(error).__name__)
        record_fallback(
            component='sync_dispatch',
            from_mode='retired_custody_ack',
            to_mode='redis_status',
            reason='unavailable',
            outcome='degraded',
        )
        return None
