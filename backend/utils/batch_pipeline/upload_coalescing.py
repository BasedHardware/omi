"""Durable raw-upload custody before unit admission, with per-upload receipts.

The narrow first cohort is ordinary batch uploads to one explicit target,
with a recording identity, known supported language, no alternate decoder,
no coverage claims or early capture clocks, no provider/BYOK/native record.
Everything else takes existing per-upload admission. No encoded audio is
concatenated: the sealed raw files use the existing canonical decoder.
"""

from dataclasses import asdict, replace
import base64
import hashlib
import json
import math
from pathlib import Path
import tempfile
import time

from prometheus_client import Counter

from config import batch_pipeline_coalescing as config
from config.policy import BatchUnitPolicy
from database import batch_pipeline_coalescing as rows
from utils.batch_pipeline.contracts import WorkItem
from utils.batch_pipeline.capture_decode import decode_units
from utils.batch_pipeline.scheduler import owner_key
from utils.executors import run_blocking, db_executor, storage_executor, sync_executor

EVENTS = Counter('omi_batch_upload_coalescing_total', 'Pre-unit custody outcomes; no identities', ['outcome'])


def queued(member):
    return {
        'job_id': member['job_id'],
        'status': 'queued',
        'lane': member['lane'],
        'total_files': member['files'],
        'total_segments': 0,
        'processed_segments': 0,
        'successful_segments': 0,
        'failed_segments': 0,
        'errors': [],
        'result': None,
        'poll_after_ms': 3000,
    }


def member_status(store, uid, intake, read_status):
    if not intake.get('coalesce_group'):
        return None
    if intake['owner_id'] != uid:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail='Not authorized to view this sync job')
    store.run(lambda tx: rows.authorize(tx, intake))
    content = store.run(lambda tx: tx.get('content', f"{uid}/{intake['content_id']}"))
    from database.sync_ledger import is_valid_completed_sync_content_result

    if content.get('status') == 'completed' and is_valid_completed_sync_content_result(content.get('result')):
        return {
            **queued(intake),
            'status': 'completed',
            'result': content['result'],
            'total_segments': intake['original_units'],
            'processed_segments': intake['original_units'],
            'successful_segments': intake['original_units'],
            'poll_after_ms': 0,
        }
    if not intake.get('coalesce_target'):
        return queued(intake)
    status = read_status(store, uid, intake['coalesce_target'])
    if status is None:
        return queued(intake)
    # Completion is conservative: ALL group siblings must complete before
    # any member releases phone custody. Each member still has its own handle.
    complete = status['status'] == 'completed'
    result = status.get('result') if complete else None
    if result is not None:
        result = {**result, 'total_segments': intake['original_units']}
        rows.checkpoint_completion(store, intake, result, time.time())
    return {
        **status,
        'job_id': intake['job_id'],
        'total_files': intake['files'],
        'total_segments': intake['original_units'],
        'processed_segments': intake['original_units'] if complete else 0,
        'successful_segments': intake['original_units'] if complete else 0,
        'failed_segments': intake['original_units'] if status['status'] == 'failed' else 0,
        'result': result,
    }


def _pack(paths, arguments):
    if len(json.dumps(arguments, allow_nan=False).encode()) > 64 * 1024:
        return None
    files = []
    size = 0
    for path in paths:
        name = Path(path).name
        if name != str(name) or '/' in name or '\\' in name or not name.endswith('.bin'):
            raise ValueError('bounded original upload basename required')
        with open(path, 'rb') as source:
            data = source.read(config.MAX_MEMBER_BYTES + 1)
        size += len(data)
        if size > config.MAX_MEMBER_BYTES:
            return None
        files.append(
            {'name': name, 'body': base64.b64encode(data).decode(), 'sha256': hashlib.sha256(data).hexdigest()}
        )
    if not 0 < len(files) <= config.MAX_FILES or len({f['name'] for f in files}) != len(files):
        return None
    # The existing decoder consumes its .bin inputs. Inspect private copies so
    # a declined hold or a failed commit can still use the original admission.
    with tempfile.TemporaryDirectory(prefix='batch-hold-inspect-') as directory:
        copied = []
        source_frames = 0
        for file in files:
            path = Path(directory) / file['name']
            original = base64.b64decode(file['body'], validate=True)
            path.write_bytes(original)
            # Source admission denominator excludes decoder-inserted gap
            # silence. Count each original file's canonical samples ONCE,
            # independently of either the baseline or grouped unit packing.
            single = decode_units([str(path)])
            try:
                source_frames += sum(round(unit.duration_seconds * 16000) for unit in single)
            finally:
                single.close()
            path.write_bytes(original)
            copied.append(str(path))
        iterator = decode_units(copied)
        try:
            spans = [(unit.capture_at, unit.duration_seconds) for unit in iterator]
        finally:
            iterator.close()
    if not spans or sum(d for _, d in spans) > config.MAX_AUDIO_SECONDS:
        return None
    start, end = min(s for s, _ in spans), max(s + d for s, d in spans)
    if not all(math.isfinite(v) for v in (start, end)):
        return None
    body = json.dumps({'files': files, 'arguments': arguments}, allow_nan=False, separators=(',', ':')).encode()
    return (
        body,
        len(body),
        start,
        end,
        sum(d for _, d in spans),
        len(spans),
        [rows.digest(f['name']) for f in files],
        source_frames,
    )


async def offer(store, artifacts, seed, *, arguments, context, language, policy, now=None):
    """Called only after ordinary route/privacy selection, before unit staging."""
    if not config.enabled():
        return None
    now = time.time() if now is None else now
    upload_context = arguments.get('intake_context') or {}
    session = upload_context.get('recording_session_id')
    if not (
        arguments['conversation_id']
        and arguments['client_device_id']
        and isinstance(session, str)
        and 0 < len(session) <= 128
        and language
        and not arguments.get('byok_enabled')
        and not upload_context.get('capture_evidence_claims')
        and not upload_context.get('capture_received_at')
    ):
        return None
    packed = await run_blocking(
        sync_executor, _pack, arguments['paths'], {k: v for k, v in arguments.items() if k != 'paths'}
    )
    if packed is None:
        EVENTS.labels(outcome='bounded_bypass').inc()
        return None
    body, size, start, end, seconds, unit_count, filenames, source_frames = packed
    hold = config.hold_seconds(now=now, batch_pre_unit=True)
    if hold <= 0:
        return None
    # This source item is a deletion-outbox identity, never a scheduler job.
    item = replace(
        seed,
        segment_id=await run_blocking(sync_executor, rows.digest, ['held-source', arguments['content_id']]),
        capture_at=start,
        duration_seconds=seconds,
        privacy_generation=context.generation,
    )
    uri = await run_blocking(storage_executor, artifacts.stage_audio, item, body)
    member = {
        'owner_id': arguments['uid'],
        'owner_key': owner_key(arguments['uid']),
        'conversation_id': arguments['conversation_id'],
        'privacy_generation': context.generation,
        'content_id': arguments['content_id'],
        'job_id': 'bp_' + arguments['job_id'],
        'item': asdict(replace(item, audio_uri=uri)),
        'uri': uri,
        'bytes': size,
        'files': len(arguments['paths']),
        'filenames': filenames,
        'seconds': seconds,
        'start': start,
        'end': end,
        'original_units': unit_count,
        'source_frames': source_frames,
        'source_sample_rate': 16000,
        'lane': arguments['lane'],
        'hold_seconds': hold,
        'accepted_at': now,
        'policy': policy.to_dict(),
        'language': language,
    }
    # Metadata is hashed for identity; private context remains encrypted in body.
    key = await run_blocking(
        sync_executor,
        rows.digest,
        [
            arguments['uid'],
            session,
            arguments['conversation_id'],
            arguments['source'],
            arguments['client_device_id'],
            arguments['client_platform'],
            arguments['should_lock'],
            context.level,
            context.generation,
            language,
            policy.policy_id,
            arguments['lane'],
            int(seed.priority),
            sorted({tuple(Path(p).name.split('_')[1:4]) for p in arguments['paths']}),
            upload_context.get('geolocation'),
        ],
    )
    admitted = await run_blocking(db_executor, rows.enqueue, store, member, key, now)
    if admitted == 'wait':
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=503,
            headers={'Retry-After': '1'},
            content={'code': 'sync_batch_unavailable', 'detail': 'Retain local audio'},
        )
    if admitted is None:
        EVENTS.labels(outcome='quota_bypass').inc()
        return None
    # A racing prior content owner must be answered through its existing status,
    # never represented as our newly held receipt.
    from utils.batch_pipeline.intake import durable_status, start_response

    status = await run_blocking(db_executor, durable_status, store, arguments['uid'], admitted)
    if status is None:
        raise ValueError('coalescing receipt unavailable')
    EVENTS.labels(outcome='accepted').inc()
    return start_response(status)


def _unpack(body, directory):
    package = json.loads(body)
    paths = []
    size = 0
    for file in package['files']:
        name = file['name']
        if (
            not isinstance(name, str)
            or Path(name).name != name
            or '/' in name
            or '\\' in name
            or not name.endswith('.bin')
        ):
            raise ValueError('invalid held upload path')
        data = base64.b64decode(file['body'], validate=True)
        size += len(data)
        if size > config.MAX_MEMBER_BYTES or hashlib.sha256(data).hexdigest() != file['sha256']:
            raise ValueError('held upload size or hash mismatch')
        path = Path(directory) / name
        with path.open('xb') as target:
            target.write(data)
        paths.append(str(path))
    if not 0 < len(paths) <= config.MAX_FILES:
        raise ValueError('invalid held file count')
    return package['arguments'], paths


async def drain_group(store, artifacts, group_id, *, admit_upload=None, now=None):
    if admit_upload is None:
        from utils.batch_pipeline.intake import accept_upload

        admit_upload = accept_upload
    clock = time.time if now is None else lambda: now
    group = await run_blocking(db_executor, rows.claim, store, group_id, clock(), producer_enabled=config.enabled())
    if group is None:
        return False
    # Temporary files are reconstructible copies of the encrypted, generation-
    # pinned originals. A crash leaves sources and the sealed membership intact.
    directory = tempfile.TemporaryDirectory(prefix='batch-coalesce-')
    try:
        uploads = []
        for index, member in enumerate(group['members']):
            item = WorkItem(**member['item'])
            body = await run_blocking(storage_executor, artifacts.fetch_audio, item)
            destination = Path(directory.name) / str(index)
            await run_blocking(storage_executor, destination.mkdir)
            arguments, paths = await run_blocking(sync_executor, _unpack, body, destination)
            uploads.append((arguments, paths))
        targets = []
        batches = [uploads] if group['mode'] == 'merged' else [[upload] for upload in uploads]
        for batch in batches:
            args = dict(batch[0][0])
            args['paths'] = [path for _, paths in batch for path in paths]
            if group['mode'] == 'merged':
                content = await run_blocking(sync_executor, rows.digest, [group['id'], 'merged'])
                args.update(job_id=content, content_id=content)
                args['intake_context'] = {
                    **(args.get('intake_context') or {}),
                    'filenames': [Path(p).name for p in args['paths']],
                    'raw_capture_paths': list(
                        dict.fromkeys(
                            path
                            for original, _ in batch
                            for path in ((original.get('intake_context') or {}).get('raw_capture_paths') or [])
                        )
                    ),
                }
            args.update(
                policy=BatchUnitPolicy.from_dict(group['members'][0]['policy']),
                vendor_table=False,
                _coalescing_group=group,
            )
            response = await admit_upload(**args)
            if response is None or response.status_code != 202:
                raise ValueError('held upload admission remains uncommitted')
            target = json.loads(bytes(response.body))['job_id']
            targets.extend([target] * len(batch))
        await run_blocking(db_executor, rows.finish, store, group, targets, clock())
        EVENTS.labels(outcome='drained_merged' if group['mode'] == 'merged' else 'drained_individual').inc()
        return True
    finally:
        await run_blocking(storage_executor, directory.cleanup)


async def drain(store):
    # Readers/drainers intentionally operate with producer OFF. An empty scan
    # is bounded; no process dictionary is authoritative for accepted audio.
    from utils.batch_pipeline.artifact_policy import artifacts_for

    enabled = config.enabled()
    epoch, after = await run_blocking(db_executor, rows.scan_position, store)
    page = await run_blocking(
        db_executor, lambda: rows.due(store.client, store.namespace, time.time(), producer_enabled=enabled, after=after)
    )
    if page or after is not None:
        await run_blocking(db_executor, rows.advance_scan, store, epoch, page[-1] if page else None)
    if not page:
        await run_blocking(db_executor, rows.note_scan, store, time.time(), producer_enabled=enabled)
        return
    artifacts = await run_blocking(storage_executor, artifacts_for, store)
    failed = False
    for entry in page:
        try:
            await drain_group(store, artifacts, entry['id'])
        except Exception as error:
            failed = True
            import logging

            EVENTS.labels(outcome='drain_retry').inc()
            logging.getLogger(__name__).warning(
                'event=batch_coalescing outcome=retry exception_type=%s', type(error).__name__
            )
    if not failed:
        await run_blocking(db_executor, rows.note_scan, store, time.time(), producer_enabled=enabled)
