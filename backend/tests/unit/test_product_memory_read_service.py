from datetime import datetime, timedelta, timezone

import pytest

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import (
    MemoryAccessPolicy,
    MemoryItemStatus,
    MemoryTier,
    ProcessingState,
    MemoryItem,
)
from utils.memory.short_term_lifecycle import DEFAULT_SHORT_TERM_TTL_DAYS
from utils.memory.product_memory_read_service import (
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


def test_fetch_default_product_memory_search_reads_authoritative_items_and_filters_default_visibility():
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

    response = fetch_default_product_memory_search(
        uid='u1',
        query='coffee',
        policy=MemoryAccessPolicy.for_omi_chat(),
        now=now,
        db_client=db_client,
    )

    assert db_client.collection_paths == ['users/u1/memory_items']
    assert [item['memory_id'] for item in response['items']] == ['fresh-short-term', 'long-term']
    assert response['total_count'] == 2
    assert response['returned_count'] == 2
    assert response['offset'] == 0
    assert response['limit'] == 100
    assert response['archive_default_visible'] is False
    assert response['items'][0]['tier'] == 'short_term'
    assert response['items'][1]['tier'] == 'long_term'


def test_fetch_default_product_memory_search_excludes_pending_short_term_text():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    pending = _memory_item(
        'pending-explicit',
        now=now,
        content='coffee pending explicit memory',
        processing_state=ProcessingState.pending,
    )
    db_client = _FirestoreFake({f'users/u1/memory_items/{pending.memory_id}': _stored_item(pending)})

    response = fetch_default_product_memory_search(
        uid='u1',
        query='coffee',
        policy=MemoryAccessPolicy.for_omi_chat(),
        now=now,
        db_client=db_client,
    )

    assert response['items'] == []
    assert response['total_count'] == 0


def test_fetch_default_product_memory_search_paginates_after_filtering_with_deterministic_order():
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

    response = fetch_default_product_memory_search(
        uid='u1',
        query='coffee',
        policy=MemoryAccessPolicy.for_omi_chat(),
        now=now,
        db_client=db_client,
        limit=2,
        offset=1,
    )

    assert [item['memory_id'] for item in response['items']] == ['b-long', 'c-long']
    assert response['total_count'] == 3
    assert response['returned_count'] == 2
    assert response['offset'] == 1
    assert response['limit'] == 2


def test_fetch_default_product_memory_search_rejects_uid_mismatches():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    item = _memory_item('wrong-uid', now=now, uid='other-user')
    db_client = _FirestoreFake({f'users/u1/memory_items/{item.memory_id}': _stored_item(item)})

    with pytest.raises(ValueError, match='memory item uid mismatch'):
        fetch_default_product_memory_search(
            uid='u1',
            query='coffee',
            policy=MemoryAccessPolicy.for_omi_chat(),
            now=now,
            db_client=db_client,
        )


def test_fetch_archive_product_memory_search_requires_archive_capability_and_keeps_default_separate():
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

    denied = fetch_archive_product_memory_search(
        uid='u1',
        query='coffee',
        policy=MemoryAccessPolicy.for_omi_chat(archive_capability=False),
        now=now,
        db_client=db_client,
    )
    allowed = fetch_archive_product_memory_search(
        uid='u1',
        query='coffee',
        policy=MemoryAccessPolicy.for_omi_chat(archive_capability=True),
        now=now,
        db_client=db_client,
    )
    default = fetch_default_product_memory_search(
        uid='u1',
        query='coffee',
        policy=MemoryAccessPolicy.for_omi_chat(),
        now=now,
        db_client=db_client,
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
