"""Durable live/desktop admission, drained independently of reconciliation.

Capture reserves its route in the existing conversation create. Finalization
registers a privacy-fenced pending job before closing its own durable job. No
Firestore reads are added to audio frames, provisional segments or pusher flush.
"""

import asyncio
from dataclasses import replace
from collections.abc import Generator
from typing import Any
import hashlib
import json
import logging
import math
import os
import random
import time

from utils.conversations import phase_shadow

from config.policy import resolve_batch_policy
from config.audio_archive import derived_audio_bucket
from config.record_audio import BARRIER_NOT_CLOSED, require_record_audio_barrier, record_identity
from config.record_partial import UNIT_SECONDS, UNIT_REFERENCES, INVENTORY_POLL_SECONDS
from config.record_drain import (
    record_drain_batch,
    record_drain_concurrency,
    record_drain_lease_seconds,
    record_drain_privacy_defer_seconds,
    record_drain_idle_without_progress_enabled,
    barrier_retry_delay,
    record_drain_barrier_backoff_enabled,
)
from database.batch_pipeline_policy import load_job_policy
from database.batch_ramp import ramp_admission_policy
from config.batch_pipeline import (
    Priority,
    RecordOwnerContention,
    record_capture_eligible,
    batch_held_dead_letter_enabled,
    RECORD_DEAD_LETTER_SECONDS,
)
from database.conversations import claim_record_lane_owner, is_soft_deleted
from utils.batch_pipeline.record_provider import admit_record_units
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_store import FirestoreStore
from database.batch_pipeline_shadow_hook import shadow_from_env
from utils.batch_pipeline.artifact_policy import create_artifact_store
from utils.batch_pipeline.contracts import ProjectionBinding, WorkItem
from utils.batch_pipeline.scheduler import owner_key
from utils.batch_pipeline.source_audio import MAGIC, MAX_REFERENCES, read_reference, batch_timing_store
from utils.batch_pipeline.record_barrier import validate_record_tail
from utils.batch_pipeline.record_language import prove_manifest
from utils.batch_pipeline.language_receipt import admission as language_admission_receipt
from utils.batch_pipeline.record_partial import drain_partial, record_failure as record_partial_failure
from config.record_seal_rules import overlap_trim_enabled
from utils.executors import db_executor, storage_executor, run_blocking
from utils.other.local_storage import create_storage_client
from utils.other.storage import list_audio_chunks, private_cloud_sync_bucket
from utils.sync.stage import current_stage
from config.server_batch import owned as server_batch_owned, has_audio as server_batch_has_audio

logger = logging.getLogger(__name__)
OWNER = 'batch_live_v1'
UPLOAD_GRACE_SECONDS = 0
# Literal admission refusals worth counting; any other text could carry a value
# and is reported only as `other`.
_RETRY_REASONS = frozenset(
    {
        'audio staging reservation missing or reclaimed',
        'capture upload barrier changed during staging',
        BARRIER_NOT_CLOSED,
        'complete ordered sibling set must match immutable projection binding',
        'conflicting retained audio overlap',
        'existing segment cannot change its immutable intake binding',
        'invalid encrypted audio frame',
        'invalid retained audio size',
        'native provider outbox factory required',
        'partial continuation changed',
        'partial continuation ownership changed',
        'partial page unavailable',
        'partial record barrier disabled',
        'pending recording owner cannot change',
        'record owner is immutable',
        'record protocol cutover barrier closed',
        'registered record target unavailable',
        'retained audio reference is outside admitted source',
        'retained audio source exceeds size budget',
        'retained capture checksum mismatch',
        'retained capture finish missing',
        'retained capture not durable yet',
        'retained capture reference budget exceeded',
        'retained capture tail not durable yet',
        'retained capture unit budget exceeded',
        'retained source has no aligned audio',
        'truncated encrypted audio length',
        'unit has no capture end',
        'work identity must match projection binding',
    }
)


def _retry_reason(error: BaseException) -> str:
    if not isinstance(error, ValueError):
        return '-'
    text = str(error)
    return text.replace(' ', '_').replace('/', '_') if text in _RETRY_REASONS else 'other'


BATCH_LEDGER_OWNERS = frozenset({OWNER, 'batch_sync_v1'})


def observe_admitted(uid: str, conversation: dict, *, now=None) -> bool:
    """Fail-open C1 admission: the capture entered the in-flight ledger.

    The row is created at the durable admission that gives this capture a batch
    owner, so the census gets a denominator row even when the capture never
    reaches a later stage. A later repair that admits after the seal already
    wrote ``sealed`` keeps that forward stage: the ledger is forward-only and
    refuses the rewind. A reconnect or finalizer replay can only produce a
    duplicate, a forward refusal, or an illegal-transition refusal; never a
    second admission. A deleted capture gets no row, matching the seal's fence.
    """
    capture_id = conversation.get('id')
    if not isinstance(capture_id, str) or not capture_id or conversation.get('deleted'):
        return False
    try:
        from database import pipeline_ledger

        return pipeline_ledger.advance(
            uid, capture_id, pipeline_ledger.CAPTURING, now=time.time() if now is None else now
        )
    except Exception as error:  # The real admission is already authoritative.
        logger.warning('event=batch_live_ledger outcome=error stage=capturing exception_type=%s', type(error).__name__)
        return False


def reserve_recording(uid: str, conversation: dict) -> str | None:
    """Cover captures already in progress at enablement, before legacy admission."""
    owner = conversation.get('record_lane_owner')
    if owner:
        # A lane claimed on a streaming path is still an admission; the writer is
        # idempotent, and a sealed or later row keeps its forward stage.
        if owner in BATCH_LEDGER_OWNERS:
            observe_admitted(uid, conversation)
        return owner
    policy = resolve_batch_policy(uid)
    if conversation.get('status') not in {'in_progress', 'processing'} or not record_capture_eligible(
        uid, conversation, policy=policy
    ):
        return None
    if not ramp_admission_policy(uid, policy).live_record_enabled:
        return None
    revision = claim_record_lane_owner(uid, conversation['id'], OWNER, conversation.get('updated_at'))
    if revision is None:
        raise RecordOwnerContention('record route snapshot changed')
    conversation.update(record_lane_owner=OWNER, updated_at=revision)
    observe_admitted(uid, conversation)
    return OWNER


def register_recording(
    uid: str, conversation: dict, *, store=None, now=None, transaction=None, server_flags=None, restoring: bool = False
) -> bool:
    if conversation.get('record_lane_owner') != OWNER:
        return False
    if server_batch_owned(conversation) and not server_batch_has_audio(conversation):
        return False
    if conversation.get('deleted') or conversation.get('uses_custom_stt'):
        return False
    # Only explicit register-first restore may cross the discard fence. Use
    # restore's tombstone predicate and also refuse a merged-away donor.
    if restoring:
        if is_soft_deleted(conversation) or conversation.get('sync_merged_into'):
            return False
    elif conversation.get('discarded'):
        return False
    if not conversation.get('private_cloud_sync_enabled'):
        return False
    if transaction is None:
        store = store or shadow_from_env(FirestoreStore(f'batch_pipeline_{current_stage()}'))
    now = time.time() if now is None else now
    content, segment = record_identity(uid, conversation['id'])
    # The immutable native owner is main's earlier admission receipt. A later
    # cohort rollback cannot cancel it before finalization registers the unit.
    policy = replace(
        resolve_batch_policy(uid, flags=server_flags) if server_flags is not None else resolve_batch_policy(uid),
        batch_enabled=True,
        live_admission_enabled=True,
        live_record_enabled=True,
    )
    snapshot = {
        key: conversation.get(key)
        for key in (
            'id',
            'source',
            'language',
            'client_device_id',
            'client_platform',
            'started_at',
            'finished_at',
            'data_protection_level',
        )
    }
    if (conversation.get('external_data') or {}).get('server_batch_only') is True:
        snapshot['server_batch_only'] = True

    def commit(tx):
        previous = tx.get('jobs', segment)
        if previous:
            return True
        generation = tx.check_privacy(uid, (conversation['id'],))
        tx.put(
            'jobs',
            segment,
            {
                'segment_id': segment,
                'owner_id': uid,
                'owner_key': owner_key(uid),
                'conversation_id': conversation['id'],
                'privacy_generation': generation,
                'priority': int(Priority.FRESH),
                'state': 'record_pending',
                'available_at': now + UPLOAD_GRACE_SECONDS,
                'enqueued_at': now,
                'record_content_id': content,
                'record_snapshot': snapshot,
                'policy': policy.to_dict(),
                'policy_source': 'admission',
                'merge_pending': False,
                **({'registration_origin': 'restore'} if restoring else {}),
            },
        )
        return True

    # Operator seal backfill joins registration to the row's existing transaction.
    # The caller owns flushing buffered writes after all privacy reads complete.
    if transaction is not None:
        return commit(transaction)
    assert store is not None
    return store.run(commit)


def retained_record_units(
    uid, conversation_id, chunks, client, key, *, diagnostics=None, partial=False, decoded_tail=None
) -> Generator[tuple[float, float, list[dict[str, Any]]], None, None]:
    """Bounded one-hour units; earlier retained objects own overlapping frames."""
    trim_divergent = overlap_trim_enabled()
    unit_frames = (UNIT_SECONDS if partial else 3600) * 16000
    reference_limit = UNIT_REFERENCES if partial else MAX_REFERENCES
    allowed = {private_cloud_sync_bucket, derived_audio_bucket()}
    references, start, end, previous_pcm = [], None, None, b''
    capture_origin = None
    for chunk in chunks:
        ref = {
            'path': chunk['path'],
            'bucket': chunk.get('bucket', private_cloud_sync_bucket),
            'generation': int(chunk['generation']),
        }
        if chunk.get('span'):
            ref['sample_rate'] = int(chunk['span'].get('sample_rate', 16000))
        if decoded_tail is not None and decoded_tail.get('chunk') is chunk:
            ref, pcm = dict(decoded_tail['ref']), decoded_tail['pcm']
        else:
            pcm = read_reference(
                client, ref, uid, conversation_id, allowed, key, source_metadata=True, listed_source=chunk
            )
            if decoded_tail is not None and chunk is chunks[-1]:
                decoded_tail.update(chunk=chunk, ref=dict(ref), pcm=pcm)
        if not pcm or len(pcm) % 2:
            raise ValueError('retained source has no aligned audio')
        comparison_pcm = pcm
        source_digest = hashlib.sha256(pcm).hexdigest()
        source_skip = 0
        raw_offset = chunk.get('raw_offset_samples')
        if raw_offset is not None:
            # A listed raw fragment selects its own samples from the unchanged
            # pack. A gapped pack yields one fragment per contiguous run, so
            # reading the whole pack for every fragment would duplicate audio
            # and close the writer's gaps.
            count = int((chunk.get('span') or {}).get('samples', 0))
            if count <= 0:
                raise ValueError('raw fragment has no sample span')
            source_skip = int(raw_offset)
            pcm = pcm[source_skip * 2 : (source_skip + count) * 2]
            if len(pcm) != count * 2:
                raise ValueError('raw fragment exceeds its source pack')
            # The next overlap compares against this fragment's tail, not the
            # whole pack the fragment was selected from.
            comparison_pcm = pcm
        capture = float(chunk['timestamp'])
        if capture_origin is None:
            capture_origin = capture
        # Quantize once to the capture's sample grid. Independent rounding of
        # overlap lengths and manifest positions disagrees at half-frame ties.
        capture = capture_origin + round((capture - capture_origin) * 16000) / 16000
        # Resolve even a one-frame overlap: the manifest reader forbids
        # overlapping slices, so the proof cannot let that frame through twice.
        if end is not None and round((end - capture) * 16000) > 0:
            overlap = round((end - capture) * 16000) * 2
            if overlap > len(previous_pcm):
                raise ValueError('conflicting retained audio overlap')
            # A contained object compares only the frames it actually carries.
            prior_start = len(previous_pcm) - overlap
            divergent = pcm[:overlap] != previous_pcm[prior_start : prior_start + min(overlap, len(pcm))]
            if divergent and not trim_divergent:
                raise ValueError('conflicting retained audio overlap')
            # Preserve the old refusal for short contained objects when off.
            if not trim_divergent and len(pcm) < overlap:
                raise ValueError('conflicting retained audio overlap')
            if divergent and diagnostics is not None:
                diagnostics['trimmed_divergent_overlaps'] = diagnostics.get('trimmed_divergent_overlaps', 0) + 1
            source_skip = source_skip + overlap // 2
            pcm, capture = pcm[overlap:], end
            if not pcm:
                continue
            # The next overlap may reach into this object's discarded prefix.
            # Keep its full extent with earlier accepted bytes in that prefix,
            # so both the size fence and divergence count use the accepted union.
            comparison_pcm = previous_pcm[-overlap:] + pcm if trim_divergent else pcm
        if start is not None and end is not None and capture - end > 30:
            yield start, end - start, references
            references, start = [], None
        offset = 0
        while offset < len(pcm):
            if start is None:
                start = capture + offset / 32000
            position = round((capture + offset / 32000 - start) * 16000)
            if position >= unit_frames or partial and len(references) >= reference_limit:
                if end is None:
                    raise ValueError('unit has no capture end')
                yield start, end - start, references
                references, start = [], None
                continue
            frames = min((len(pcm) - offset) // 2, unit_frames - position)
            references.append(
                {
                    **ref,
                    'pcm_sha256': source_digest,
                    'start_frame': position,
                    'offset_frame': source_skip + offset // 2,
                    'frames': frames,
                }
            )
            if len(references) > MAX_REFERENCES:
                raise ValueError('retained capture reference budget exceeded')
            offset += frames * 2
            end = capture + offset / 32000
            if position + frames == unit_frames:
                yield start, end - start, references
                references, start = [], None
        previous_pcm = comparison_pcm
    if references and start is not None and end is not None:
        yield start, end - start, references


async def admit_recording(store, pending, *, now=None, provider_outbox_factory=None):
    from config.batch_pipeline import require_record_protocol_ready

    require_record_protocol_ready()
    now = time.time() if now is None else now
    uid, conversation_id = pending['owner_id'], pending['conversation_id']
    row = pending['record_snapshot']
    content = pending['record_content_id']

    def read_current():
        return (
            store.client.collection('users')
            .document(uid)
            .collection('conversations')
            .document(conversation_id)
            .get()
            .to_dict()
            or {}
        )

    current = await run_blocking(db_executor, read_current)
    try:
        record_barrier = require_record_audio_barrier(current)
    except ValueError:
        phase_shadow.observe('batch_admission', current, False, now=now)
        raise
    phase_shadow.observe('batch_admission', current, True, now=now)
    client = await run_blocking(storage_executor, create_storage_client)
    bucket = os.getenv('BUCKET_BATCH_PIPELINE', '').strip()
    artifacts = create_artifact_store(store, client, bucket, os.getenv('ENCRYPTION_SECRET', '').encode())
    if current.get('record_audio_partial'):
        return await drain_partial(
            store,
            pending,
            current,
            client,
            artifacts,
            retained_record_units,
            now=now,
            provider_outbox_factory=provider_outbox_factory,
        )
    # A failed raw-archive listing raises (drain retries in 60 s) rather than
    # admitting a recording whose later packs are silently missing.
    chunks = await run_blocking(
        storage_executor, list_audio_chunks, uid, conversation_id, max_count=4096, require_archive=True
    )
    if not chunks:
        raise ValueError('retained capture not durable yet')
    seed = WorkItem(
        pending['segment_id'],
        uid,
        0,
        'record:pending',
        1,
        Priority.FRESH,
        conversation_id=conversation_id,
        privacy_generation=pending['privacy_generation'],
    )
    protection = await run_blocking(db_executor, artifacts.authorize, seed)
    iterator = retained_record_units(uid, conversation_id, chunks, client, artifacts.key_for_owner(uid))
    units = []
    try:
        # Advancing the generator downloads retained objects. Keep that leaf
        # I/O off the smaller sync pool used by serving and sync coordinators.
        while unit := await run_blocking(storage_executor, next, iterator, None):
            units.append(unit)
            if len(units) > 128:
                raise ValueError('retained capture unit budget exceeded')
    finally:
        iterator.close()
    # Never claim a successful record whose final recognized speech is missing
    # from the durable upload. The pending obligation has no TTL.
    validate_record_tail(units, row.get('finished_at'))
    validate_record_tail(units, current.get('finished_at'))
    from utils.batch_pipeline.language_receipt import auto_language_cohort

    receipt_enabled = auto_language_cohort(
        server_batch_only=row.get('server_batch_only') is True,
        client_platform=row.get('client_platform'),
        native_record=True,
        language=row.get('language'),
    )
    items = [
        WorkItem(
            hashlib.sha256(f'{content}:{i}'.encode()).hexdigest(),
            uid,
            start,
            'record:pending',
            duration,
            Priority.FRESH,
            conversation_id=conversation_id,
            privacy_generation=pending['privacy_generation'],
            requires_compute_admission=True,
            language_receipt_enabled=True if receipt_enabled else None,
        )
        for i, (start, duration, _) in enumerate(units)
    ]
    _, policy = await run_blocking(db_executor, load_job_policy, store, pending['segment_id'])
    binding = ProjectionBinding(
        uid,
        'bp_' + content,
        content,
        tuple(i.segment_id for i in items),
        source=row.get('source') or 'omi',
        client_device_id=row.get('client_device_id'),
        client_platform=row.get('client_platform'),
        private_cloud_sync_enabled=True,
        target_conversation_id=conversation_id,
        privacy_generation=pending['privacy_generation'],
        language=row.get('language'),
        data_protection_level=protection.level,
        record_origin=True,
        native_record=True,
    )
    staged, language_receipts = [], {}
    for item, (_, _, refs) in zip(items, units):
        context = {
            'owner_id': uid,
            'job_id': binding.job_id,
            'content_id': content,
            'segment_id': item.segment_id,
            'capture_at': item.capture_at,
            'source': binding.source,
            'should_lock': False,
            'client_device_id': binding.client_device_id,
            'client_platform': binding.client_platform,
            'conversation_id': conversation_id,
            # Declared profiles preserve their proof. Auto capture must replace
            # these fields with independent whole-unit audio proof below.
            'stt_language': binding.language or '',
            'stt_language_evidence': 'declared',
            'stt_language_confidence': 1.0,
        }
        manifest = {
            'owner_id': uid,
            'conversation_id': conversation_id,
            'capture_at': item.capture_at,
            'references': refs,
            'context': context,
        }
        if row.get('server_batch_only') is True:
            manifest = await prove_manifest(store, artifacts, item, manifest)
        if item.language_receipt_enabled:
            language_receipts[item.segment_id] = language_admission_receipt(manifest['context'])
        uri = await run_blocking(
            storage_executor, artifacts.stage_audio, item, MAGIC + json.dumps(manifest, separators=(',', ':')).encode()
        )
        staged.append(replace(item, audio_uri=uri, timing_store=batch_timing_store(refs)))
    return await run_blocking(
        db_executor,
        admit_record_units,
        store,
        staged,
        binding,
        now,
        namespace=store.namespace,
        policy=policy,
        provider_outbox_factory=provider_outbox_factory,
        require_artifacts=True,
        record_barrier=record_barrier,
        intake={
            'owner_id': uid,
            'owner_key': owner_key(uid),
            'content_id': content,
            'conversation_id': conversation_id,
            'segment_ids': list(binding.segment_ids),
            'total_files': len(chunks),
            'total_audio_seconds': sum(i.duration_seconds for i in staged),
            'lane': 'fresh',
            'record_ranges': [{'start': i.capture_at, 'end': i.capture_at + i.duration_seconds} for i in staged],
            **({'language_receipts': language_receipts} if language_receipts else {}),
            **({'server_batch_only': True} if row.get('server_batch_only') is True else {}),
        },
    )


async def drain_recordings(store, *, provider_outbox_factory=None, metrics=None) -> bool:
    """Drain one bounded pass; return whether a full page warrants another."""
    started = time.monotonic()
    batch_size = record_drain_batch()
    concurrency = record_drain_concurrency()
    lease_seconds = record_drain_lease_seconds()
    segments, partial_count = [], 0
    privacy_blocked = False
    # Rows this pass actually admitted. A full page of deferred/failed rows (for
    # example captures still behind their upload barrier) made no progress, so
    # rescanning at once only re-reads it (2026-11-07: store:due 4x in 30 min).
    admitted = 0
    # Every admission rewrites the owner's scheduler row, so two local workers
    # admitting one owner only exhaust each other's contention retries. Leave
    # the busy owner's other rows due for the next pass instead.
    busy_owners = set()

    async def drain_one(segment):
        nonlocal privacy_blocked
        pending = await run_blocking(db_executor, store.run, lambda tx: tx.get('jobs', segment))
        if pending.get('state') != 'record_pending':
            return
        owner = pending.get('owner_id')
        if owner in busy_owners:
            return
        busy_owners.add(owner)
        try:
            try:
                lease = await run_blocking(db_executor, store.run, lambda tx: claim(tx, segment))
            except BatchPrivacyBlocked:
                # The claim write meets the same privacy fence as admission;
                # erasure owns the row and this worker moves on. A fence-exempt
                # available_at-only defer takes it off the oldest page, so the
                # rows behind it are not starved; an undeferred row stays due.
                privacy_blocked = not await defer_privacy_blocked(segment) or privacy_blocked
                return
            if lease is None:
                return
            await admit_and_defer(segment, pending, lease)
        finally:
            busy_owners.discard(owner)

    async def defer_privacy_blocked(segment):
        delay = record_drain_privacy_defer_seconds()
        if not delay:
            return False
        now = time.time()
        try:
            return await run_blocking(db_executor, store.defer_privacy_blocked_record, segment, now + delay, now)
        except Exception as error:
            logger.warning(
                'event=batch_live_admission outcome=privacy_defer_failed exception_type=%s', type(error).__name__
            )
            return False

    def claim(tx, segment):
        # Every replica selects the same oldest page. Without a claim, each one
        # repeated the same listing, download and staging for a row until the
        # first finished, multiplying admission work by the replica count. A
        # bounded lease moves the row out of other replicas' due pages; a
        # crashed worker's row becomes due again when the lease ends.
        latest = tx.get('jobs', segment)
        now = time.time()
        if latest.get('state') != 'record_pending' or latest.get('available_at', 0) > now:
            return None
        lease = now + lease_seconds
        latest['available_at'] = lease
        tx.put('jobs', segment, latest)
        return lease

    async def admit_and_defer(segment, pending, lease):
        nonlocal partial_count, privacy_blocked, admitted
        partial_count += bool(pending.get('partial_coordinator'))
        failed = barrier_open = False
        try:
            if provider_outbox_factory is None:
                await admit_recording(store, pending)
            else:
                await admit_recording(store, pending, provider_outbox_factory=provider_outbox_factory)
        except BatchPrivacyBlocked as error:
            # Privacy cleanup owns erasure; an admission retry cannot bypass it.
            # These rows remain due, so a full page must keep the idle wait.
            privacy_blocked = True
            if pending.get('partial_coordinator'):
                record_partial_failure(error, privacy=True, run=pending.get('partial_run'))
            return
        except Exception as error:
            failed = True
            barrier_open = isinstance(error, ValueError) and str(error) == BARRIER_NOT_CLOSED
            if pending.get('partial_coordinator'):
                record_partial_failure(error, run=pending.get('partial_run'))
            logger.warning(
                'event=batch_live_admission outcome=retry exception_type=%s reason=%s tables=%s record=%s',
                type(error).__name__,
                _retry_reason(error),
                getattr(error, 'store_tables', 'n/a'),
                # Same one-way key as the sync pending line (record content hash prefix), so the two join.
                str(pending.get('record_content_id') or '-')[:16],
            )

        def defer(tx):
            # Admission can return without moving the obligation (for example
            # a partial capture waiting on inventory). Re-read after admission
            # so a no-op cannot monopolize every immediately repeated pass,
            # and never overwrite a concurrently admitted row.
            latest = tx.get('jobs', segment)
            if latest.get('state') != 'record_pending':
                # The row left record_pending: it was admitted (by us or a peer). A
                # peer's dead-letter is not an admission, so it is not progress.
                return latest.get('state') != 'dead', False
            now = time.time()
            expired = False
            if barrier_open and latest.get('available_at') == lease and batch_held_dead_letter_enabled():
                deadline = latest.get('record_dead_letter_deadline_at')
                if deadline is None:
                    latest['record_dead_letter_deadline_at'] = now + RECORD_DEAD_LETTER_SECONDS
                elif (
                    not isinstance(deadline, bool)
                    and isinstance(deadline, (int, float))
                    and math.isfinite(deadline)
                    and deadline <= now
                ):
                    latest.update(
                        state='dead',
                        merge_pending=False,
                        dead_letter_reason='record_barrier_aged',
                        record_dead_letter_at=now,
                    )
                    expired = True
            delay = 60
            if not failed and (latest.get('partial_run') or {}).get('complete'):
                delay = INVENTORY_POLL_SECONDS
            elif barrier_open and record_drain_barrier_backoff_enabled():
                # The capture is not finalized yet: back off by how long it has waited.
                enqueued = latest.get('enqueued_at')
                age = (
                    max(0.0, now - enqueued)
                    if not isinstance(enqueued, bool) and isinstance(enqueued, (int, float)) and math.isfinite(enqueued)
                    else 0.0
                )
                delay = barrier_retry_delay(age)
            # Our own lease ends now; a later deferral written during
            # admission (or another replica's newer lease) is kept.
            current = latest.get('available_at', 0)
            latest['available_at'] = max(0 if current == lease else current, now + delay)
            tx.put('jobs', segment, latest)
            return False, expired

        # Progress means the row actually left record_pending; a normal return can be a
        # no-op (an unchanged partial inventory poll), which must not count. The
        # dead-letter verdict rides the same transaction but is not progress.
        progressed, expired = await run_blocking(db_executor, store.run, defer)
        if progressed:
            admitted += 1
        if expired and metrics is not None:
            metrics.record_dead_letter.inc()

    async def worker():
        # next() has no await: each selected row belongs to one local worker.
        for segment in remaining:
            await drain_one(segment)

    try:
        segments = await run_blocking(db_executor, store.due, 'record_pending', time.time(), batch_size)
        # Every replica selects the same oldest page; a per-replica order plus
        # the per-row lease keeps replicas from admitting the same rows at once.
        random.shuffle(segments)
        remaining = iter(segments)
        # Join every worker even on failure; a retry must not overlap unfinished
        # work from this pass. Across replicas the existing intake/partial CAS
        # still decides admission; the lease only hides a row, never expires it.
        results = await asyncio.gather(
            *(worker() for _ in range(min(concurrency, len(segments)))), return_exceptions=True
        )
        for result in results:
            if isinstance(result, BaseException):
                raise result
        progressed = admitted > 0 or not record_drain_idle_without_progress_enabled()
        return len(segments) == batch_size and not privacy_blocked and progressed
    finally:
        logger.info(
            'event=batch_drain_pass row_count=%s partial_count=%s seconds=%.3f',
            len(segments),
            partial_count,
            time.monotonic() - started,
        )
