"""Refresh stored recap learning references without reviving retired memories.

A recap is a snapshot, not memory authority. Resolve explicit successor links
before rendering controls, and show the successor's text along with its id.
Source replacement receipts can resolve several old rows to one replacement;
a set of several newly extracted facts is not a per-fact successor.
"""

import logging
import os
import time
from concurrent.futures import FIRST_COMPLETED, Future, wait
from dataclasses import dataclass, field
from typing import Any, TypeGuard

from fastapi import HTTPException
from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client
from database.memory_collections import MemoryCollections
from models.daily_summary import DailySummaryResponse
from models.daily_summary_payload import LearnedMemoryRef
from models.memories import MemoryDB
from models.product_memory import MemoryItem
from utils.executors import db_executor
from utils.memory.canonical_memory_adapter import memory_item_to_memorydb
from utils.memory.memory_service import MemoryService
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

MAX_SUCCESSOR_HOPS = 12
MAX_RESPONSE_READ_SECONDS = 5
MAX_CONCURRENT_RESOLUTIONS = 4
SUCCESSOR_FIELDS = (
    'canonical_memory_id',
    'superseded_by',
    'merged_into',
    'replaced_by',
    'replacement_memory_id',
)
_METADATA_FIELDS = ('uid', 'memory_id', 'id', 'status', 'source_state', *SUCCESSOR_FIELDS)


def _valid_id(value: Any) -> TypeGuard[str]:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip() and '/' not in value


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('Recap learning reference read budget exhausted')
    return remaining


def _source_successor(
    uid: str, memory_id: str, *, client: Any, deadline: float | None = None
) -> tuple[str | None, bool]:
    """Return a unique committed replacement and positive retirement evidence."""
    deadline = deadline if deadline is not None else time.monotonic() + MAX_RESPONSE_READ_SECONDS
    collection = client.collection('users').document(uid).collection('memory_source_replacements')
    rows = list(
        collection.where(filter=FieldFilter('retracted_memory_ids', 'array_contains', memory_id))
        .limit(2)
        .stream(timeout=_remaining(deadline), retry=None)
    )
    if len(rows) != 1:
        return None, False
    receipt = rows[0].to_dict() or {}
    retracted = receipt.get('retracted_memory_ids')
    if receipt.get('uid') != uid or not isinstance(retracted, list) or memory_id not in retracted:
        return None, False
    targets = receipt.get('committed_memory_ids')
    if not isinstance(targets, list):
        return None, False
    if len(targets) != 1 or not _valid_id(targets[0]):
        return None, True
    return targets[0], True


@dataclass(frozen=True)
class _CanonicalBatch:
    client: Any
    rows: dict[str, Any] = field(default_factory=dict)
    direct: dict[str, MemoryDB | None] = field(default_factory=dict)


def _canonical_batch(uid: str, memory_ids: list[str], client: Any, deadline: float) -> _CanonicalBatch:
    """One direct-live read round, independent of page size (at most 300 ids).

    Keep payloads local to the read workers; no worker receives recap objects.
    Firestore get_all is unordered, so snapshot identity is mandatory.
    """
    _remaining(deadline)
    client = client if client is not None else get_firestore_client()
    root = MemoryCollections(uid=uid).memory_items
    refs = [client.document(f'{root}/{mid}') for mid in memory_ids if _valid_id(mid)]
    if not refs:
        return _CanonicalBatch(client)
    rows = {}
    direct = {}
    for snapshot in client.get_all(refs, timeout=_remaining(deadline), retry=None):
        _remaining(deadline)
        mid = snapshot.id
        if mid not in memory_ids:
            raise ValueError('Unexpected canonical document identity')
        raw = snapshot.to_dict() if snapshot.exists else None
        rows[mid] = raw
        if (
            raw
            and raw.get('status') == 'active'
            and not any(raw.get(key) and raw[key] != mid for key in SUCCESSOR_FIELDS)
        ):
            try:
                direct[mid] = _project_active(uid, mid, raw)
            except Exception:
                # Bad payload/identity is unresolved, never deletion evidence.
                pass
    return _CanonicalBatch(client, rows, direct)


def _project_active(uid: str, mid: str, raw: dict[str, Any]) -> MemoryDB | None:
    # Same validation/projection as MemoryService.fetch's canonical branch.
    item = MemoryItem.model_validate(raw)
    if item.uid != uid or item.memory_id != mid:
        raise ValueError('Unverified canonical identity')
    return _reviewable(memory_item_to_memorydb(item), uid, mid, raw)


def _reviewable(memory: MemoryDB, uid: str, mid: str, raw: dict[str, Any] | None) -> MemoryDB | None:
    if memory.uid != uid or memory.id != mid:
        raise ValueError('Unverified hydrated identity')
    if (
        memory.invalid_at is not None
        or memory.user_review is False
        or (raw and raw.get('source_state') in {'tombstoned', 'purged'})
    ):
        return None
    if memory.is_locked or memory.superseded_by or not memory.content.strip():
        raise ValueError('Unverified live feedback target')
    return memory


class _Resolver:
    def __init__(self, uid: str, client: Any, canonical: dict[str, Any], deadline: float) -> None:
        self.uid = uid
        self.client = client
        self.canonical = canonical
        self.deadline = deadline

    def resolve(self, memory_id: str) -> MemoryDB | None:
        seen: set[str] = set()
        current = memory_id
        retired = False
        for _ in range(MAX_SUCCESSOR_HOPS):
            _remaining(self.deadline)
            if not _valid_id(current):
                raise ValueError('Unverified memory identity')
            if current in seen:
                if retired:
                    return None
                raise ValueError('Unverified successor cycle')
            seen.add(current)
            collections = MemoryCollections(uid=self.uid)
            raw = None
            canonical = False
            historical = False
            for collection in (
                collections.memory_items,
                f'{collections.user_root}/memories',
                collections.memory_historical_overrides,
            ):
                if collection == collections.memory_items and current in self.canonical:
                    raw = self.canonical[current]
                else:
                    snapshot = self.client.document(f'{collection}/{current}').get(
                        field_paths=None if collection == collections.memory_items else _METADATA_FIELDS,
                        timeout=_remaining(self.deadline),
                        retry=None,
                    )
                    raw = snapshot.to_dict() if snapshot.exists else None
                if raw is not None:
                    # Legacy documents may omit uid/id; canonical rows may not.
                    if raw.get('uid', self.uid) != self.uid or raw.get('memory_id', raw.get('id', current)) != current:
                        raise ValueError('Unverified memory identity')
                    canonical = collection == collections.memory_items
                    historical = collection == f'{collections.user_root}/memories'
                    if canonical and (raw.get('uid') != self.uid or raw.get('memory_id') != current):
                        raise ValueError('Unverified canonical identity')
                    retired = retired or raw.get('status') in {'superseded', 'hidden', 'tombstoned'}
                    break
            targets: set[str] = set()
            for key in SUCCESSOR_FIELDS:
                target = raw.get(key) if raw else None
                if target:
                    if not _valid_id(target):
                        raise ValueError('Unverified successor identity')
                    if target != current:
                        targets.add(target)
            if len(targets) > 1:
                if retired:
                    return None
                raise ValueError('Ambiguous live identity')
            if targets:
                current = targets.pop()
                continue
            result = None
            try:
                if canonical and raw and raw.get('status') == 'active':
                    # Exactly the active-row validation/projection used by
                    # MemoryService.fetch, without repeating its point read.
                    return _project_active(self.uid, current, raw)
                elif historical:
                    # Still use universal suppression/decryption/lock authority.
                    # The coordinator deadline also bounds this unbudgeted fetch.
                    _remaining(self.deadline)
                    result = MemoryService(db_client=self.client).fetch(self.uid, current)
            except HTTPException as exc:
                if exc.status_code not in {402, 404}:
                    raise
                # Missing/locked is not proof of retirement. Preserve the card
                # unless metadata or a committed receipt positively retires it.
            _remaining(self.deadline)
            if result is None:
                successor, source_retired = _source_successor(
                    self.uid, current, client=self.client, deadline=self.deadline
                )
                retired = retired or source_retired
                if successor is not None:
                    current = successor
                    continue
            if result is not None:
                return _reviewable(result, self.uid, current, raw)
            if retired:
                return None
            raise ValueError('No retirement evidence')
        # A hop cap is resolution exhaustion, never proof of no live successor.
        raise TimeoutError('Recap learning reference hop budget exhausted')


def _resolve_one(uid: str, mid: str, client: Any, canonical: dict[str, Any], deadline: float) -> MemoryDB | None:
    # Leaf read only. Each worker owns its resolver; late completion can neither
    # write storage nor mutate the response or the coordinator's result map.
    return _Resolver(uid, client, canonical, deadline).resolve(mid)


def _read_results(uid: str, memory_ids: list[str], client: Any, deadline: float) -> dict[str, MemoryDB | None]:
    results: dict[str, MemoryDB | None] = {}
    pending: dict[Future, str] = {}
    batch = None
    try:
        batch = db_executor.submit(_canonical_batch, uid, memory_ids, client, deadline)
        read = batch.result(timeout=_remaining(deadline))
        client, canonical = read.client, read.rows
        results.update(read.direct)
        remaining = iter(mid for mid in memory_ids if mid not in results)
        while True:
            while len(pending) < MAX_CONCURRENT_RESOLUTIONS:
                mid = next(remaining, None)
                if mid is None:
                    break
                _remaining(deadline)
                future = db_executor.submit(_resolve_one, uid, mid, client, canonical, deadline)
                pending[future] = mid
            if not pending:
                break
            done, _ = wait(pending, timeout=_remaining(deadline), return_when=FIRST_COMPLETED)
            if not done:
                break
            for future in done:
                mid = pending.pop(future)
                try:
                    results[mid] = future.result()
                except Exception:
                    # Leave only this reference unresolved, preserving its snapshot.
                    pass
    except Exception:
        # A batch failure or the single wall deadline preserves unfinished refs.
        pass
    finally:
        if batch is not None:
            batch.cancel()
        for future in pending:
            future.cancel()
    return results


def refresh_recap_learning_refs(
    uid: str, summaries: list[DailySummaryResponse], *, firestore_client: Any = None
) -> list[DailySummaryResponse]:
    """Read-only response projection shared by recap list, search and detail.

    The kill switch is on by default. No collection-wide memory scan, write,
    materialization, or model call is made. Memoization lasts one response only.
    """
    if os.getenv('DAILY_RECAP_LEARNING_REFS_ENABLED', 'true').lower() in {'false', '0', 'off'}:
        return summaries
    if not any(summary.memories_learned for summary in summaries):
        return summaries
    deadline = time.monotonic() + MAX_RESPONSE_READ_SECONDS
    memory_ids = list(dict.fromkeys(ref.memory_id for summary in summaries for ref in summary.memories_learned[:3]))
    results = _read_results(uid, memory_ids, firestore_client, deadline)
    refreshed = []
    for summary in summaries:
        items: list[LearnedMemoryRef] = []
        used: set[str] = set()
        for ref in summary.memories_learned[:3]:
            if ref.memory_id not in results:
                items.append(ref)
                continue
            memory = results[ref.memory_id]
            if memory is None or memory.id in used:
                continue
            used.add(memory.id)
            items.append(
                LearnedMemoryRef(
                    memory_id=memory.id,
                    content=memory.content,
                    category=memory.category.value,
                    captured_at=memory.created_at,
                )
            )
        items.extend(summary.memories_learned[3:])
        # Stored counts may contain more than the displayed cards. Only verified
        # omissions and duplicate targets change them; unresolved cards have zero delta.
        delta = len(items) - len(summary.memories_learned)
        updates: dict[str, Any] = {'memories_learned': items}
        stored_count = (summary.model_extra or {}).get('memories_learned_count')
        if delta and isinstance(stored_count, int):
            updates['memories_learned_count'] = max(0, stored_count + delta)
        updated = summary.model_copy(update=updates)
        if delta and updated.stats is not None and updated.stats.memories_learned_count is not None:
            updated.stats = updated.stats.model_copy(
                update={'memories_learned_count': max(0, updated.stats.memories_learned_count + delta)}
            )
        refreshed.append(updated)
    if len(results) < len(memory_ids):
        record_fallback(
            component='daily_summary',
            from_mode='stored_learning_refs',
            to_mode='verified_learning_refs',
            reason='other',
            outcome='degraded',
            log=logger,
        )
    return refreshed
