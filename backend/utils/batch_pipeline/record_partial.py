"""Resumable partial admission on the real batch worker and projection path."""

from dataclasses import replace
from enum import StrEnum
import json
import logging
from prometheus_client import Counter

from config import record_partial as config
from config.record_audio import require_record_audio_barrier
from database.batch_pipeline_intake import admit
from database.batch_pipeline_policy import load_job_policy
from database.record_partial import update_run, continuation_refusal
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.batch_pipeline.record_partial_audio import digest, inventory_digest, missing_units, union
from utils.batch_pipeline.scheduler import owner_key
from utils.batch_pipeline.source_audio import MAGIC
from utils.executors import db_executor, storage_executor, sync_executor, run_blocking
from utils.other.storage import list_audio_chunks
from utils.observability.reasons import ReasonFamily, reason_label

logger = logging.getLogger(__name__)
RERUNS = Counter(
    'omi_record_audio_partial_reruns_total', 'Observed partial continuation outcomes', ['phase', 'outcome']
)


class PartialRerunOutcome(StrEnum):
    UNKNOWN = 'unknown'
    SCHEDULED = 'scheduled'
    COMPLETED = 'completed'
    UNCHANGED = 'unchanged'
    NO_NEW_AUDIO = 'no_new_audio'
    WAITING = 'waiting'
    STATE_CHANGED = 'state_changed'
    BOUNDED = 'bounded'
    RETRY = 'retry'
    PRIVACY_REFUSED = 'privacy_refused'
    BYOK_REFUSED = 'byok_refused'
    DISCARDED_REFUSED = 'discarded_refused'
    RETIRED = 'retired'


def event(outcome, *, late=False):
    # No identities, storage paths, exception messages or open labels.
    try:
        outcome = PartialRerunOutcome(outcome)
    except ValueError:
        outcome = PartialRerunOutcome.STATE_CHANGED
    phase = 'late' if late else 'initial'
    logger.info('event=record_partial_rerun phase=%s outcome=%s count=1', phase, outcome)
    RERUNS.labels(
        phase=phase, outcome=reason_label(ReasonFamily.RECORD_PARTIAL_RERUN, outcome, PartialRerunOutcome)
    ).inc()


def record_failure(error, *, privacy=False, run=None):
    bounded = str(error) in {
        'partial source budget exceeded',
        'partial unit budget exceeded',
        'partial coverage budget exceeded',
        'batch artifact exceeds bounded payload size',
        'speaker audio listing budget exhausted',
    }
    late = bool(run and (run.get('generation', 0) > 1 or run.get('complete')))
    event(
        (
            'privacy_refused'
            if privacy
            else 'byok_refused' if str(error) == 'partial BYOK excluded' else 'bounded' if bounded else 'retry'
        ),
        late=late,
    )


def seed_for(pending):
    return WorkItem(
        pending['segment_id'],
        pending['owner_id'],
        0,
        'record:pending',
        1,
        Priority.FRESH,
        conversation_id=pending['conversation_id'],
        privacy_generation=pending['privacy_generation'],
    )


def page_content(run):
    return digest([run['fingerprint'], run['generation'], run['page'], run['plan_digest']])


def unit_coverage(units):
    return [
        [round(start * 16000) + ref['start_frame'], round(start * 16000) + ref['start_frame'] + ref['frames']]
        for start, _, refs in units
        for ref in refs
    ]


async def prepare_run(store, pending, current, barrier, client, artifacts, units_reader, now):
    previous = pending.get('partial_run')
    chunks = await run_blocking(
        storage_executor,
        list_audio_chunks,
        pending['owner_id'],
        pending['conversation_id'],
        max_count=config.MAX_SOURCES,
        require_archive=True,
    )
    fingerprint = inventory_digest(chunks)
    refusal = await run_blocking(db_executor, continuation_refusal, store, pending)
    if refusal:
        event(refusal, late=bool(previous))
        return None
    if previous and previous.get('complete') and previous['fingerprint'] == fingerprint:
        changed_at = previous.get('inventory_changed_at', now)
        updated = {
            **previous,
            'inventory_changed_at': changed_at,
            'next_inventory_at': now + config.INVENTORY_POLL_SECONDS,
        }
        if now - changed_at >= config.INVENTORY_IDLE_SECONDS:
            updated['retired_at'] = now
        changed = await run_blocking(db_executor, update_run, store, pending, barrier, previous, updated, now=now)
        if changed and updated.get('retired_at'):
            event('retired', late=True)
            return None
        event('unchanged', late=True)
        return None
    seed = seed_for(pending)
    await run_blocking(db_executor, artifacts.authorize, seed)
    iterator = units_reader(
        pending['owner_id'],
        pending['conversation_id'],
        chunks,
        client,
        artifacts.key_for_owner(pending['owner_id']),
        partial=True,
    )
    coverage = (previous or {}).get('coverage', [])

    def collect():
        try:
            return missing_units(iterator, coverage)
        finally:
            iterator.close()

    units, _ = await run_blocking(sync_executor, collect)
    plan = {'version': 1, 'fingerprint': fingerprint, 'units': units, 'prior_coverage': coverage}
    uri = await run_blocking(storage_executor, artifacts.stage_record_plan, seed, plan)
    generation = int((previous or {}).get('generation', 0)) + 1
    run = {
        'fingerprint': fingerprint,
        'generation': generation,
        'page': 0,
        'units': len(units),
        'coverage': coverage,
        'plan_uri': uri,
        'plan_digest': digest(plan),
        'complete': not units,
        'inventory_changed_at': now,
        'next_inventory_at': now + config.INVENTORY_POLL_SECONDS,
    }
    changed = await run_blocking(
        db_executor,
        update_run,
        store,
        pending,
        barrier,
        previous,
        run,
        now=now,
        applied=not units,
    )
    event('scheduled' if changed and units else 'no_new_audio' if changed else 'state_changed', late=generation > 1)
    return run if changed else None


async def drain_partial(store, pending, current, client, artifacts, units_reader, *, now):
    if not config.enabled() or not pending.get('partial_coordinator'):
        raise ValueError('partial record barrier disabled')
    run = pending.get('partial_run')
    late = bool(run and (run.get('generation', 0) > 1 or run.get('complete')))
    if current.get('discarded'):
        event('discarded_refused', late=late)
        return {'outcome': 'partial'}
    _, policy = await run_blocking(db_executor, load_job_policy, store, pending['segment_id'])
    if policy is None or policy.provider_reason == 'byok':
        event('byok_refused' if policy is not None else 'state_changed', late=late)
        return {'outcome': 'partial'}
    barrier = require_record_audio_barrier(current)
    if pending.get('state') == 'partial_retired' or (
        run and run.get('complete') and now < run.get('next_inventory_at', 0)
    ):
        return {'outcome': 'partial'}
    if run and run.get('complete'):
        # Every serving replica can drain recordings. Claim this hourly poll
        # before listing so stale/concurrent scheduler snapshots do no IO.
        claimed = {**run, 'next_inventory_at': now + config.INVENTORY_POLL_SECONDS}
        if not await run_blocking(db_executor, update_run, store, pending, barrier, run, claimed, now=now):
            return {'outcome': 'partial'}
        pending = {**pending, 'partial_run': claimed}
    if not run or run.get('complete'):
        await prepare_run(store, pending, current, barrier, client, artifacts, units_reader, now)
        return {'outcome': 'partial'}
    content = page_content(run)
    ledger = await run_blocking(
        db_executor, store.run, lambda tx: tx.get('content', f"{pending['owner_id']}/{content}")
    )
    if ledger and ledger.get('status') != 'completed':
        event('waiting', late=run['generation'] > 1)
        return {'outcome': 'partial'}
    refusal = await run_blocking(db_executor, continuation_refusal, store, pending)
    if refusal:
        event(refusal, late=run['generation'] > 1)
        return {'outcome': 'partial'}
    seed = seed_for(pending)
    plan = await run_blocking(storage_executor, artifacts.load_record_plan, seed, run['plan_uri'])
    if digest(plan) != run['plan_digest'] or plan['fingerprint'] != run['fingerprint']:
        raise ValueError('partial continuation changed')
    offset = run['page'] * config.PAGE_UNITS
    units = plan['units'][offset : offset + config.PAGE_UNITS]
    if not units:
        raise ValueError('partial page unavailable')
    if ledger.get('status') == 'completed':
        updated = {
            **run,
            'page': run['page'] + 1,
            'coverage': union([*run['coverage'], *unit_coverage(units)]),
            'complete': offset + len(units) == len(plan['units']),
            'next_inventory_at': now + config.INVENTORY_POLL_SECONDS,
        }
        changed = await run_blocking(
            db_executor,
            update_run,
            store,
            pending,
            barrier,
            run,
            updated,
            now=now,
            applied=bool(updated['complete']),
        )
        event('completed' if changed else 'state_changed', late=run['generation'] > 1)
        return {'outcome': 'partial'}
    await admit_page(store, pending, current, barrier, artifacts, plan, run, units, content, now)
    return {'outcome': 'partial'}


async def admit_page(store, pending, current, barrier, artifacts, plan, run, units, content, now):
    uid, cid = pending['owner_id'], pending['conversation_id']
    _, policy = await run_blocking(db_executor, load_job_policy, store, pending['segment_id'])
    if policy is None or policy.provider_reason == 'byok':
        event('byok_refused', late=run['generation'] > 1)
        return
    refusal = await run_blocking(db_executor, continuation_refusal, store, pending)
    if refusal:
        event(refusal, late=run['generation'] > 1)
        return
    items = [
        WorkItem(
            digest([content, i]),
            uid,
            start,
            'record:pending',
            duration,
            Priority.FRESH,
            conversation_id=cid,
            privacy_generation=pending['privacy_generation'],
            requires_compute_admission=True,
        )
        for i, (start, duration, _) in enumerate(units)
    ]
    row = pending['record_snapshot']
    protection = await run_blocking(db_executor, artifacts.authorize, seed_for(pending))
    binding = ProjectionBinding(
        uid,
        'bp_' + content,
        content,
        tuple(item.segment_id for item in items),
        source=row.get('source') or 'omi',
        client_device_id=row.get('client_device_id'),
        client_platform=row.get('client_platform'),
        private_cloud_sync_enabled=True,
        target_conversation_id=cid,
        privacy_generation=pending['privacy_generation'],
        language=row.get('language'),
        data_protection_level=protection.level,
        record_origin=True,
        native_record=True,
        partial_record=True,
    )
    staged = []
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
            'conversation_id': cid,
            'stt_language': binding.language or '',
            'stt_language_evidence': 'declared',
            'stt_language_confidence': 1.0,
        }
        manifest = {
            'owner_id': uid,
            'conversation_id': cid,
            'capture_at': item.capture_at,
            'references': refs,
            'context': context,
        }
        uri = await run_blocking(
            storage_executor,
            artifacts.stage_audio,
            item,
            MAGIC + json.dumps(manifest, separators=(',', ':')).encode(),
        )
        staged.append(replace(item, audio_uri=uri))
    intake = {
        'owner_id': uid,
        'owner_key': owner_key(uid),
        'content_id': content,
        'conversation_id': cid,
        'segment_ids': list(binding.segment_ids),
        'total_files': sum(len(refs) for _, _, refs in units),
        'total_audio_seconds': sum(item.duration_seconds for item in items),
        'lane': 'fresh',
        'record_ranges': [{'start': item.capture_at, 'end': item.capture_at + item.duration_seconds} for item in items],
        'record_partial_parent': pending['segment_id'],
        'record_partial_generation': run['generation'],
        'record_partial_page': run['page'],
        'record_partial_content': content,
        **({'server_batch_only': True} if row.get('server_batch_only') is True else {}),
    }
    await run_blocking(
        db_executor,
        admit,
        store,
        staged,
        binding,
        now,
        namespace=store.namespace,
        policy=policy,
        require_artifacts=True,
        record_barrier=barrier,
        intake=intake,
    )
