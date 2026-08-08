from datetime import datetime, timedelta, timezone

import pytest

from database import document_store
from tests.store_fakes import FakeDocumentStore
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import (
    MemoryAccessPolicy,
    MemoryItemStatus,
    MemoryTier,
    ProcessingState,
    MemoryItem,
)
from utils.memory.short_term_lifecycle import DEFAULT_SHORT_TERM_TTL_DAYS
from utils.memory import product_memory_read_service
from utils.memory.product_memory_read_service import (
    fetch_authoritative_product_memory_items_for_source,
    fetch_authoritative_superseded_memory_items_for_targets,
    fetch_archive_product_memory_search,
    fetch_default_product_memory_search,
)


class _Snapshot:
    def __init__(self, data=None):
        self._data = data

    def to_dict(self):
        return dict(self._data or {})


class _CollectionRef:
    def __init__(self, db_client, path):
        self._db_client = db_client
        self.path = path

    def stream(self):
        prefix = f'{self.path}/'
        snapshots = []
        for path, data in sorted(self._db_client.docs.items()):
            if not path.startswith(prefix) or '/' in path[len(prefix) :]:
                continue
            snapshots.append(_Snapshot(data))
        return snapshots


class _FirestoreFake:
    def __init__(self, docs=None):
        self.docs = docs or {}
        self.collection_paths = []

    def collection(self, path):
        self.collection_paths.append(path)
        return _CollectionRef(self, path)


def _evidence(source_id='conv1'):
    return MemoryEvidence(
        evidence_id=f'ev-{source_id}',
        source_id=source_id,
        source_type='conversation',
        source_version='v1',
        quote_refs=[{'text': 'User prefers concise product memory reads.'}],
        content_hash='hash1',
        source_state=SourceState.active,
        artifact_preservation=ArtifactPreservationState.preserved,
    )


def _memory_item(memory_id: str, *, tier=MemoryTier.short_term, now=None, captured_at=None, content=None, **overrides):
    now = now or datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    captured_at = captured_at or (now - timedelta(days=1))
    data = {
        'memory_id': memory_id,
        'uid': 'u1',
        'version': 1,
        'tier': tier,
        'status': MemoryItemStatus.active,
        'processing_state': ProcessingState.processed,
        'content': content or f'{memory_id} coffee preference',
        'evidence': [_evidence(f'{memory_id}-source')],
        'source_state': SourceState.active,
        'sensitivity_labels': [],
        'visibility': 'private',
        'user_asserted': False,
        'captured_at': captured_at,
        'updated_at': captured_at,
        'expires_at': (
            captured_at + timedelta(days=DEFAULT_SHORT_TERM_TTL_DAYS) if tier == MemoryTier.short_term else None
        ),
        'ledger_commit_id': 'commit-1' if tier == MemoryTier.long_term else None,
        'ledger_sequence': 1 if tier == MemoryTier.long_term else None,
    }
    data.update(overrides)
    return MemoryItem(**data)


def _stored_item(item):
    return item.model_dump(mode='json')


def test_fetch_default_product_memory_search_reads_authoritative_items_and_filters_default_visibility(monkeypatch):
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    fresh_short_term = _memory_item('fresh-short-term', now=now, content='coffee fresh short term')
    stale_short_term = _memory_item(
        'stale-short-term', now=now, captured_at=now - timedelta(days=45), content='coffee stale short term'
    )
    long_term = _memory_item('long-term', tier=MemoryTier.long_term, now=now, content='coffee long term')
    archive = _memory_item('archive', tier=MemoryTier.archive, now=now, content='coffee archived memory')
    db_client = _FirestoreFake(
        {
            f'users/u1/memory_items/{stale_short_term.memory_id}': _stored_item(stale_short_term),
            f'users/u1/memory_items/{archive.memory_id}': _stored_item(archive),
            f'users/u1/memory_items/{fresh_short_term.memory_id}': _stored_item(fresh_short_term),
            f'users/u1/memory_items/{long_term.memory_id}': _stored_item(long_term),
        }
    )
    monkeypatch.setattr(document_store, '_store', lambda: FakeDocumentStore(backing=db_client.docs))

    response = fetch_default_product_memory_search(
        uid='u1',
        query='coffee',
        policy=MemoryAccessPolicy.for_omi_chat(),
        now=now,
    )

    assert [item['memory_id'] for item in response['items']] == ['fresh-short-term', 'long-term']
    assert response['total_count'] == 2
    assert response['returned_count'] == 2
    assert response['offset'] == 0
    assert response['limit'] == 100
    assert response['archive_default_visible'] is False
    assert response['items'][0]['tier'] == 'short_term'
    assert response['items'][1]['tier'] == 'long_term'


def test_fetch_default_product_memory_search_collapses_alias_before_pagination(monkeypatch):
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    survivor = _memory_item(
        'canonical-survivor',
        tier=MemoryTier.long_term,
        now=now,
        content='Project Beacon uses weekly planning',
        canonical_memory_id='canonical-survivor',
        captured_at=now - timedelta(days=3),
        updated_at=now - timedelta(days=2),
    )
    alias = _memory_item(
        'duplicate-short-term',
        now=now,
        content='Fresh duplicate: Project Beacon uses weekly planning',
        canonical_memory_id=survivor.memory_id,
        updated_at=now - timedelta(hours=1),
    )
    db_client = _FirestoreFake(
        {f'users/u1/memory_items/{item.memory_id}': _stored_item(item) for item in [alias, survivor]}
    )
    monkeypatch.setattr(document_store, '_store', lambda: FakeDocumentStore(backing=db_client.docs))

    response = fetch_default_product_memory_search(
        uid='u1',
        query='Project Beacon',
        policy=MemoryAccessPolicy.for_omi_chat(),
        now=now,
        limit=1,
    )

    assert [item['memory_id'] for item in response['items']] == [survivor.memory_id]
    assert response['total_count'] == 1
    assert response['returned_count'] == 1


def test_fetch_default_product_memory_search_excludes_pending_short_term_text(monkeypatch):
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    pending = _memory_item(
        'pending-explicit',
        now=now,
        content='coffee pending explicit memory',
        processing_state=ProcessingState.pending,
    )
    db_client = _FirestoreFake({f'users/u1/memory_items/{pending.memory_id}': _stored_item(pending)})
    monkeypatch.setattr(document_store, '_store', lambda: FakeDocumentStore(backing=db_client.docs))

    response = fetch_default_product_memory_search(
        uid='u1',
        query='coffee',
        policy=MemoryAccessPolicy.for_omi_chat(),
        now=now,
    )

    assert response['items'] == []
    assert response['total_count'] == 0


def test_fetch_default_product_memory_search_paginates_after_filtering_with_deterministic_order(monkeypatch):
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    first = _memory_item('a-fresh', now=now, updated_at=now - timedelta(minutes=1), content='coffee alpha')
    stale = _memory_item(
        'z-stale', now=now, captured_at=now - timedelta(days=45), updated_at=now, content='coffee stale newest'
    )
    second = _memory_item(
        'b-long', tier=MemoryTier.long_term, now=now, updated_at=now - timedelta(minutes=2), content='coffee beta'
    )
    third = _memory_item(
        'c-long', tier=MemoryTier.long_term, now=now, updated_at=now - timedelta(minutes=3), content='coffee gamma'
    )
    db_client = _FirestoreFake(
        {f'users/u1/memory_items/{item.memory_id}': _stored_item(item) for item in [third, stale, second, first]}
    )
    monkeypatch.setattr(document_store, '_store', lambda: FakeDocumentStore(backing=db_client.docs))

    response = fetch_default_product_memory_search(
        uid='u1',
        query='coffee',
        policy=MemoryAccessPolicy.for_omi_chat(),
        now=now,
        limit=2,
        offset=1,
    )

    assert [item['memory_id'] for item in response['items']] == ['b-long', 'c-long']
    assert response['total_count'] == 3
    assert response['returned_count'] == 2
    assert response['offset'] == 1
    assert response['limit'] == 2


def test_fetch_default_product_memory_search_rejects_uid_mismatches(monkeypatch):
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    item = _memory_item('wrong-uid', now=now, uid='other-user')
    db_client = _FirestoreFake({f'users/u1/memory_items/{item.memory_id}': _stored_item(item)})
    monkeypatch.setattr(document_store, '_store', lambda: FakeDocumentStore(backing=db_client.docs))

    with pytest.raises(ValueError, match='memory item uid mismatch'):
        fetch_default_product_memory_search(
            uid='u1',
            query='coffee',
            policy=MemoryAccessPolicy.for_omi_chat(),
            now=now,
        )


def test_fetch_archive_product_memory_search_requires_archive_capability_and_keeps_default_separate(monkeypatch):
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    fresh_short_term = _memory_item('fresh-short-term', now=now, content='coffee fresh short term')
    long_term = _memory_item('long-term', tier=MemoryTier.long_term, now=now, content='coffee long term')
    archive = _memory_item('archive', tier=MemoryTier.archive, now=now, content='coffee archived memory')
    db_client = _FirestoreFake(
        {
            f'users/u1/memory_items/{item.memory_id}': _stored_item(item)
            for item in [archive, fresh_short_term, long_term]
        }
    )
    monkeypatch.setattr(document_store, '_store', lambda: FakeDocumentStore(backing=db_client.docs))

    denied = fetch_archive_product_memory_search(
        uid='u1',
        query='coffee',
        policy=MemoryAccessPolicy.for_omi_chat(archive_capability=False),
        now=now,
    )
    allowed = fetch_archive_product_memory_search(
        uid='u1',
        query='coffee',
        policy=MemoryAccessPolicy.for_omi_chat(archive_capability=True),
        now=now,
    )
    default = fetch_default_product_memory_search(
        uid='u1',
        query='coffee',
        policy=MemoryAccessPolicy.for_omi_chat(),
        now=now,
    )

    assert denied['archive_capability_required'] is True
    assert denied['archive_capability_granted'] is False
    assert denied['items'] == []
    assert allowed['archive_capability_required'] is True
    assert allowed['archive_capability_granted'] is True
    assert [item['memory_id'] for item in allowed['items']] == ['archive']
    assert allowed['total_count'] == 1
    assert allowed['archive_default_visible'] is False
    assert [item['memory_id'] for item in default['items']] == ['fresh-short-term', 'long-term']


class _PagingRecorderStore(FakeDocumentStore):
    """FakeDocumentStore that records the (limit, offset) of each ``query`` page.

    After the WP2/ADR-0028 migration the source-replacement reads page through the neutral
    storage port's ``query(collection, filters=..., limit=..., offset=...)`` (offset-bounded
    pages in document-name order) instead of the retired raw-Firestore cursor API
    (``order_by('__name__')`` + ``start_after``). Recording the per-page limits/offsets keeps
    the original "reads the cohort in bounded pages" intent as a behavioral assertion on the
    seam the source actually uses.
    """

    def __init__(self, *, backing, page_limits, page_offsets):
        super().__init__(backing=backing)
        self._page_limits = page_limits
        self._page_offsets = page_offsets

    def query(self, collection, **kwargs):
        self._page_limits.append(kwargs.get('limit'))
        self._page_offsets.append(kwargs.get('offset'))
        return super().query(collection, **kwargs)


def _patch_read_service_store(monkeypatch, docs):
    """Route the read service's paging seam to a recorder over ``docs``; return trackers.

    The paging helpers hydrate through the module-local ``_store()`` seam (``get_document_store()``),
    not ``document_store._store``, so patch that; returns ``(page_limits, page_offsets)`` collected
    across the whole call.
    """
    page_limits: list = []
    page_offsets: list = []
    monkeypatch.setattr(
        product_memory_read_service,
        '_store',
        lambda: _PagingRecorderStore(backing=docs, page_limits=page_limits, page_offsets=page_offsets),
    )
    return page_limits, page_offsets


def _seed_items(items):
    return {f'users/u1/memory_items/{item.memory_id}': _stored_item(item) for item in items}


def test_memory_item_computes_source_ids_from_current_evidence_without_stale_mutable_state():
    item = _memory_item('source-projection')

    assert item.source_ids == ['source-projection-source']
    item.evidence.append(_evidence('second-source'))
    item.arguments = {'preference': 'concise'}
    assert item.source_ids == ['second-source', 'source-projection-source']
    assert item.model_dump(mode='json')['source_ids'] == item.source_ids


def test_source_replacement_reads_only_the_indexed_source_cohort_in_bounded_pages(monkeypatch):
    source_items = [_memory_item(f'source-{index}', evidence=[_evidence('conversation-a')]) for index in range(3)]
    unrelated_items = [
        _memory_item(f'unrelated-{index}', evidence=[_evidence(f'conversation-{index}')]) for index in range(200)
    ]
    docs = _seed_items([*source_items, *unrelated_items])
    page_limits, page_offsets = _patch_read_service_store(monkeypatch, docs)

    items = fetch_authoritative_product_memory_items_for_source(
        'u1',
        'conversation-a',
        page_size=2,
    )

    # Only the indexed ``source_ids array_contains 'conversation-a'`` cohort is read back, never the
    # 200 unrelated rows — the storage-port filter scopes the scan the way the Firestore index did.
    assert [item.memory_id for item in items] == ['source-0', 'source-1', 'source-2']
    # Three matching rows drained in size-2 pages: (limit=2, offset=0) then (limit=2, offset=2).
    assert page_limits == [2, 2]
    assert page_offsets == [0, 2]


def test_source_replacement_discovers_canonical_and_legacy_supersession_edges(monkeypatch):
    target = 'source-survivor'
    canonical_alias = _memory_item(
        'canonical-alias',
        status=MemoryItemStatus.superseded,
        canonical_memory_id=target,
        superseded_by=target,
    )
    legacy_alias = _memory_item(
        'legacy-alias',
        status=MemoryItemStatus.superseded,
        canonical_memory_id=None,
        superseded_by=target,
    )
    unrelated = _memory_item(
        'unrelated-alias',
        status=MemoryItemStatus.superseded,
        canonical_memory_id='other-target',
        superseded_by='other-target',
    )
    docs = _seed_items([canonical_alias, legacy_alias, unrelated])
    page_limits, _page_offsets = _patch_read_service_store(monkeypatch, docs)

    items = fetch_authoritative_superseded_memory_items_for_targets(
        'u1',
        [target],
        page_size=2,
    )

    assert [item.memory_id for item in items] == ['canonical-alias', 'legacy-alias']
    assert all(limit == 2 for limit in page_limits)
