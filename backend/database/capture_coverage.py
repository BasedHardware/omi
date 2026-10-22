"""Bounded committed-frame ledger. One document/track serializes racing writers.

No clients are created at import time. Bounds reject new evidence rather than
coalescing a gap or evicting evidence and pretending it was committed.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from models.capture_coverage import CaptureKey, CoverageRecord, FrameRange
from utils.capture_evidence import Span, coverage_union

MAX_RECORDS = 256
MAX_INTERVALS = 2048
MAX_DOCUMENT_BYTES = 600_000


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
    records = [CoverageRecord.model_validate(row) for row in document.get('records', [])]
    previous = next(
        (row for row in records if (row.conversation_id, row.origin) == (rec.conversation_id, rec.origin)), None
    )
    spans = coverage_union(Span(r.start, r.end) for r in [*(previous.ranges if previous else []), *rec.ranges])
    merged = rec.model_copy(update={'ranges': [FrameRange(start=s.start, end=s.end) for s in spans]})
    rows = sorted(
        [row.model_dump() for row in records if row is not previous] + [merged.model_dump()],
        key=lambda row: (row['conversation_id'], row['origin']),
    )
    result = {'version': 1, 'key': payload, 'records': rows}
    if len(rows) > MAX_RECORDS or sum(len(row['ranges']) for row in rows) > MAX_INTERVALS:
        raise ValueError('capture coverage capacity exceeded')
    if len(json.dumps(result, separators=(',', ':')).encode()) > MAX_DOCUMENT_BYTES:
        raise ValueError('capture coverage byte capacity exceeded')
    return result


def _client() -> Any:
    from database._client import get_firestore_client

    return get_firestore_client()


def read(uid: str, key: CaptureKey) -> list[CoverageRecord]:
    row = reference(_client(), uid, key).get().to_dict() or {}
    if row and row.get('key') != key_payload(key):
        raise ValueError('capture coverage key mismatch')
    return [CoverageRecord.model_validate(rec) for rec in row.get('records', [])]


def record(uid: str, key: CaptureKey, rec: CoverageRecord) -> None:
    from google.cloud import firestore
    from database._client import run_transactional

    client = _client()
    ref = reference(client, uid, key)

    @firestore.transactional
    def write(transaction):
        old = ref.get(transaction=transaction).to_dict() or {}
        new = merge_record(old, key, rec)
        if new != old:
            transaction.set(ref, new)

    run_transactional(client, write, transient=True)
