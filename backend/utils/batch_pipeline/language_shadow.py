"""Probe-only qualification on the first canonical batch unit of new legacy uploads.

No artifact, serving job, GPU transcription, projection or usage mutation.
One reserved pair per immutable upload prevents duplicate/retry sample inflation.
"""

from dataclasses import replace
import hashlib
import logging
import shutil

from prometheus_client import Counter

from config.batch_pipeline_shadow import language_only_enabled, selected
from config.batch_pipeline_providers import provider_config
from config.prerecorded_language import language_class
from config.stt_provider_policy import normalized_stt_language
from database.batch_pipeline_language_shadow import LanguageShadowStore
from utils.batch_pipeline.capture_decode import decode_units
from utils.batch_pipeline.contracts import WorkItem, Priority
from utils.batch_pipeline.retention import batch_artifact_authorize
from utils.executors import db_executor, storage_executor, sync_executor, run_blocking
from utils.stt.batch_language import compare_shadow_pair
from utils.stt_cap_dispatch import sync_allowed
from utils.sync.content_id import compute_sync_content_id
from utils.sync.input_limits import BackfillInputLimitExceeded, validate_language_probe_paths

logger = logging.getLogger(__name__)
UNITS = Counter('omi_batch_language_shadow_total', 'Probe-only qualification admission and outcomes', ['outcome'])


def first_unit(paths):
    validate_language_probe_paths(paths)
    iterator = decode_units(paths, max_seconds=provider_config().max_unit_seconds)
    try:
        return next(iterator, None)
    finally:
        iterator.close()


def compare(repository, item, unit):
    def before_call():
        return (
            language_only_enabled()
            and repository.authorize(item)
            and sync_allowed(item.owner_id, min(unit.duration_seconds, 30), 'modulate', lane='batch')
        )

    return compare_shadow_pair(unit.wav, before_call=before_call)


async def offer_upload(*, uid, content_id, paths, conversation_id, byok, policy, **_unused):
    from utils.batch_pipeline.shadow_intake import copy_paths, repository_for_stage

    if byok or not language_only_enabled() or not selected(uid, policy):
        return
    directory, repository, reserved, item = None, None, False, None
    try:
        if content_id is None:
            content_id = await run_blocking(sync_executor, compute_sync_content_id, uid, paths)
        store = (await run_blocking(db_executor, repository_for_stage)).store
        seed = WorkItem(
            hashlib.sha256(f'{content_id}:0'.encode()).hexdigest(),
            uid,
            0,
            'intake:language-shadow',
            1,
            Priority.DEEP,
            shadow=True,
            conversation_id=conversation_id,
        )
        snapshots = {}
        context = await run_blocking(db_executor, batch_artifact_authorize, store, seed, snapshots=snapshots)
        user = snapshots['user']
        target = snapshots.get('conversations', {}).get(conversation_id) or {}
        if user.get('stt_byok_enabled') or target.get('record_lane_owner') == 'batch_live_v1':
            return
        prefs = user.get('transcription_preferences') or {}
        language = normalized_stt_language(user.get('language')) if prefs.get('single_language_mode') else 'multi'
        if language_class(language) != 'unknown':
            UNITS.labels('declared').inc()
            return
        item = replace(seed, privacy_generation=context.generation)
        UNITS.labels('eligible').inc()
        try:
            await run_blocking(storage_executor, validate_language_probe_paths, paths)
        except BackfillInputLimitExceeded:
            UNITS.labels('oversized').inc()
            return
        repository = await run_blocking(db_executor, LanguageShadowStore, store)
        if not await run_blocking(db_executor, repository.reserve, item):
            UNITS.labels('not_reserved').inc()
            return
        reserved = True
        directory, copies = await run_blocking(storage_executor, copy_paths, paths)
        owned_directory, directory = directory, None
        reserved = False
        # Remain inside the already tracked offer task, including its cleanup.
        await qualify(repository, item, copies, owned_directory)
    except Exception as error:
        UNITS.labels('error').inc()
        logger.info('event=batch_language_shadow outcome=error exception_type=%s', type(error).__name__)
    finally:
        try:
            if reserved and repository is not None and item is not None:
                await run_blocking(db_executor, repository.release, item)
        finally:
            if directory:
                await run_blocking(storage_executor, shutil.rmtree, directory)


async def qualify(repository, item, paths, directory):
    try:
        unit = await run_blocking(sync_executor, first_unit, paths)
        if unit is None:
            UNITS.labels('no_unit').inc()
            return
        matched = await run_blocking(sync_executor, compare, repository, item, unit)
        UNITS.labels('matched' if matched else 'unmatched').inc()
    except Exception as error:
        UNITS.labels('error').inc()
        logger.info('event=batch_language_shadow outcome=error exception_type=%s', type(error).__name__)
    finally:
        try:
            await run_blocking(db_executor, repository.release, item)
        finally:
            await run_blocking(storage_executor, shutil.rmtree, directory)
