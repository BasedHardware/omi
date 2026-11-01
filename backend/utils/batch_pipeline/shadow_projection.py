"""Ephemeral production projection/assignment planning on the CPU role.

This exercises the real result partitioner, incoming builder and assignment
transaction body. It does not simulate owner-chain scheduling, commit, claims,
followups or publication; those remain separate replay/runtime evidence.
"""

from copy import deepcopy
import threading
import time
import json
import logging
from typing import Any, Callable

from utils.batch_pipeline.shadow_transaction import ShadowBoundaryError, ShadowTransaction
from config.policy import ProjectionPolicy
from database.batch_pipeline_shadow import ShadowStore
from database import conversations
from utils.batch_pipeline.contracts import WorkItem, ProjectionBinding, projection_speech_spans
from utils.batch_pipeline.projection import build_incoming
from utils.batch_pipeline.projection_parts import split_result
from utils.sync.assignment import assign_in_transaction
from utils.batch_pipeline.shadow_metrics import (
    PROJECTION,
    PROJECTION_CPU,
    PROJECTION_WALL,
    PROJECTION_READS,
    PROJECTION_BYTES,
)
from utils.batch_pipeline.errors import error_site_field

SLOTS = threading.BoundedSemaphore(3)
STATUSES = frozenset({'planned', 'empty', 'not_eligible', 'budget_skipped', 'busy', 'error'})
logger = logging.getLogger(__name__)


def plan(item, payload, context, reader, *, decode, builder=None, assign=None):

    if not item.shadow:
        raise ShadowBoundaryError('shadow_required')
    if not isinstance(payload, dict) or not isinstance(payload.get('words'), list) or len(payload['words']) > 50000:
        raise ShadowBoundaryError('bounded_result_required')
    transaction = ShadowTransaction(item.owner_id, reader)
    try:
        if not payload['words']:
            if payload.get('speech_seconds') != 0:
                raise ShadowBoundaryError('empty_with_speech')
            return dict(status='empty', reads=0, planned_writes=0, parts=0)
        target = item.conversation_id
        current = transaction.user().collection('conversations').document(target).get().to_dict() if target else None
        record_origin = bool(current and current.get('record_lane_owner') in {'batch_live_v1', 'batch_sync_v1'})
        binding = ProjectionBinding(
            item.owner_id,
            item.segment_id,
            item.segment_id,
            (item.segment_id,),
            source=context.get('source', 'omi'),
            client_device_id=context.get('client_device_id'),
            is_locked=context.get('is_locked', False),
            language=context.get('language'),
            data_protection_level=context.get('data_protection_level', 'enhanced'),
            privacy_generation=item.privacy_generation,
            target_conversation_id=target,
            record_origin=record_origin,
        )
        projection_speech_spans(payload, item.duration_seconds)
        parts = [(item, payload)] if record_origin else split_result(item, payload)
        builder = builder or build_incoming
        # The serving body is SDK-annotated; this intentional duck-typed seam
        # supplies narrower read/discard capabilities, never an SDK transaction.
        assign_body: Callable[..., Any] = assign or assign_in_transaction
        policy = ProjectionPolicy(authoritative_labels=True)
        # Each part gets its own discarded transaction, as the serving path does.
        # No SDK client/ref/commit escapes through the planner's capabilities.
        reads = writes = 0
        for part, part_payload in parts:
            if transaction.clock() >= transaction.deadline:
                raise ShadowBoundaryError('time_budget')
            incoming = builder(part, binding, part_payload, batch_segment_id=item.segment_id, policy=policy)
            if record_origin:
                incoming['_batch_replace_live'] = {
                    'start': item.capture_at,
                    'end': item.capture_at + item.duration_seconds,
                }
            assign_body(
                transaction,
                transaction.user(),
                incoming,
                target_id=target,
                decode=decode,
                encode=deepcopy,
                invalidate=lambda row: None,
            )
            reads, writes = transaction.reads, transaction.writes
            # No part is committed or retained. A later part must plan against
            # the same real snapshot, not claim effects from a discarded write.
            transaction.next_part()
        return dict(status='planned', reads=reads, planned_writes=writes, parts=len(parts))
    finally:
        PROJECTION_READS.inc(transaction.reads)
        transaction.close()


def run(store, segment_id, payload):

    if not SLOTS.acquire(blocking=False):
        PROJECTION.labels('busy').inc()
        return {'status': 'busy'}
    started = time.thread_time()
    wall_started = time.monotonic()
    outcome = 'error'
    try:
        size = len(json.dumps(payload, allow_nan=False).encode())
        if size > 8 * 1024 * 1024:
            return {'status': 'error'}
        PROJECTION_BYTES.inc(size)
        repository = ShadowStore(store)
        job = repository.projection_input(segment_id)
        if job is None:
            outcome = 'not_eligible'
            return {'status': 'not_eligible'}
        item = WorkItem(**job['item'])

        def read(path, fields, timeout):
            return store.client.document('/'.join(path)).get(field_paths=fields, timeout=timeout, retry=None).to_dict()

        def decode(raw):
            result = deepcopy(raw)
            result['transcript_segments'] = conversations.decode_transcript_segments_verified(
                item.owner_id, raw.get('transcript_segments', []), bool(raw.get('transcript_segments_compressed'))
            )
            if raw.get('manual_speaker_assignments') is not None:
                result['manual_speaker_assignments'] = conversations.decode_manual_speaker_assignments(
                    item.owner_id,
                    raw['manual_speaker_assignments'],
                    bool(raw.get('manual_speaker_assignments_compressed')),
                )
            return result

        receipt = plan(item, payload, job.get('projection_context') or {}, read, decode=decode)
        outcome = receipt['status']
        return receipt
    except Exception as error:
        logger.warning(
            'event=batch_shadow_projection outcome=error exception_type=%s%s',
            type(error).__name__,
            error_site_field(error),
        )
        return {'status': 'error'}
    finally:
        PROJECTION.labels(outcome).inc()
        PROJECTION_CPU.inc(max(0, time.thread_time() - started))
        PROJECTION_WALL.inc(max(0, time.monotonic() - wall_started))
        SLOTS.release()
