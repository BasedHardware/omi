"""Server-owned user rollout membership, shared across flags and serving platforms.

Only boolean fields in rollout_cohorts/{uid}.cohorts grant membership. Explicit
false overrides a legacy env member. Missing fields use the migration fallback;
read errors, malformed documents and cold asynchronous misses deny membership.
No network I/O runs on an event loop. Listen awaits its initial bounded read.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass
import logging
import os
from threading import RLock
import time
from typing import Any, Callable

TTL_SECONDS = 60
MAX_USERS = 4096
COLLECTION = 'rollout_cohorts'
# Literal env reads keep the migration fallbacks visible to the flag registry.
COHORT_ENVS = {
    'batch-pipeline': lambda: os.getenv('BATCH_PIPELINE_UID_ALLOWLIST', ''),
    'batch-pipeline-recovery': lambda: os.getenv('BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST', ''),
    'first-summary': lambda: os.getenv('FIRST_SUMMARY_UID_ALLOWLIST', ''),
    'audio-archive': lambda: os.getenv('AUDIO_ARCHIVE_UID_ALLOWLIST', ''),
    'dream-agent': lambda: os.getenv('DREAM_AGENT_UID_ALLOWLIST', ''),
    'speaker-grouping-shadow': lambda: os.getenv('SPEAKER_GROUPING_SHADOW_UID_ALLOWLIST', ''),
    'stt-live-demand': lambda: os.getenv('STT_LIVE_DEMAND_UID_ALLOWLIST', ''),
    'sync-legacy-fresh': lambda: os.getenv('SYNC_LEGACY_FRESH_UID_ALLOWLIST', ''),
    'sync-lineage-resolve': lambda: os.getenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', ''),
    'transcription-final-pass': lambda: os.getenv('TRANSCRIPTION_FINAL_PASS_UID_ALLOWLIST', ''),
    'transcription-shadow': lambda: os.getenv('TRANSCRIPTION_SHADOW_UID_ALLOWLIST', ''),
    'mobile-standard-batch': lambda: os.getenv('MOBILE_STANDARD_BATCH_UIDS', ''),
    'messaging-telegram': lambda: os.getenv('OMI_MESSAGING_CHANNELS_UIDS', ''),
    'messaging-imessage': lambda: os.getenv('OMI_MESSAGING_CHANNELS_UIDS', ''),
}
logger = logging.getLogger(__name__)


def valid_uid(uid: object) -> bool:
    return isinstance(uid, str) and bool(uid) and uid.strip() == uid and '/' not in uid and len(uid.encode()) <= 256


def _read_memberships(uid: str) -> dict[str, bool]:
    # Reuse the lazy customer data plane; SERVICE_ACCOUNT_JSON pins listen/Cloud Run.
    from database._client import data_plane_db as db

    doc = db.collection(COLLECTION).document(uid).get(timeout=1.0, retry=None)
    if not doc.exists:
        return {}
    data = doc.to_dict()
    members = data.get('cohorts') if isinstance(data, dict) else None
    if not isinstance(members, dict) or any(type(value) is not bool for value in members.values()):
        raise ValueError('invalid cohort document')
    return members


@dataclass
class _Entry:
    future: Future
    expires: float = float('inf')


class _TTLReads:
    """Bounded positive/negative/error cache with one in-flight read per key."""

    def __init__(self, reader: Callable[[str], Any], capacity: int = MAX_USERS):
        self.reader = reader
        self.capacity = capacity
        self.entries: OrderedDict[str, _Entry] = OrderedDict()
        self.lock = RLock()

    def _refresh(self, key: str, entry: _Entry) -> None:
        try:
            value = self.reader(key)
        except Exception:
            # SDK exceptions carry document paths and therefore UIDs. Never log them.
            logger.warning('event=rollout_cohort_read outcome=denied')
            value = None
        with self.lock:
            entry.expires = time.monotonic() + TTL_SECONDS
            entry.future.set_result(value)

    def request(self, key: str, *, background: bool) -> Future:
        with self.lock:
            entry = self.entries.get(key)
            if entry is not None and (not entry.future.done() or entry.expires > time.monotonic()):
                self.entries.move_to_end(key)
                return entry.future
            if entry is not None:
                del self.entries[key]
            if len(self.entries) >= self.capacity:
                victim = next((k for k, value in self.entries.items() if value.future.done()), None)
                if victim is None:
                    denied: Future = Future()
                    denied.set_result(None)
                    return denied
                del self.entries[victim]
            entry = _Entry(Future())
            self.entries[key] = entry
        if background:
            from utils.executors import get_rollout_executor

            try:
                get_rollout_executor().submit(self._refresh, key, entry)
            except Exception:
                with self.lock:
                    entry.expires = time.monotonic() + TTL_SECONDS
                    entry.future.set_result(None)
        else:
            self._refresh(key, entry)
        return entry.future

    def get(self, key: str) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            future = self.request(key, background=False)
            try:
                return future.result(timeout=1.25)
            except TimeoutError:
                return None
        future = self.request(key, background=True)
        return future.result() if future.done() else None


_cache = _TTLReads(_read_memberships)


def in_rollout_cohort(
    uid: str, name: str, *, legacy_members: tuple[str, ...] | None = None, legacy_all: bool = False
) -> bool:
    """Warm checks cost zero reads; missing fields retain explicit legacy env members."""
    if not valid_uid(uid) or name not in COHORT_ENVS:
        return False
    members = _cache.get(uid)
    if members is None:
        return False
    if name in members:
        return members[name] is True
    if legacy_members is None:
        legacy_members = tuple(item.strip() for item in COHORT_ENVS[name]().split(',') if item.strip())
    return legacy_all or uid in legacy_members


def load_rollout_cohorts(uid: str) -> None:
    """Preload in a synchronous request dependency (already on a worker thread)."""
    if valid_uid(uid):
        _cache.get(uid)


async def warm_rollout_cohorts(uid: str) -> None:
    """Await the first listen read without blocking the loop or extending SDK retries."""
    if not valid_uid(uid):
        return
    future = _cache.request(uid, background=True)
    try:
        await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), timeout=1.25)
    except asyncio.TimeoutError:
        pass  # The pending cache entry denies admission until its read completes.


def _read_cohort_members(name: str) -> tuple[str, ...]:
    from database._client import data_plane_db as db
    from google.cloud.firestore_v1.base_query import FieldFilter
    from google.cloud.firestore_v1.field_path import FieldPath

    rows = list(
        db.collection(COLLECTION)
        .where(filter=FieldFilter(FieldPath('cohorts', name).to_api_repr(), '==', True))
        .limit(500)
        .stream(timeout=1.0, retry=None)
    )
    if len(rows) >= 500:
        raise ValueError('cohort discovery limit exceeded')
    return tuple(row.id for row in rows if valid_uid(row.id))


_member_cache = _TTLReads(_read_cohort_members, capacity=len(COHORT_ENVS))


def rollout_cohort_members(name: str) -> tuple[str, ...]:
    """Bounded background-job discovery; never query the collection per request."""
    if name not in COHORT_ENVS:
        return ()
    members = _member_cache.get(name)
    if members is None:
        return ()
    legacy = {item.strip() for item in COHORT_ENVS[name]().split(',') if valid_uid(item.strip())}
    return tuple(sorted(set(members) | {uid for uid in legacy if in_rollout_cohort(uid, name)}))
