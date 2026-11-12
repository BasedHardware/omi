"""Cold WAL admission fence for a registered live record, including rollback.

No frame/segment/pusher path calls this. A named WAL reuses the record result
only after its PCM is proven covered by that record's pinned raw references.
An unproven/late tail remains client-owned; it never starts a second GPU job.
"""

from dataclasses import fields
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
import io
import hashlib
import json
import logging
import wave

from fastapi.responses import JSONResponse

from config.batch_pipeline import (
    known_unsupported_batch_language,
    record_capture_eligible,
)
from config.policy import resolve_batch_policy
from config.batch_pipeline_coverage_wait import coverage_wait_memo_enabled
from config.batch_pipeline_language import admission_language_exclusion_enabled, batch_admission_language
from database.conversations import claim_record_lane_owner
from database.batch_pipeline_store import FirestoreStore
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.sync_ledger import LEDGER_RETENTION_DAYS
from database.record_custody_append import resolve_target
from database.sync_record_wait_cache import (
    RECORD_WAIT_CACHE_SECONDS,
    cached_record_wait,
    remember_record_wait,
    cached_coverage_wait,
    remember_coverage_wait,
)
from utils.batch_pipeline.contracts import WorkItem
from utils.batch_pipeline.intake import durable_status, start_response
from utils.batch_pipeline.artifact_policy import artifacts_for
from utils.batch_pipeline.intake_outcome import IntakeRouteEvidence
from utils.batch_pipeline.live import OWNER, record_identity
from utils.batch_pipeline.language_metrics import record_admission_exclusion
from utils.batch_pipeline.capture_decode import decode_units
from utils.capture.batch_coverage import covered_response
from utils.batch_pipeline import record_gap_fill
from config.record_gap_fill import gap_fill_enabled
from utils.executors import db_executor, storage_executor, run_blocking, sync_executor
from utils.sync.stage import current_stage
from utils.sync.legacy_dark import LegacySyncMode


class RecordUploadRoute(Enum):
    LEGACY = 'legacy_owned'
    BATCH = 'batch_owned'


logger = logging.getLogger(__name__)


class RecordUploadWait(Enum):
    TARGET_UNRESOLVED = 'target_unresolved'
    RESERVATION_PENDING = 'reservation_pending'
    OWNER_CLAIM_RACED = 'owner_claim_raced'
    OWNER_CONTEXT_MISMATCH = 'owner_context_mismatch'
    RECEIPT_STATUS_MISSING = 'receipt_status_missing'
    CONTENT_RECEIPT_CONFLICT = 'content_receipt_conflict'
    RECORD_JOBS_MISSING = 'record_jobs_missing'
    AUDIO_COVERAGE_UNPROVEN = 'audio_coverage_unproven'
    ALIAS_CONFLICT = 'alias_conflict'
    ARTIFACT_LOOKUP_FAILED = 'artifact_lookup_failed'
    COVERAGE_CHECK_FAILED = 'coverage_check_failed'
    ALIAS_WRITE_FAILED = 'alias_write_failed'
    RECEIPT_STATUS_READ_FAILED = 'receipt_status_read_failed'


def _pending(reason: RecordUploadWait, record: str | None = None):
    # These are custody waits, not evidence of Cloud Run refusing a request.
    # Keep the branch vocabulary static and omit identities/audio/error text.
    # ``record`` is a 16-hex prefix of the record content hash (the intake key
    # bp_<content>), so repeated waits can be grouped per recording without ids.
    # No Retry-After: shipped clients read any 5xx carrying one as an
    # account-wide pause, so one conversation's wait stalled every other WAL
    # on the phone (2026-11-07 503 storm). Without it the drain skips this
    # recording for the pass and keeps uploading the rest, after the client's
    # own short unscoped-5xx pause (2-30s, reset by a success); the WAL is kept.
    # The body's retry_after_seconds paces only this recording in new apps.
    logger.info('event=sync_record_upload outcome=pending reason=%s record=%s', reason.value, (record or '-')[:16])
    return JSONResponse(
        status_code=503,
        content={
            'code': 'record_capture_pending',
            'detail': 'Retain local audio until the registered record is complete',
            'retry_after_seconds': RECORD_WAIT_CACHE_SECONDS,
        },
    )


# Conversation-level waits: any WAL for the conversation gets the same answer
# until record state changes. Content-level waits (coverage, receipts) are not
# memoized here, since another WAL of the same conversation may already be provable.
_MEMOIZED_WAITS = frozenset({RecordUploadWait.RECORD_JOBS_MISSING, RecordUploadWait.RESERVATION_PENDING})


async def conversation_pending(reason: RecordUploadWait, uid: str, conversation_id: str | None):
    if reason in _MEMOIZED_WAITS and isinstance(conversation_id, str) and conversation_id:
        await run_blocking(db_executor, remember_record_wait, uid, conversation_id, reason.value)
    return _pending(reason, _record_key(uid, conversation_id))


def _record_key(uid: str, conversation_id: str | None) -> str | None:
    return record_identity(uid, conversation_id)[0] if isinstance(conversation_id, str) and conversation_id else None


async def memoized_record_wait(uid, conversation_id) -> JSONResponse | None:
    """Repeat a recent conversation-level custody wait before any upload work."""
    if not isinstance(conversation_id, str) or not conversation_id:
        return None
    cached = await run_blocking(db_executor, cached_record_wait, uid, conversation_id)
    if cached is None:
        return None
    try:
        reason = RecordUploadWait(cached)
    except ValueError:
        return None
    return _pending(reason, _record_key(uid, conversation_id)) if reason in _MEMOIZED_WAITS else None


def _pcm(wav):
    with wave.open(io.BytesIO(wav), 'rb') as stream:
        return stream.readframes(stream.getnframes())


def _coverage_wait_key(uid, conversation_id, content_id, jobs):
    # content_id already hashes each uploaded basename (capture timestamp and
    # codec) plus its bytes, without decoding. record_identity is stable for the
    # conversation, NOT a revision: hash the current jobs too, so added units or
    # changed artifact references/timing invalidate immediately. Existing reads
    # supply all inputs; no extra Firestore lookup or local file read is needed.
    payload = json.dumps([uid, conversation_id, content_id, jobs], sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _covered(paths, jobs, artifacts):
    # Input bundles and raw captures can have different chunk boundaries. Match
    # their actual sample intervals and bytes, never just timestamps or text.
    record = [
        WorkItem(**{field.name: job[field.name] for field in fields(WorkItem) if field.name in job})
        for job in sorted(jobs, key=lambda job: (job['capture_at'], job['segment_id']))
    ]
    # A long recording can have 128 units. Keep one source unit at a time and
    # fetch only intersections, rather than retaining many hours of decoded PCM.
    for unit in decode_units(paths):
        pcm = _pcm(unit.wav)
        consumed = 0
        for item in record:
            cursor = unit.capture_at + consumed / 32000
            if (
                item.capture_at + item.duration_seconds <= cursor
                or item.capture_at >= unit.capture_at + unit.duration_seconds
            ):
                continue
            offset = round((cursor - item.capture_at) * 16000) * 2
            if offset < 0:
                # The WAL has audio before (or between) the record's units.
                return _unproven('wal_audio_outside_record')
            source = _pcm(artifacts.fetch_audio(item))
            length = min(len(source) - offset, len(pcm) - consumed)
            if length <= 0:
                return _unproven('record_unit_exhausted')
            if memoryview(source)[offset : offset + length] != memoryview(pcm)[consumed : consumed + length]:
                return _unproven('audio_bytes_differ')
            consumed += length
            del source
            if consumed == len(pcm):
                break
        if consumed != len(pcm):
            # The record ends (or has no unit) before this WAL unit does.
            return _unproven('wal_audio_past_record')
    return True


def _unproven(cause: str) -> bool:
    # Static vocabulary only: says which way the WAL and record disagree.
    logger.info('event=sync_record_coverage outcome=unproven cause=%s', cause)
    return False


async def _legacy_mode(legacy_mode, uid):
    """The caller's mode, else one off-loop read (a cold process gets its bounded first wait)."""
    # Imported per call: router harnesses stub ``utils`` wholesale.
    from utils.sync import legacy_dark

    return legacy_mode if legacy_mode is not None else await run_blocking(db_executor, legacy_dark.current_mode, uid)


async def _legacy_final_pass_route(uid, conversation_id, store, legacy_mode) -> RecordUploadRoute:
    """``legacy_final_pass_v1`` keeps today's route in ``on``; after that, re-home or hold.

    In ``draining``/``dark`` legacy can no longer serve this conversation, so a
    successful re-home routes the upload to batch intake. A held re-home (a live
    legacy job for the uid, a lost CAS) keeps the LEGACY route: the router's fence
    answers the shipped in-progress ACK and the client retries.
    """
    from utils.sync import final_pass_rehome

    if not conversation_id:
        return RecordUploadRoute.LEGACY
    mode = await _legacy_mode(legacy_mode, uid)
    outcome = await run_blocking(
        db_executor, final_pass_rehome.upload_rehome, mode, uid, conversation_id, firestore_client=store.client
    )
    return RecordUploadRoute.BATCH if final_pass_rehome.rehomes_to_batch(outcome) else RecordUploadRoute.LEGACY


async def _legacy_takes_new_owner(policy, legacy_mode, uid, language=None) -> bool:
    """An ownerless conversation goes to legacy only at ``on``: for a narrowed uid,
    or (batch eligibility, lead 41e13b) a conversation language known to be
    unsupported by batch Parakeet.

    Outside ``on`` legacy may take no new owner (M3 re-review): batch owns it even
    for a narrowed uid, as intake widens such an upload anyway. The mode is read
    only when the policy would otherwise pick legacy.
    """
    from utils.sync import legacy_dark

    if policy.batch_enabled and not known_unsupported_batch_language(language):
        return False
    return await _legacy_mode(legacy_mode, uid) is legacy_dark.LegacySyncMode.ON


async def _language_exclusion(store, uid, conversation):
    """Only a new owner/re-home needs this preference read; rollback adds no IO."""
    if not admission_language_exclusion_enabled():
        return None, None
    user = await run_blocking(db_executor, lambda: store.client.collection('users').document(uid).get().to_dict() or {})
    _, reason = batch_admission_language(user, conversation)
    return reason, conversation.get('language') or user.get('language')


async def registered_record_response(
    *,
    uid,
    conversation_id,
    content_id,
    paths,
    source,
    client_device_id,
    byok_enabled=False,
    recording_session_id=None,
    loaded_conversation=None,
    policy=None,
    legacy_mode=None,
    evidence: IntakeRouteEvidence | None = None,
) -> JSONResponse | RecordUploadRoute | None:
    policy = policy or resolve_batch_policy(uid)
    if not conversation_id and not recording_session_id:
        return None
    # No owner-discovery read while dark. Callers can supply ownership from a
    # snapshot their existing provenance/privacy path already needed.
    if not policy.live_admission_enabled and not (loaded_conversation or {}).get('record_lane_owner'):
        return None
    store = await run_blocking(db_executor, FirestoreStore, f'batch_pipeline_{current_stage()}')

    def target_snapshot() -> tuple[str | None, Any]:
        user = store.client.collection('users').document(uid)
        target = resolve_target(uid, conversation_id, recording_session_id, firestore_client=store.client)
        return (target, user.collection('conversations').document(target).get()) if target else (None, None)

    snapshot = None
    if loaded_conversation is not None:
        row = loaded_conversation
    else:
        conversation_id, snapshot = await run_blocking(db_executor, target_snapshot)
        if snapshot is None or conversation_id is None:
            return _pending(RecordUploadWait.TARGET_UNRESOLVED) if policy.live_record_enabled else None
        row = snapshot.to_dict() or {}
    if row.get('record_lane_owner') != OWNER:
        if row.get('record_lane_owner') == 'legacy_final_pass_v1':
            # The upload follows a prior durable owner whether the re-home
            # succeeds (BATCH) or holds (LEGACY): never a fresh batch admission.
            if evidence is not None:
                evidence.final_pass_owner_followed = True
            return await _legacy_final_pass_route(uid, conversation_id, store, legacy_mode)
        if row.get('record_lane_owner') == 'batch_sync_v1':
            return RecordUploadRoute.BATCH
        # A pre-enable capture can exist without an owner until its finalizer
        # reserves one. Hold its WAL too: starting sync here would race that
        # reservation and process the same retained audio through two jobs.
        awaiting_reservation = (
            not row.get('record_lane_owner')
            and row.get('status') in {'in_progress', 'processing'}
            and not byok_enabled
            and record_capture_eligible(uid, row, policy=policy)
        )
        if awaiting_reservation or (snapshot is not None and not snapshot.exists and policy.live_record_enabled):
            return await conversation_pending(RecordUploadWait.RESERVATION_PENDING, uid, conversation_id)
        if snapshot is not None and snapshot.exists and not row.get('record_lane_owner'):
            # Only enabled admission may establish a new dispatcher. BYOK takes the
            # batch owner like any upload (David, 10-19): no request-scoped keys needed.
            legacy_mode = await _legacy_mode(legacy_mode, uid)
            reason, language = (
                await _language_exclusion(store, uid, row) if legacy_mode is LegacySyncMode.ON else (None, None)
            )
            if reason or legacy_mode is not LegacySyncMode.ON:
                # A prior batch content receipt must drain before new-custody
                # eligibility, even if this conversation has no owner marker.
                prior = await run_blocking(db_executor, store.run, lambda tx: tx.get('content', f'{uid}/{content_id}'))
                if prior.get('dispatch_protocol') == 'batch_v1':
                    return RecordUploadRoute.BATCH
            legacy_owner = bool(reason) or await _legacy_takes_new_owner(policy, legacy_mode, uid, row.get('language'))
            owner = 'legacy_final_pass_v1' if legacy_owner else 'batch_sync_v1'
            revision = await run_blocking(
                db_executor,
                claim_record_lane_owner,
                uid,
                conversation_id,
                owner,
                snapshot.update_time,
                firestore_client=store.client,
            )
            if revision is None:
                return _pending(RecordUploadWait.OWNER_CLAIM_RACED)
            if reason:
                record_admission_exclusion(language, reason, legacy_available=True)
            # A fresh legacy claim caused by this conversation's language is a
            # language exclusion like ``reason``; a narrowed policy is not (the
            # ramp already recorded its own exclusion).
            if (
                evidence is not None
                and legacy_owner
                and (reason or (policy.batch_enabled and known_unsupported_batch_language(row.get('language'))))
            ):
                evidence.language_excluded = True
            return RecordUploadRoute.BATCH if owner == 'batch_sync_v1' else RecordUploadRoute.LEGACY
        return None
    if byok_enabled or row.get('uses_custom_stt'):
        return JSONResponse(
            status_code=409,
            content={
                'code': 'record_capture_byok_conflict',
                'detail': 'BYOK audio cannot join this capture because server record processing already owns it',
                'retryable': False,
            },
        )
    if row.get('deleted') or row.get('source') != source or row.get('client_device_id') != client_device_id:
        return _pending(RecordUploadWait.OWNER_CONTEXT_MISMATCH)
    content, _ = record_identity(uid, conversation_id)

    def read(tx):
        tx.check_privacy(uid, (conversation_id,))
        prior = tx.get('content', f'{uid}/{content_id}')
        if prior.get('dispatch_protocol') == 'batch_v1' and prior.get('job_id') == 'bp_' + content:
            return prior, []
        intake = tx.get('intakes', 'bp_' + content)
        jobs = [tx.get('jobs', segment) for segment in intake.get('segment_ids', [])]
        return prior, jobs

    try:
        prior, jobs = await run_blocking(db_executor, store.run, read)
    except BatchPrivacyBlocked:
        return JSONResponse(
            status_code=409,
            content={
                'code': 'record_capture_privacy_blocked',
                'detail': 'Capture is unavailable for server processing',
            },
        )
    from utils.batch_pipeline.record_lease_append import retain_upload

    await retain_upload(uid, conversation_id, row, paths, store)
    if prior.get('dispatch_protocol') == 'batch_v1' and prior.get('job_id') == 'bp_' + content:
        status = await run_blocking(db_executor, durable_status, store, uid, prior['job_id'])
        return start_response(status) if status else _pending(RecordUploadWait.RECEIPT_STATUS_MISSING, content)
    if prior:
        return _pending(RecordUploadWait.CONTENT_RECEIPT_CONFLICT, content)
    if not jobs:
        if gap_fill_enabled(uid):
            # A closed record whose retained tail never landed cannot admit;
            # write this owner WAL's missing span so the drain's next normal
            # pass can. Option A (RECORD_RETAINED_ACK): once the server holds
            # a byte-exact durable copy of every WAL sample, answer the covered
            # 200 so the phone releases this batch and sends the next one.
            # Otherwise the answer is the same 503.
            _, acked = await record_gap_fill.run_gap_fill(
                uid=uid,
                conversation_id=conversation_id,
                paths=paths,
                wal_content_id=content_id,
                store=store,
            )
            if acked:
                return covered_response()
        return await conversation_pending(RecordUploadWait.RECORD_JOBS_MISSING, uid, conversation_id)
    coverage_key = None
    if coverage_wait_memo_enabled():
        coverage_key = _coverage_wait_key(uid, conversation_id, content_id, jobs)
        if await run_blocking(db_executor, cached_coverage_wait, coverage_key):
            return _pending(RecordUploadWait.AUDIO_COVERAGE_UNPROVEN, content)
    failure_reason = RecordUploadWait.ARTIFACT_LOOKUP_FAILED
    try:
        artifacts = await run_blocking(storage_executor, artifacts_for, store)
        failure_reason = RecordUploadWait.COVERAGE_CHECK_FAILED
        if not await run_blocking(sync_executor, _covered, paths, jobs, artifacts):
            if coverage_key is not None:
                await run_blocking(db_executor, remember_coverage_wait, coverage_key)
            return _pending(RecordUploadWait.AUDIO_COVERAGE_UNPROVEN, content)

        def alias(tx):
            current = tx.get('content', f'{uid}/{content_id}')
            original = tx.get('content', f'{uid}/{content}')
            tx.check_privacy(uid, (conversation_id,))
            if current and current.get('job_id') != original.get('job_id'):
                return False
            tx.put(
                'content',
                f'{uid}/{content_id}',
                {
                    **original,
                    'record_content_id': content,
                    'expires_at': datetime.now(timezone.utc) + timedelta(days=LEDGER_RETENTION_DAYS),
                },
            )
            return True

        failure_reason = RecordUploadWait.ALIAS_WRITE_FAILED
        if not await run_blocking(db_executor, store.run, alias):
            return _pending(RecordUploadWait.ALIAS_CONFLICT, content)
        failure_reason = RecordUploadWait.RECEIPT_STATUS_READ_FAILED
        status = await run_blocking(db_executor, durable_status, store, uid, 'bp_' + content)
        return start_response(status) if status else _pending(RecordUploadWait.RECEIPT_STATUS_MISSING, content)
    except Exception:
        # An erased/missing manifest cannot prove WAL coverage. Retain it;
        # never translate a storage/privacy failure into legacy compute.
        return _pending(failure_reason, content)
