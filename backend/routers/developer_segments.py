"""Bounded continuation intake for the developer router's from-segments endpoint.

Chunks are encrypted and create-only by (deterministic conversation, index).
A retry can finish assembly after a crash; the existing conversation admission
claim owns processing, so concurrent final requests cannot create two rows.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Callable, cast

from fastapi import HTTPException
from google.cloud import firestore
from prometheus_client import Counter
from pydantic import BaseModel, Field, model_validator

from config.refactor_modes import serving_for, shadow_or_serve
from database.account_deletion_marker import account_deletion_firestore_client as get_firestore_client
from database.from_segments_chunks import purge_chunks
from models.capture_coverage import AdmitResult, CaptureKey, FrameRange
from utils import encryption

if TYPE_CHECKING:
    from routers.developer_segments_models import CreateConversationFromTranscriptRequest

logger = logging.getLogger(__name__)
CONTINUATION_FLAG_KEY = 'CLIENTS_FROM_SEGMENTS_CHUNKS_MODE'
CONTINUATION_PERCENT_ENV = 'CLIENTS_FROM_SEGMENTS_CHUNKS_MODE_SERVE_PERCENT'
CONTINUATION_DIGESTS_ENV = 'CLIENTS_FROM_SEGMENTS_CHUNKS_MODE_SERVE_UID_SHA256S'
STAGING_TTL = timedelta(days=7)
SHADOW = Counter('omi_clients_refactor_shadow_total', 'L5 bounded shadow comparisons', ['check', 'outcome'])


def observe(check: str, outcome: str) -> None:
    if outcome == 'agree':
        counter = SHADOW.labels(check=check, outcome='agree')
    elif outcome == 'disagree':
        counter = SHADOW.labels(check=check, outcome='disagree')
    else:
        outcome = 'error'
        counter = SHADOW.labels(check=check, outcome='error')
    if outcome != 'agree':
        logger.info('event=refactor_shadow lane=L5 check=%s outcome=%s', check, outcome)
    counter.inc()


class ContinuationFields(BaseModel):
    chunk_index: int | None = Field(default=None, ge=0, le=127)
    chunk_count: int | None = Field(default=None, ge=1, le=128)
    capture_key: CaptureKey | None = None
    capture_segment_ranges: list[FrameRange] | None = Field(default=None, max_length=500)

    @model_validator(mode='after')
    def validate_continuation(self):
        if (self.chunk_index is None) != (self.chunk_count is None):
            raise ValueError('chunk_index and chunk_count must be supplied together')
        if self.chunk_index is not None:
            if (
                not getattr(self, 'client_session_id', None)
                or self.chunk_count is None
                or self.chunk_index >= self.chunk_count
            ):
                raise ValueError('a chunk requires a session and index below chunk_count')
            if getattr(self, 'started_at', None) is None or getattr(self, 'finished_at', None) is None:
                raise ValueError('chunks require fixed recording timestamps')
        if self.capture_segment_ranges is not None:
            if self.capture_key is None or len(self.capture_segment_ranges) != len(
                getattr(self, 'transcript_segments', [])
            ):
                raise ValueError('capture ranges require a key and one range per segment')
            if any(r.end <= r.start for r in self.capture_segment_ranges):
                raise ValueError('capture ranges must be nonempty')
        return self


def stage_chunk(
    uid: str, conversation_id: str, request: CreateConversationFromTranscriptRequest, *, firestore_client: Any = None
) -> dict[str, Any] | None:
    """Return the assembled payload only when all indices are durable.

    No query/index is needed. Point reads are bounded by chunk_count. Direct
    children of users/{owner} remain visible to recursive account erasure even
    before a conversation exists. Transactions fence deletion and replay.
    """
    if request.chunk_index is None or request.chunk_count is None or not request.client_session_id:
        raise HTTPException(status_code=422, detail='Incomplete continuation metadata')
    # Reject malformed frozen input before persisting any constituent chunk.
    for segment in request.transcript_segments:
        if (
            not math.isfinite(segment.start)
            or not math.isfinite(segment.end)
            or segment.start < 0
            or segment.end <= segment.start
            or not segment.text.strip()
        ):
            raise HTTPException(status_code=422, detail='Invalid transcript segment')
    client: Any = firestore_client if firestore_client is not None else get_firestore_client()
    user = client.collection('users').document(uid)
    chunks = user.collection('from_segments_chunks')
    payload = request.model_dump(mode='json', by_alias=False)
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    if len(encoded.encode()) > 700_000:
        raise HTTPException(status_code=413, detail='Chunk exceeds staging byte limit')
    digest_payload = {k: v for k, v in payload.items() if k != 'client_processing'}
    digest = hashlib.sha256(json.dumps(digest_payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    ref = chunks.document(f'{conversation_id}-{request.chunk_index:03d}')
    ciphertext = encryption.encrypt(encoded, uid)

    @firestore.transactional
    def commit(transaction: Any) -> None:
        deleting = client.collection('account_deletions').document(uid).get(transaction=transaction)
        deleted = user.collection('deleted_conversations').document(conversation_id).get(transaction=transaction)
        session_deleted = (
            user.collection('deleted_conversations').document(request.client_session_id).get(transaction=transaction)
        )
        prior = ref.get(transaction=transaction)
        if deleting.exists or deleted.exists or session_deleted.exists:
            raise HTTPException(status_code=409, detail='Capture owner or conversation is deleted')
        previous = prior.to_dict() or {}
        expiry = previous.get('expires_at')
        expired = isinstance(expiry, datetime) and expiry <= datetime.now(timezone.utc)
        if prior.exists and not expired:
            if previous.get('digest') != digest:
                raise HTTPException(status_code=409, detail='Chunk index already contains different content')
            return
        payload_row = {'digest': digest, 'payload': ciphertext, 'expires_at': datetime.now(timezone.utc) + STAGING_TTL}
        if expired:
            transaction.set(ref, payload_row)
        else:
            transaction.create(ref, payload_row)

    commit(client.transaction())
    parts: list[dict[str, Any]] = []
    for index in range(request.chunk_count):
        snapshot = chunks.document(f'{conversation_id}-{index:03d}').get()
        stored = snapshot.to_dict() or {}
        if (
            not snapshot.exists
            or not isinstance(stored.get('expires_at'), datetime)
            or stored['expires_at'] <= datetime.now(timezone.utc)
        ):
            return None
        parts.append(json.loads(encryption.decrypt(stored['payload'], uid)))

    def common(part: dict[str, Any]) -> dict[str, Any]:
        return {
            k: v
            for k, v in part.items()
            if k not in {'chunk_index', 'transcript_segments', 'capture_segment_ranges', 'client_processing'}
        }

    if any(common(part) != common(parts[0]) for part in parts):
        raise HTTPException(status_code=409, detail='Continuation metadata changed between chunks')
    assembled = dict(parts[0])
    assembled['transcript_segments'] = [segment for part in parts for segment in part['transcript_segments']]
    if assembled.get('capture_segment_ranges') is not None:
        assembled['capture_segment_ranges'] = [span for part in parts for span in part['capture_segment_ranges']]
    # Only the final chunk may carry the projection of the entire transcript.
    assembled['client_processing'] = parts[-1].get('client_processing')
    return assembled


def continuation(
    uid: str,
    request: CreateConversationFromTranscriptRequest,
    conversation_id: str,
    ingest: Callable[[CreateConversationFromTranscriptRequest], Any],
    response: Callable[..., Any],
) -> Any:
    if not serving_for(CONTINUATION_FLAG_KEY, uid):
        if shadow_or_serve(CONTINUATION_FLAG_KEY):
            observe('chunk_admission', 'disagree')
        # Explicitly fail so a client never treats a legacy "first chunk wins" reply as success.
        raise HTTPException(status_code=409, detail='Continuation uploads are not enabled')
    payload = stage_chunk(uid, conversation_id, request)
    if payload is None:
        return response(id=conversation_id, status='processing', discarded=False)
    # Every constituent request passed public validation. Aggregates deliberately
    # exceed the per-request maxItems; model_copy avoids reapplying that wire cap.
    updates: dict[str, Any] = {
        'transcript_segments': [
            type(request.transcript_segments[0]).model_validate(s) for s in payload['transcript_segments']
        ],
        'capture_segment_ranges': (
            [FrameRange.model_validate(r) for r in payload['capture_segment_ranges']]
            if payload.get('capture_segment_ranges') is not None
            else None
        ),
        'client_processing': payload.get('client_processing'),
    }
    result = ingest(request.model_copy(update=updates))
    # Successful processing has durably moved the transcript into its conversation.
    # Failed/in-progress assembly keeps the encrypted inputs for replay.
    if getattr(result, 'status', None) in {'completed', 'deleted'}:
        try:
            purge_chunks(uid, conversation_id, request.chunk_count or 128)
        except Exception:
            observe('chunk_cleanup', 'error')
    return result


def admit_segments(
    uid: str, request: CreateConversationFromTranscriptRequest, response: Callable[..., Any]
) -> tuple[CreateConversationFromTranscriptRequest, Any]:
    """Only exact whole-segment frame proofs can suppress transcript text.

    Partial overlap cannot be split safely without word/frame alignment. Fail
    closed into retained custody in serving mode; shadow always keeps old input.
    """
    flag = 'CAPTURE_COVERAGE_MODE'
    if not shadow_or_serve(flag):
        return request, None
    if request.capture_key is None or request.capture_segment_ranges is None:
        observe('from_segments_coverage_unknown', 'agree')
        return request, None
    try:
        from importlib import import_module

        admit = cast(Callable[..., Any], import_module('utils.capture.coverage').admit)
        result = cast(
            AdmitResult,
            admit(
                uid,
                request.capture_key,
                request.capture_segment_ranges,
                origin='desktop' if request.source == 'desktop' else 'batch',
            ),
        )
    except ImportError:
        observe('from_segments_coverage', 'error')
        if serving_for(flag, uid):
            raise HTTPException(status_code=503, detail='Coverage admission unavailable')
        return request, None
    except Exception:
        observe('from_segments_coverage', 'error')
        if serving_for(flag, uid):
            raise
        return request, None
    observe('from_segments_coverage', 'disagree' if result.covered else 'agree')
    if not serving_for(flag, uid) or not result.covered:
        return request, None
    kept = []
    spans: list[FrameRange] = []
    for segment, span in zip(request.transcript_segments, request.capture_segment_ranges):
        intersections = [r for r in result.covered if r.start < span.end and r.end > span.start]
        if not intersections:
            kept.append(segment)
            spans.append(span)
        elif not any(r.start <= span.start and r.end >= span.end for r in intersections):
            raise HTTPException(status_code=409, detail='Partial frame overlap requires aligned recovery')
    if not kept:
        if not result.covering_conversation_id:
            raise HTTPException(status_code=409, detail='Coverage has no conversation receipt')
        return request, response(id=result.covering_conversation_id, status='completed', discarded=False)
    # A projection digest for the original transcript cannot bind after filtering.
    return (
        request.model_copy(
            update={'transcript_segments': kept, 'capture_segment_ranges': spans, 'client_processing': None}
        ),
        None,
    )
