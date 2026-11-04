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


def _unavailable(outcome: str, *, segments: int = 1, fault: str | None = None) -> None:
    """One degradation event for the whole optional-evidence operation.

    A single call may inspect hundreds of sidecars, and a fault that hits a
    conversation-wide shape (a key rotation, one oversized or corrupted blob,
    a stale envelope) repeats the identical failure on every segment. Emitting
    one ``omi_fallback_total`` and one warning per segment turned each such
    read into a warning storm (prod backend-listen 2026-10-28:
    ``event=speaker_grouping_storage outcome=evidence_unavailable`` and its
    paired ``omi_fallback_event`` rose through 1.6k+/hour with the ramp
    concentrated on the highest-segment reads). The event is the unit of
    degraded outcome — one per call — with the segment count and the fault
    shape carried as bounded detail. Both callers aggregate:
    ``protect_segments`` reports the whole-drop, or the per-segment
    rejections when verification drops individual sidecars; and
    ``reveal_segments`` reports the per-read failures.
    """
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
    if segments > 1 or fault:
        detail = ' segments=%d' % segments if segments > 1 else ''
        if fault:
            detail += ' fault=%s' % fault
        logger.warning('event=speaker_grouping_storage outcome=%s%s', outcome, detail)
    else:
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
    """Remove plaintext first; any optional encryption failure drops the evidence.

    One sidecar this codec cannot re-verify (foreign, corrupted, oversized, or
    no longer authenticating) is dropped alone: it is evidence the read path
    already refuses to trust, so keeping its neighbors' healthy sidecars loses
    nothing and stops one poisoned segment from re-dropping the whole
    conversation's evidence on every rewrite. Envelope-level and key-level
    faults keep the conservative whole-drop: capacity is a property of the
    conversation's envelope, and an encryption fault fails every re-seal
    after it just failed verification for the same reason.
    """
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
    rejected = 0
    rejected_faults: dict[str, int] = {}
    try:
        if len(pending) > MAX_SEGMENTS:
            raise ValueError('capacity')
        serialized = [
            (segment, json.dumps(record) if record else None, existing) for segment, record, existing in pending
        ]
        if sum(len((payload or '').encode()) for _, payload, _ in serialized) > MAX_BYTES:
            raise ValueError('capacity')
        verified: list[tuple[dict[str, Any], str | None, Any]] = []
        for segment, payload, existing in serialized:
            if payload is None:
                try:
                    if not isinstance(existing, str) or len(existing) > MAX_ENCODED_BYTES:
                        raise ValueError('capacity')
                    plaintext = encryption.decrypt(existing, uid)
                    if plaintext == existing or json.loads(plaintext).get('id') != segment.get('id'):
                        raise ValueError('authentication')
                except Exception as error:
                    # Unverifiable evidence is untrustable by construction; it
                    # is dropped alone instead of failing its neighbors.
                    fault = _reveal_fault(error)
                    rejected_faults[fault] = rejected_faults.get(fault, 0) + 1
                    rejected += 1
                    continue
            verified.append((segment, payload, existing))
        encrypted = [
            (segment, encryption.encrypt(payload, uid) if payload else existing)
            for segment, payload, existing in verified
        ]
        if (
            any(not isinstance(value, str) for _, value in encrypted)
            or sum(len(value) for _, value in encrypted) > MAX_ENCODED_BYTES
        ):
            raise ValueError('capacity')
        if any(value == payload for (_, payload, _), (_, value) in zip(verified, encrypted) if payload):
            raise ValueError('encryption')
        for segment, value in encrypted:
            segment[FIELD] = value
    except Exception:
        _unavailable('evidence_dropped')
        _protect_timing_markers(pending, uid)
        return
    _protect_timing_markers(pending, uid)
    if rejected:
        _unavailable('evidence_dropped', segments=rejected, fault=_primary_fault(rejected_faults))


def _reveal_fault(error: BaseException) -> str:
    """Classify one sidecar failure into the bounded fault vocabulary.

    The vocabulary is what the codec can verify, not root-cause truth: a
    blob this codec wrote fails here as ``oversized`` (an envelope above the
    codec's own write bound) or ``unwritable`` (not a str, or the decrypted
    record does not re-bind to its segment id — corruption, a foreign field,
    or key material that no longer authenticates; the codec cannot tell
    those apart because ``encryption.decrypt`` returns the envelope
    unchanged on AES failure). A non-ValueError escaping is a key-derivation
    or unexpected codec fault and is reported as ``key_unavailable``.
    """

    if isinstance(error, ValueError):
        message = str(error)
        if message in {'capacity', 'authentication', 'binding'}:
            if message == 'capacity':
                return 'oversized'
            return 'unwritable'
        return 'unknown'
    return 'key_unavailable'


def reveal_segments(segments: list[Any], uid: str) -> None:
    """Reveal stored grouping evidence, reporting degradation once per call.

    Semantics are unchanged from the per-segment version: every sidecar that
    survives its own checks is revealed even when its neighbors fail; a
    failed sidecar contributes nothing; plaintext extras are never trusted;
    bounds are enforced per segment (index, cumulative ciphertext, decoded
    plaintext). Only the telemetry shape changed: one degradation event per
    call, with the failing sidecar count and the most instructive fault
    shape observed (``_primary_fault``). The count is the blast radius the
    old per-segment storm obscured: a whole-conversation failure mode
    (unreadable envelopes after a key change, an oversized envelope) and a
    single corrupted sidecar both used to emit one identical warning per
    segment.
    """

    now = time.time()
    total = 0
    decoded_bytes = 0
    failures: list[tuple[str, int]] = []
    value_index = 0
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
            # Writer-fault gates run BEFORE decryption, keyed on admitted
            # value rows: an envelope beyond the encoded bound and a
            # segment beyond the envelope's slot cap classify as
            # 'capacity'/'oversized' even when their content is garbage
            # (event-storm contract), while timing markers — detected
            # only after decrypt — neither consume nor trip these caps
            # (review-regression contract: a timing-only conversation
            # can exceed the value-segment caps legitimately).
            if not isinstance(encrypted, str) or len(encrypted) > MAX_ENCODED_BYTES:
                raise ValueError('capacity')
            plaintext = encryption.decrypt(encrypted, uid)
            if plaintext == encrypted:
                # Non-codec content (garbage 'decrypts' to itself). Beyond
                # the envelope's slot cap the operative fault is the cap —
                # the admit path enforces the same cap, so this row was
                # never a legitimate value segment (the candidate's index
                # contract). Below the cap it is an authentication fault.
                if index >= MAX_SEGMENTS:
                    raise ValueError('capacity') from None
                raise ValueError('authentication')
            record = json.loads(plaintext)
            if record['id'] != segment.get('id'):
                raise ValueError('binding')
            if 'timing_unit' in record:
                # Main's timing exemption: decodable timing markers are
                # bounded by their own MAX_TIMING_* budgets and are the one
                # legitimate over-cap population; they neither consume nor
                # trip the value-segment caps.
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
            # A decodable VALUE row beyond the envelope's slot cap is the
            # cap fault, not a fault of its content (the candidate's index
            # contract; binding above already identified misattributed
            # sidecars by their id).
            if index >= MAX_SEGMENTS:
                raise ValueError('capacity')
            # Value rows: the candidate's exact accounting order.
            total += len(encrypted)
            decoded_bytes += len(plaintext.encode())
            if total > MAX_ENCODED_BYTES:
                raise ValueError('capacity')
            if decoded_bytes > MAX_BYTES:
                raise ValueError('authentication')
            if not isinstance(record.get('values'), dict):
                raise ValueError('binding')
            value_index += 1
            values = record['values']
            expires = values.get('speaker_grouping_shadow_expires_at', 0)
            if not isinstance(expires, (int, float)) or not now < expires <= now + PREDICTION_TTL_SECONDS:
                values.pop('speaker_grouping_shadow', None)
                values.pop('speaker_grouping_shadow_expires_at', None)
            segment.update(
                {key: value for key, value in values.items() if key in GROUPING_INTERNAL_FIELDS and key != FIELD}
            )
        except Exception as error:
            failures.append((_reveal_fault(error), index))
    if failures:
        counts: dict[str, int] = {}
        for fault, _ in failures:
            counts[fault] = counts.get(fault, 0) + 1
        primary_fault = _primary_fault(counts)
        _unavailable('evidence_unavailable', segments=len(failures), fault=primary_fault)
    members = {
        sid: {**label, 'scope': marker['scope'], 'timing_store': marker['timing_store']}
        for marker in timing_units.values()
        for sid, label in marker['segments'].items()
    }
    for segment in segments:
        if isinstance(segment, dict) and isinstance(segment.get('id'), str) and segment['id'] in members:
            segment['provider_speaker'] = dict(members[segment['id']])



def _primary_fault(counts: dict[str, int]) -> str:
    """The fault shape that headlines the aggregated event.

    Order is instructiveness for the operator reading one line: an
    ``oversized`` envelope is a conversation-envelope fault the writer
    should never have produced; ``key_unavailable`` is an unexpected codec
    fault worth its own alert triage; ``unwritable`` covers the
    corruption/foreign-field/failed-authentication family the codec cannot
    sub-classify; ``unknown`` is anything else. Ties between the
    unattributable shapes go to ``unwritable`` so the alert lands on the
    named family instead of the catch-all.
    """

    if counts.get('oversized'):
        return 'oversized'
    if counts.get('key_unavailable'):
        return 'key_unavailable'
    unwritable = counts.get('unwritable', 0)
    unknown = counts.get('unknown', 0)
    if unwritable or unknown:
        return 'unwritable' if unwritable >= unknown else 'unknown'
    return 'unknown'
