"""Copy selected legacy upload bytes into a bounded, disposable shadow handoff."""

from dataclasses import replace
from pathlib import Path
import asyncio
import logging
import os
import shutil
import tempfile

from config.batch_pipeline import Priority, priority_for, language_inheritance_enabled
from config.batch_language_recovery import inherited_language
from config.prerecorded_language import language_class, language_guard_enabled
from config.stt_provider_policy import normalized_stt_language
from config.batch_pipeline_shadow import language_only_enabled, selected, shadow_percent
from config.batch_pipeline_providers import provider_config
from database.batch_pipeline_store import FirestoreStore
from database.batch_pipeline_shadow import ShadowStore
from utils.batch_pipeline.audio import with_context
from utils.batch_pipeline.capture_decode import decode_units
from utils.batch_pipeline.contracts import WorkItem
from utils.batch_pipeline.artifact_policy import artifacts_for
from utils.batch_pipeline.retention import batch_artifact_authorize
from utils.executors import db_executor, storage_executor, sync_executor, run_blocking, start_background_task
from utils.sync.stage import current_stage
from utils.sync.content_id import compute_sync_content_id

logger = logging.getLogger(__name__)


class _LanguageProbeGuard:
    """Fresh, fail-closed authorization for each model/vendor classification."""

    def __init__(self, store, item):
        self.store, self.item, self.blocked = store, item, False

    def __call__(self):
        from utils.stt_cap_dispatch import sync_allowed
        from utils.funded_processing import consent_allows

        if self.blocked:
            return False
        try:
            batch_artifact_authorize(self.store, self.item)
            allowed = consent_allows(self.item.owner_id) and sync_allowed(
                self.item.owner_id, self.item.duration_seconds, 'modulate', lane='batch'
            )
        except Exception:
            self.blocked = True
            raise
        self.blocked = not allowed
        return allowed


def _next_unit(iterator):
    # StopIteration cannot cross asyncio Future boundaries.
    return next(iterator, None)


def copy_paths(paths):
    directory = tempfile.mkdtemp(prefix='omi-batch-shadow-')
    try:
        copies = []
        for index, path in enumerate(paths):
            target = Path(directory) / f'{index}_{Path(path).name}'
            try:
                # Raw upload bytes are immutable. A private hardlink survives
                # legacy unlink without copying large bundles on its 202 path.
                os.link(path, target)
            except OSError:
                shutil.copy2(path, target)
            copies.append(str(target))
        return directory, copies
    except Exception:
        shutil.rmtree(directory)
        raise


def repository_for_stage():
    # Client construction may resolve credentials/transports. Keep it on the
    # same bounded database executor as the following admission transaction.
    return ShadowStore(FirestoreStore(f'batch_pipeline_{current_stage()}'))


async def offer_upload(
    *, uid, content_id, paths, lane, age, conversation_id, source, device_id, byok, policy, should_lock=False
):
    if language_only_enabled():
        from utils.batch_pipeline.language_shadow import offer_upload as offer_language_upload

        offering = start_background_task(
            offer_language_upload(
                uid=uid,
                content_id=content_id,
                paths=paths,
                conversation_id=conversation_id,
                byok=byok,
                policy=policy,
            ),
            name='batch_language_shadow_offer',
        )
        try:
            await asyncio.wait_for(asyncio.shield(offering), timeout=1)
        except asyncio.TimeoutError:
            # The tracked task may finish best effort; legacy owns its own
            # files and progress. A late copy failure consumes no external call.
            pass
        return
    if byok or not selected(uid, policy):
        return
    repository, reservation, directory = None, None, None
    try:
        if content_id is None:
            content_id = await run_blocking(sync_executor, compute_sync_content_id, uid, paths)
        repository = await run_blocking(db_executor, repository_for_stage)
        class_name = ('fresh', 'recent', 'deep')[int(priority_for(lane, age))]
        reserving = start_background_task(
            run_blocking(db_executor, repository.reserve, uid, content_id + ':0', class_name),
            name='batch_shadow_reserve',
        )
        try:
            reservation = await asyncio.wait_for(asyncio.shield(reserving), timeout=1)
        except asyncio.TimeoutError:
            start_background_task(drop_late_reservation(repository, reserving), name='batch_shadow_late_reserve')
            return
        if reservation is None:
            return
        # Legacy retains its paths and cleanup ownership. Only these copies
        # belong to the tracked task; never touch its progress, locks or ledger.
        directory, copies = await run_blocking(storage_executor, copy_paths, paths)
        start_background_task(
            stage_upload(
                repository,
                reservation,
                uid,
                content_id,
                copies,
                directory,
                class_name,
                conversation_id,
                source,
                device_id,
                should_lock,
            ),
            name='batch_shadow_stage',
        )
    except Exception as error:
        if repository is not None and reservation is not None:
            try:
                await run_blocking(db_executor, repository.finish, reservation[0], 'error')
            except Exception:
                pass
        if directory:
            try:
                await run_blocking(storage_executor, shutil.rmtree, directory)
            except OSError:
                pass
        logger.info('event=batch_shadow_intake outcome=error exception_type=%s', type(error).__name__)


async def drop_late_reservation(repository, task):
    try:
        reservation = await task
        if reservation is not None:
            await run_blocking(db_executor, repository.finish, reservation[0], 'dropped')
    except Exception:
        pass


async def stage_upload(
    repository,
    first,
    uid,
    content_id,
    paths,
    directory,
    class_name,
    conversation_id,
    source,
    device_id,
    should_lock=False,
):
    iterator, reservation = None, first
    try:
        store = repository.store
        seed = WorkItem(
            first[0], uid, 0, 'intake:shadow', 1, Priority.DEEP, shadow=True, conversation_id=conversation_id
        )
        snapshots = {}
        context = await run_blocking(db_executor, batch_artifact_authorize, store, seed, snapshots=snapshots)
        user = snapshots['user']
        target = snapshots.get('conversations', {}).get(conversation_id) or {}
        if target.get('record_lane_owner') == 'batch_live_v1' or user.get('stt_byok_enabled'):
            await run_blocking(db_executor, repository.finish, first[0], 'dropped')
            return
        language = target.get('language') or user.get('language') or ''
        prefs = user.get('transcription_preferences') or {}
        input_language = normalized_stt_language(user.get('language')) if prefs.get('single_language_mode') else 'multi'
        inherit = language_inheritance_enabled()
        inherited = inherited_language(target.get('language'), user.get('language')) if inherit else None
        if inherited:
            language = inherited
            if language_class(inherited) == 'supported':
                input_language = inherited
        elif inherit:
            language = input_language = 'multi'
        artifacts = await run_blocking(storage_executor, artifacts_for, store)
        config = provider_config()
        if config.pool_kind != 'dedicated_batch':
            raise ValueError('shadow requires the existing dedicated batch pool')
        iterator = decode_units(paths, max_seconds=config.max_unit_seconds)
        index = 0
        while unit := await run_blocking(sync_executor, _next_unit, iterator):
            if index:
                reservation = await run_blocking(
                    db_executor, repository.reserve, uid, f'{content_id}:{index}', class_name
                )
            index += 1
            if reservation is None:
                continue
            if not shadow_percent():
                await run_blocking(db_executor, repository.finish, reservation[0], 'dropped')
                break
            from utils.stt.batch_language import resolve_language

            item = replace(
                seed,
                segment_id=reservation[0],
                capture_at=unit.capture_at,
                duration_seconds=unit.duration_seconds,
                privacy_generation=context.generation,
                unit_kind='conversation' if conversation_id else 'capture_span',
            )
            probe = _LanguageProbeGuard(store, item)

            # Mirror serving intake's per-audio proof. A primary-language hint
            # alone cannot authorize fixed-language GPU recognition in multi mode.
            language_decision = await run_blocking(
                sync_executor,
                resolve_language,
                input_language,
                unit.wav,
                surface='batch',
                cohort_key=uid,
                before_probe=probe,
                before_self_probe=probe,
            )
            if probe.blocked:
                await run_blocking(db_executor, repository.finish, reservation[0], 'dropped')
                continue
            frozen_language = (
                language_decision.language
                if language_decision.parakeet_safe or language_class(language_decision.language) == 'unsupported'
                else 'und' if language_guard_enabled() else input_language
            )
            wav = await run_blocking(
                sync_executor,
                with_context,
                unit.wav,
                {
                    'owner_id': uid,
                    'job_id': reservation[0],
                    'content_id': content_id,
                    'segment_id': item.segment_id,
                    'capture_at': item.capture_at,
                    'source': source,
                    'client_device_id': device_id,
                    'should_lock': should_lock,
                    'stt_language': frozen_language,
                    'stt_language_evidence': language_decision.evidence,
                    'stt_language_confidence': language_decision.confidence,
                    'stt_language_probe_seconds': language_decision.probe_seconds,
                },
            )
            uri = await run_blocking(storage_executor, artifacts.stage_audio, item, wav)
            ready = await run_blocking(
                db_executor,
                repository.ready,
                reservation,
                replace(item, audio_uri=uri),
                language,
                projection_context={
                    'source': source,
                    'client_device_id': device_id,
                    'is_locked': should_lock,
                    'language': language,
                    'data_protection_level': context.level,
                },
            )
            if not ready:
                await run_blocking(db_executor, repository.finish, item.segment_id, 'dropped')
        if index == 0:
            await run_blocking(db_executor, repository.finish, first[0], 'error')
    except Exception as error:
        if reservation:
            await run_blocking(db_executor, repository.finish, reservation[0], 'error')
        logger.info('event=batch_shadow_stage outcome=error exception_type=%s', type(error).__name__)
    finally:
        if iterator:
            await run_blocking(sync_executor, iterator.close)
        await run_blocking(storage_executor, shutil.rmtree, directory)
