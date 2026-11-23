"""One bounded process owner for optional playback discovery, never audio PCM."""

import asyncio
import os
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from utils.pusher_audio_projection import PusherAudioProjection

from utils.executors import playback_metadata_executor, playback_debt_executor, run_blocking, start_background_task
from database import record_projection_rebuild
from utils.pusher_receive_metrics import observe_work
from utils.observability.fallback import record_fallback

MAX_CONVERSATIONS = 128
MAX_PATHS = 2048
WORKERS = 2


@dataclass
class Refresh:
    uid: str
    cid: str
    paths: tuple[str, ...]
    closing: bool
    callback: Callable[[str, bool | None], None] | None
    observed_update_time: Any = None


class PlaybackCoordinator:
    def __init__(self):
        self.pending: OrderedDict[tuple[str, str], Refresh] = OrderedDict()
        self.active: dict[tuple[str, str], Refresh] = {}
        self.tasks: set[asyncio.Task] = set()
        self.cache: OrderedDict[tuple[str, str], PusherAudioProjection] = OrderedDict()
        self.loop = asyncio.get_running_loop()

    def submit(self, uid, cid, paths, closing, callback, *, observed_update_time=None):
        key = uid, cid
        prior = self.pending.get(key)
        paths = tuple(dict.fromkeys([*(prior.paths if prior else ()), *(paths or ())]))
        keys = set(self.active) | set(self.pending) | {key}
        weight = (
            sum(len(job.paths) for job in self.active.values())
            + sum(len(job.paths) for k, job in self.pending.items() if k != key)
            + len(paths)
        )
        if len(keys) > MAX_CONVERSATIONS or weight > MAX_PATHS:
            return False
        self.pending[key] = Refresh(
            uid, cid, paths, closing or bool(prior and prior.closing), callback, observed_update_time
        )
        self._start()
        return True

    def _start(self):
        while len(self.tasks) < WORKERS and set(self.pending) - self.active.keys():
            # Reserve the key synchronously, before another submit can start work.
            key = next(key for key in self.pending if key not in self.active)
            self.active[key] = self.pending.pop(key)
            task = start_background_task(self._work(key), name='pusher:playback_metadata')
            self.tasks.add(task)
            task.add_done_callback(self._done)

    def _done(self, task):
        self.tasks.discard(task)
        if task.cancelled():
            self.pending.clear()
        elif not self.loop.is_closed():
            self._start()

    async def wait_owner(self, uid):
        while any(key[0] == uid for key in self.active.keys() | self.pending.keys()):
            tasks = list(self.tasks)
            if not tasks:
                return
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

    async def _work(self, key):
        # Lazy import avoids a cache/coordinator import cycle; no import-time IO.
        from utils.pusher_audio_projection import PusherAudioProjection
        from utils.speaker_learning_jobs import schedule_person_voice_learning_retry

        job = self.active[key]
        cache = self.cache.pop(key, None) or PusherAudioProjection(job.uid)
        try:
            with observe_work('drain_refresh'):
                applied = await run_blocking(
                    playback_metadata_executor, cache.refresh, job.cid, list(job.paths), force=job.closing
                )
            if job.callback is not None:
                job.callback(job.cid, applied)
            if applied is None:
                record_fallback(
                    component='pusher',
                    from_mode='playback_metadata',
                    to_mode='durable_repair',
                    reason='input_missing',
                    outcome='degraded',
                )
            if applied:
                schedule_person_voice_learning_retry(job.uid, job.cid)
            if applied is True and job.closing and job.observed_update_time is not None:
                await run_blocking(
                    playback_debt_executor,
                    record_projection_rebuild.retire_observed,
                    job.uid,
                    job.cid,
                    observed_update_time=job.observed_update_time,
                )
            self.cache[key] = cache
            # Bound cached inventories as well as queued path arguments globally.
            while (
                len(self.cache) > MAX_CONVERSATIONS
                or sum(
                    sum(len(item.chunks) for item in state.inventory.values() if item is not None)
                    for state in self.cache.values()
                )
                > MAX_PATHS
            ):
                self.cache.popitem(last=False)
        except asyncio.CancelledError:
            record_fallback(
                component='pusher',
                from_mode='playback_metadata',
                to_mode='durable_repair',
                reason='cancelled',
                outcome='degraded',
            )
            raise
        except Exception:
            # Write-ahead debt already exists. A worker failure changes no seal proof.
            record_fallback(
                component='pusher',
                from_mode='incremental_audio_files',
                to_mode='audio_file_listing',
                reason='other',
                outcome='degraded',
            )
        finally:
            self.active.pop(key, None)


_owner: PlaybackCoordinator | None = None
_pid = 0


def coordinator():
    global _owner, _pid
    loop = asyncio.get_running_loop()
    if _owner is None or _pid != os.getpid() or (_owner.loop is not loop and not _owner.tasks):
        _owner, _pid = PlaybackCoordinator(), os.getpid()
    if _owner.loop is not loop:
        raise RuntimeError('playback coordinator belongs to another active loop')
    return _owner
