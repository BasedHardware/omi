"""Always-encrypted, bounded grouping sidecars inside the existing transcript write.

Provenance lasts with its transcript for safe reprocessing. Experimental identity
predictions expire after 30 days, independently of the account protection level.
No audio, vectors, extra storage calls or encryption-key network calls.
"""

# LIFECYCLE: permanent
import json
import logging
import time
from typing import Any

from models.transcript_segment import GROUPING_INTERNAL_FIELDS, strip_grouping_internal_fields
from utils import encryption
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
FIELD = 'speaker_grouping_internal'
MAX_SEGMENTS = 256
MAX_BYTES = 64 * 1024
MAX_ENCODED_BYTES = 96 * 1024
PREDICTION_TTL_SECONDS = 30 * 24 * 60 * 60


def _unavailable(outcome: str) -> None:
    try:
        record_fallback(
            component='other',
            from_mode='speaker_grouping',
            to_mode='incumbent',
            reason='other',
            outcome='degraded',
            log=logger,
        )
    except Exception:
        pass  # Optional telemetry cannot withdraw a transcript write/read.
    logger.warning('event=speaker_grouping_storage outcome=%s', outcome)


def protect_segments(segments: list[dict[str, Any]], uid: str) -> None:
    """Remove plaintext first; any optional encryption failure drops the evidence."""
    pending: list[tuple[dict[str, Any], dict[str, Any] | None, Any]] = []
    now = time.time()
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        values = {key: segment[key] for key in GROUPING_INTERNAL_FIELDS if key in segment and key != FIELD}
        existing = segment.get(FIELD)
        strip_grouping_internal_fields(segment)
        if values:
            if values.get('speaker_grouping_shadow'):
                values.setdefault('speaker_grouping_shadow_expires_at', now + PREDICTION_TTL_SECONDS)
            pending.append((segment, {'id': segment.get('id'), 'values': values}, None))
        elif existing is not None:
            pending.append((segment, None, existing))
    try:
        if len(pending) > MAX_SEGMENTS:
            raise ValueError('capacity')
        serialized = [
            (segment, json.dumps(record) if record else None, existing) for segment, record, existing in pending
        ]
        if sum(len((payload or '').encode()) for _, payload, _ in serialized) > MAX_BYTES:
            raise ValueError('capacity')
        for segment, payload, existing in serialized:
            if payload is None:
                if not isinstance(existing, str) or len(existing) > MAX_ENCODED_BYTES:
                    raise ValueError('capacity')
                plaintext = encryption.decrypt(existing, uid)
                if plaintext == existing or json.loads(plaintext).get('id') != segment.get('id'):
                    raise ValueError('authentication')
        encrypted = [
            (segment, encryption.encrypt(payload, uid) if payload else existing)
            for segment, payload, existing in serialized
        ]
        if (
            any(not isinstance(value, str) for _, value in encrypted)
            or sum(len(value) for _, value in encrypted) > MAX_ENCODED_BYTES
        ):
            raise ValueError('capacity')
        if any(value == payload for (_, payload, _), (_, value) in zip(serialized, encrypted) if payload):
            raise ValueError('encryption')
        for segment, value in encrypted:
            segment[FIELD] = value
    except Exception:
        _unavailable('evidence_dropped')


def reveal_segments(segments: list[dict[str, Any]], uid: str) -> None:
    now = time.time()
    total = 0
    decoded_bytes = 0
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            continue
        encrypted = segment.get(FIELD)
        # Never trust legacy plaintext extras, including during migrations.
        strip_grouping_internal_fields(segment)
        if encrypted is None:
            continue
        try:
            total += len(encrypted)
            if index >= MAX_SEGMENTS or total > MAX_ENCODED_BYTES or not isinstance(encrypted, str):
                raise ValueError('capacity')
            plaintext = encryption.decrypt(encrypted, uid)
            decoded_bytes += len(plaintext.encode())
            if plaintext == encrypted or decoded_bytes > MAX_BYTES:
                raise ValueError('authentication')
            record = json.loads(plaintext)
            if record['id'] != segment.get('id') or not isinstance(record['values'], dict):
                raise ValueError('binding')
            values = record['values']
            expires = values.get('speaker_grouping_shadow_expires_at', 0)
            if not isinstance(expires, (int, float)) or not now < expires <= now + PREDICTION_TTL_SECONDS:
                values.pop('speaker_grouping_shadow', None)
                values.pop('speaker_grouping_shadow_expires_at', None)
            segment.update(
                {key: value for key, value in values.items() if key in GROUPING_INTERNAL_FIELDS and key != FIELD}
            )
        except Exception:
            _unavailable('evidence_unavailable')
