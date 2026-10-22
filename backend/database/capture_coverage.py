"""Bounded committed-frame ledger. One document/track serializes racing writers.

No clients are created at import time. Bounds reject new evidence rather than
coalescing a gap or evicting evidence and pretending it was committed.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from google.cloud import firestore
from database._client import run_transactional

from models.capture_coverage import CaptureKey, CoverageRecord, FrameRange
from database.read_boundary import parse_payload_strict
from database.capture_groups import transcript_fingerprint
from utils.capture_evidence import Span, coverage_union

MAX_RECORDS = 256
MAX_INTERVALS = 2048
MAX_DOCUMENT_BYTES = 600_000


def _records(document: dict) -> list[CoverageRecord]:
    return [
        parse_payload_strict(CoverageRecord, row, document_path='<capture_coverage>')
        for row in document.get('records', [])
    ]


def key_payload(key: CaptureKey) -> dict:
    value = key.model_dump()
    if any(v is not None and (not isinstance(v, str) or not v or len(v) > 256) for v in value.values()):
        raise ValueError('invalid bounded capture key')
    return value


def reference(client: Any, uid: str, key: CaptureKey) -> Any:
    payload = json.dumps(key_payload(key), sort_keys=True, separators=(',', ':'))
    identity = hashlib.sha256(payload.encode()).hexdigest()
    return client.collection('users').document(uid).collection('capture_coverage').document(identity)


def merge_record(document: dict, key: CaptureKey, rec: CoverageRecord) -> dict:
    """Pure transaction body, also used by strict transaction tests."""
    payload = key_payload(key)
    if document and document.get('key') != payload:
        raise ValueError('capture coverage key mismatch')
    if not rec.conversation_id or len(rec.conversation_id) > 256 or not rec.ranges:
        raise ValueError('invalid coverage record')
    records = _records(document)
    previous = next(
        (row for row in records if (row.conversation_id, row.origin) == (rec.conversation_id, rec.origin)), None
    )
    spans = coverage_union(Span(r.start, r.end) for r in [*(previous.ranges if previous else []), *rec.ranges])
    merged = rec.model_copy(update={'ranges': [FrameRange(start=s.start, end=s.end) for s in spans]})
    rows = sorted(
        [row.model_dump() for row in records if row is not previous] + [merged.model_dump()],
        key=lambda row: (row['conversation_id'], row['origin']),
    )
    result = {**document, 'version': 1, 'key': payload, 'records': rows}
    if len(rows) > MAX_RECORDS or sum(len(row['ranges']) for row in rows) > MAX_INTERVALS:
        raise ValueError('capture coverage capacity exceeded')
    if len(json.dumps(result, default=str, separators=(',', ':')).encode()) > MAX_DOCUMENT_BYTES:
        raise ValueError('capture coverage byte capacity exceeded')
    return result


def _client() -> Any:
    from database._client import get_firestore_client

    return get_firestore_client()


def read(uid: str, key: CaptureKey) -> list[CoverageRecord]:
    row = reference(_client(), uid, key).get().to_dict() or {}
    if row and row.get('key') != key_payload(key):
        raise ValueError('capture coverage key mismatch')
    return _records(row)


def record(uid: str, key: CaptureKey, rec: CoverageRecord) -> None:
    client = _client()
    ref = reference(client, uid, key)

    @firestore.transactional
    def write(transaction):
        old = ref.get(transaction=transaction).to_dict() or {}
        new = merge_record(old, key, rec)
        if new != old:
            transaction.set(ref, new)

    run_transactional(client, write, transient=True)


MAX_SHARED_RECORDS = 16


def _shared_current(rows: dict, evidence: dict) -> bool:
    """A separated, edited, deleted or re-elected group cannot release custody."""
    primary, secondary = (rows.get(evidence[k]) or {} for k in ('primary_id', 'secondary_id'))
    if not primary or not secondary:
        return False
    for row in (primary, secondary):
        group = row.get('capture_group') or {}
        if (
            row.get('status') != 'completed'
            or any(row.get(k) for k in ('deleted', 'discarded', 'capture_group_closed', 'has_transcript_corrections'))
            or row.get('transcript_correction_overlay') is not None
            or group.get('id') != evidence['group_id']
            or group.get('primary_id') != evidence['primary_id']
            or not {evidence['primary_id'], evidence['secondary_id']}.issubset(
                {m.get('id') for m in group.get('members') or []}
            )
        ):
            return False
    if bool(primary.get('is_locked')) != bool(secondary.get('is_locked')):
        return False
    return all(
        transcript_fingerprint(rows.get(cid)) == fingerprint for cid, fingerprint in evidence['fingerprints'].items()
    )


def record_shared(
    uid: str,
    key: CaptureKey,
    *,
    primary_id: str,
    secondary_id: str,
    group_id: str,
    fingerprints: dict[str, str],
    window: dict,
    firestore_client=None,
) -> bool:
    """Alias only already-committed secondary frames to confirmed primary speech.

    The owner window, exact secondary capture key and both immutable transcript
    fingerprints form the proof. No wall-to-frame extrapolation or reservation.
    Read every fence and ledger document before writing, including on retries.
    """
    client = firestore_client or _client()
    ref = reference(client, uid, key)
    evidence = {
        'primary_id': primary_id,
        'secondary_id': secondary_id,
        'group_id': group_id,
        'fingerprints': fingerprints,
        'window': window,
    }
    if primary_id == secondary_id or set(fingerprints) != {primary_id, secondary_id}:
        raise ValueError('invalid cross-device coverage proof')
    conversations = client.collection('users').document(uid).collection('conversations')

    @firestore.transactional
    def write(transaction):
        rows = {cid: conversations.document(cid).get(transaction=transaction).to_dict() for cid in fingerprints}
        document = ref.get(transaction=transaction).to_dict() or {}
        if not _shared_current(rows, evidence):
            return False
        if document.get('key') != key_payload(key):
            return False
        # The ledger, not the capture envelope or wall clock, is the authority
        # for which complete source frames actually became durable speech.
        spans = coverage_union(
            Span(r.start, r.end)
            for rec in _records(document)
            if rec.conversation_id == secondary_id
            for r in rec.ranges
        )
        if not spans:
            return False
        entry = {**evidence, 'ranges': [{'start': s.start, 'end': s.end} for s in spans]}
        shared = [r for r in document.get('shared_records', []) if r['secondary_id'] != secondary_id]
        shared.append(entry)
        if len(shared) > MAX_SHARED_RECORDS:
            raise ValueError('cross-device coverage capacity exceeded')
        result = {**document, 'shared_records': sorted(shared, key=lambda r: r['secondary_id'])}
        if len(json.dumps(result, default=str, separators=(',', ':')).encode()) > MAX_DOCUMENT_BYTES:
            raise ValueError('capture coverage byte capacity exceeded')
        if result != document:
            transaction.set(ref, result)
        return True

    return run_transactional(client, write, transient=True)


def read_shared(uid: str, key: CaptureKey, *, firestore_client=None) -> list[CoverageRecord]:
    """Bounded point reads revalidate a shared window before returning receipts."""
    client = firestore_client or _client()
    ref = reference(client, uid, key)
    conversations = client.collection('users').document(uid).collection('conversations')

    @firestore.transactional
    def read_current(transaction):
        document = ref.get(transaction=transaction).to_dict() or {}
        if document and document.get('key') != key_payload(key):
            raise ValueError('capture coverage key mismatch')
        shared = document.get('shared_records', [])
        if len(shared) > MAX_SHARED_RECORDS:
            raise ValueError('cross-device coverage capacity exceeded')
        ids = {cid for entry in shared for cid in entry['fingerprints']}
        rows = {cid: conversations.document(cid).get(transaction=transaction).to_dict() for cid in ids}
        return [
            CoverageRecord(conversation_id=entry['primary_id'], origin='live', ranges=entry['ranges'])
            for entry in shared
            if _shared_current(rows, entry)
        ]

    return run_transactional(client, read_current, transient=True)
