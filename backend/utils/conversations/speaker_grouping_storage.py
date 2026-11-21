"""Always-encrypted grouping sidecars inside the existing transcript write.

Provenance lasts with its transcript for safe reprocessing. Experimental identity
predictions expire after 30 days, independently of the account protection level.
No audio, vectors, extra storage calls or encryption-key network calls.
Compact batch timing provenance is deduplicated by unit and bounded per conversation.
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
MAX_TIMING_BYTES = 1024
MAX_TIMING_UNITS = 1024
MAX_TIMING_TOTAL_BYTES = 256 * 1024
MAX_TIMING_TOTAL_ENCODED_BYTES = 384 * 1024
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


def _timing_record(record: dict[str, Any]) -> dict[str, Any] | None:
    """Validate the admission stamp and its provider partition before compaction."""
    values = record.get('values')
    provider = values.get('provider_speaker') if isinstance(values, dict) else None
    if not isinstance(provider, dict):
        return None
    scope = provider.get('scope')
    if (
        provider.get('timing_store') not in ('batch', 'sync')
        or not isinstance(scope, str)
        or not scope.startswith('final:batch:')
        or scope == 'final:batch:'
        or scope.startswith('final:batch:conversation:')
        or type(provider.get('id')) is not int
        or not isinstance(provider.get('provider'), (str, type(None)))
    ):
        return None
    compact = {key: provider.get(key) for key in ('id', 'scope', 'provider', 'timing_store')}
    result = {'id': record.get('id'), 'values': {'provider_speaker': compact}}
    return result if len(json.dumps(result).encode()) <= MAX_TIMING_BYTES else None


def _protect_timing_markers(pending, uid: str) -> None:
    # Re-scoping hides the original unit/label, so bind each unit's stamp to its
    # segment ids inside the encrypted sidecar, not to mutable public scopes.
    units: dict[str, Any] = {}
    budget = 0
    for segment, record, existing in pending:
        try:
            if record is None:
                if not isinstance(existing, str) or len(existing) > MAX_ENCODED_BYTES:
                    continue
                plaintext = encryption.decrypt(existing, uid)
                if plaintext == existing:
                    continue
                record = json.loads(plaintext)
                if record.get('id') != segment.get('id'):
                    continue
                if 'timing_unit' in record:
                    # Opaque rewrites retain the same authenticated membership.
                    marker = _timing_unit(record)
                    if marker is not None:
                        scope = marker['scope']
                        if scope not in units and len(units) < MAX_TIMING_UNITS:
                            size = len(json.dumps(record).encode())
                            if budget + size <= MAX_TIMING_TOTAL_BYTES:
                                units[scope] = (segment, record)
                                budget += size
                    continue
            if record.get('id') != segment.get('id'):
                continue
            compact = _timing_record(record)
            if compact is None or not isinstance(segment.get('id'), str):
                continue
            provider = compact['values']['provider_speaker']
            scope = provider['scope']
            if scope not in units:
                if len(units) >= MAX_TIMING_UNITS:
                    continue
                units[scope] = (
                    segment,
                    {
                        'id': segment['id'],
                        'timing_unit': {
                            'scope': scope,
                            'timing_store': provider['timing_store'],
                            'segments': {},
                        },
                    },
                )
            _, envelope = units[scope]
            marker = envelope['timing_unit']
            if marker is None:
                continue
            size = len(json.dumps(compact).encode())
            if marker['timing_store'] != provider['timing_store'] or budget + size > MAX_TIMING_TOTAL_BYTES:
                envelope['timing_unit'] = None
                continue  # Drop the unit, including earlier members, on conflicting custody or overflow.
            marker['segments'][segment['id']] = {'id': provider['id'], 'provider': provider['provider']}
            budget += size
        except Exception:
            continue  # Transcript survives; unauthenticated provenance cannot choose a store.
    total = 0
    decoded_bytes = 0
    for segment, record in units.values():
        try:
            if record['timing_unit'] is None:
                continue
            payload = json.dumps(record)
            size = len(payload.encode())
            if size > MAX_BYTES or decoded_bytes + size > MAX_TIMING_TOTAL_BYTES:
                continue
            encrypted: Any = encryption.encrypt(payload, uid)
            if (
                isinstance(encrypted, str)
                and encrypted != payload
                and len(encrypted) <= MAX_ENCODED_BYTES
                and total + len(encrypted) <= MAX_TIMING_TOTAL_ENCODED_BYTES
            ):
                segment[FIELD] = encrypted
                total += len(encrypted)
                decoded_bytes += size
        except Exception:
            continue


def _timing_unit(record: dict[str, Any]) -> dict[str, Any] | None:
    marker = record.get('timing_unit')
    if not isinstance(marker, dict) or not isinstance(marker.get('segments'), dict) or not marker['segments']:
        return None
    scope = marker.get('scope')
    stamp = marker.get('timing_store')
    for sid, label in marker['segments'].items():
        if not isinstance(sid, str) or not isinstance(label, dict) or set(label) != {'id', 'provider'}:
            return None
        provider = {**label, 'scope': scope, 'timing_store': stamp}
        if _timing_record({'id': sid, 'values': {'provider_speaker': provider}}) is None:
            return None
    if record.get('id') not in marker['segments']:
        return None
    return marker


def protect_segments(segments: list[Any], uid: str) -> None:
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
        _protect_timing_markers(pending, uid)


def reveal_segments(segments: list[Any], uid: str) -> None:
    now = time.time()
    total = 0
    decoded_bytes = 0
    timing_units: dict[str, Any] = {}
    timing_bytes = 0
    timing_encoded_bytes = 0
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            continue
        encrypted = segment.get(FIELD)
        # Never trust legacy plaintext extras, including during migrations.
        strip_grouping_internal_fields(segment)
        if encrypted is None:
            continue
        try:
            if not isinstance(encrypted, str) or len(encrypted) > MAX_ENCODED_BYTES:
                raise ValueError('capacity')
            plaintext = encryption.decrypt(encrypted, uid)
            if plaintext == encrypted:
                raise ValueError('authentication')
            record = json.loads(plaintext)
            if record['id'] != segment.get('id'):
                raise ValueError('binding')
            if 'timing_unit' in record:
                marker = _timing_unit(record)
                size = len(plaintext.encode())
                if (
                    marker is None
                    or marker['scope'] in timing_units
                    or len(timing_units) >= MAX_TIMING_UNITS
                    or timing_bytes + size > MAX_TIMING_TOTAL_BYTES
                    or timing_encoded_bytes + len(encrypted) > MAX_TIMING_TOTAL_ENCODED_BYTES
                ):
                    raise ValueError('capacity')
                timing_units[marker['scope']] = marker
                timing_bytes += size
                timing_encoded_bytes += len(encrypted)
                continue
            if not isinstance(record.get('values'), dict):
                raise ValueError('binding')
            total += len(encrypted)
            decoded_bytes += len(plaintext.encode())
            if index >= MAX_SEGMENTS or total > MAX_ENCODED_BYTES or decoded_bytes > MAX_BYTES:
                raise ValueError('capacity')
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
    members = {
        sid: {**label, 'scope': marker['scope'], 'timing_store': marker['timing_store']}
        for marker in timing_units.values()
        for sid, label in marker['segments'].items()
    }
    for segment in segments:
        if isinstance(segment, dict) and isinstance(segment.get('id'), str) and segment['id'] in members:
            segment['provider_speaker'] = dict(members[segment['id']])
