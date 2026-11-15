"""Refresh stored recap learning references without reviving retired memories.

A recap is a snapshot, not memory authority. Resolve explicit successor links
before rendering controls, and show the successor's text along with its id.
Source replacement receipts can resolve several old rows to one replacement;
a set of several newly extracted facts is not a per-fact successor.
"""

import logging
import os
import time
from typing import Any, TypeGuard

from fastapi import HTTPException
from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client
from database.memory_collections import MemoryCollections
from models.daily_summary import DailySummaryResponse
from models.daily_summary_payload import LearnedMemoryRef
from models.memories import MemoryDB
from utils.memory.memory_service import MemoryService
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

MAX_SUCCESSOR_HOPS = 12
MAX_RESPONSE_READ_SECONDS = 5
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


def _source_successor(uid: str, memory_id: str, *, client: Any) -> str | None:
    """A unique committed replacement, never an arbitrary member of a set."""
    collection = client.collection('users').document(uid).collection('memory_source_replacements')
    rows = list(
        collection.where(filter=FieldFilter('retracted_memory_ids', 'array_contains', memory_id))
        .limit(2)
        .stream(timeout=3, retry=None)
    )
    if len(rows) != 1:
        return None
    receipt = rows[0].to_dict() or {}
    retracted = receipt.get('retracted_memory_ids')
    if receipt.get('uid') != uid or not isinstance(retracted, list) or memory_id not in retracted:
        return None
    targets = receipt.get('committed_memory_ids')
    if not isinstance(targets, list) or len(targets) != 1 or not _valid_id(targets[0]):
        return None
    return targets[0]


class _Resolver:
    def __init__(self, uid: str, client: Any) -> None:
        self.uid = uid
        self.client = client
        self.service = MemoryService(db_client=client)
        self.cache: dict[str, MemoryDB | None] = {}
        self.deadline = time.monotonic() + MAX_RESPONSE_READ_SECONDS

    def resolve(self, memory_id: str) -> MemoryDB | None:
        seen: set[str] = set()
        current = memory_id
        for _ in range(MAX_SUCCESSOR_HOPS):
            if time.monotonic() >= self.deadline:
                raise TimeoutError('Recap learning reference read budget exhausted')
            if not _valid_id(current) or current in seen:
                return None
            seen.add(current)
            if current in self.cache:
                result = self.cache[current]
                break
            collections = MemoryCollections(uid=self.uid)
            raw = None
            canonical = False
            historical = False
            for collection in (
                collections.memory_items,
                f'{collections.user_root}/memories',
                collections.memory_historical_overrides,
            ):
                snapshot = self.client.document(f'{collection}/{current}').get(
                    field_paths=_METADATA_FIELDS,
                    timeout=3,
                    retry=None,
                )
                if snapshot.exists:
                    raw = snapshot.to_dict() or {}
                    # Legacy documents may omit uid/id; canonical rows may not.
                    if raw.get('uid', self.uid) != self.uid or raw.get('memory_id', raw.get('id', current)) != current:
                        return None
                    if collection == collections.memory_items and (
                        raw.get('uid') != self.uid or raw.get('memory_id') != current
                    ):
                        return None
                    canonical = collection == collections.memory_items
                    historical = collection == f'{collections.user_root}/memories'
                    break
            targets: set[str] = set()
            for key in SUCCESSOR_FIELDS:
                target = raw.get(key) if raw else None
                if target:
                    if not _valid_id(target):
                        return None
                    if target != current:
                        targets.add(target)
            if len(targets) > 1:
                return None
            if targets:
                current = targets.pop()
                continue
            try:
                if (canonical and raw and raw.get('status') == 'active') or historical:
                    # Metadata only locates a target. The universal authority
                    # still owns hydration, decryption, locks and suppression.
                    result = self.service.fetch(self.uid, current)
                else:
                    result = None
            except HTTPException as exc:
                if exc.status_code == 404:
                    result = None
                elif exc.status_code == 402:
                    return None
                else:
                    raise
            if result is None:
                successor = _source_successor(self.uid, current, client=self.client)
                if successor is not None:
                    current = successor
                    continue
            if result is not None and (
                result.uid != self.uid
                or result.id != current
                or result.is_locked
                or result.user_review is False
                or result.invalid_at is not None
                or result.superseded_by
                or (raw and raw.get('source_state') in {'tombstoned', 'purged'})
                or not result.content.strip()
            ):
                result = None
            break
        else:
            # The hop bound proves nothing about intermediate identities. Do
            # not poison a later card whose shorter chain fits the same bound.
            return None
        for visited in seen:
            self.cache[visited] = result
        return result


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
    resolver = _Resolver(uid, firestore_client if firestore_client is not None else get_firestore_client())
    refreshed = []
    unavailable = False
    for summary in summaries:
        items: list[LearnedMemoryRef] = []
        used: set[str] = set()
        for ref in summary.memories_learned[:3]:
            if unavailable:
                # One provider failure ends this response's reads; do not spend
                # another timeout for every card on a 100-recap list page.
                continue
            try:
                memory = resolver.resolve(ref.memory_id)
            except Exception:
                # A provider outage is not deletion evidence. Omit controls for
                # this response only and report degradation without private data.
                unavailable = True
                continue
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
        updates: dict[str, Any] = {'memories_learned': items}
        if 'memories_learned_count' in summary.model_fields_set:
            updates['memories_learned_count'] = len(items)
        updated = summary.model_copy(update=updates)
        if updated.stats is not None and updated.stats.memories_learned_count is not None:
            updated.stats = updated.stats.model_copy(update={'memories_learned_count': len(items)})
        refreshed.append(updated)
    if unavailable:
        record_fallback(
            component='daily_summary',
            from_mode='stored_learning_refs',
            to_mode='verified_learning_refs',
            reason='other',
            outcome='degraded',
            log=logger,
        )
    return refreshed
