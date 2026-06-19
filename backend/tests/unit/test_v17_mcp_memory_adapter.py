from datetime import datetime, timedelta, timezone

from config.v17_memory import V17Capabilities, V17Mode
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.v17_product_memory import MemoryItemStatus, MemoryTier, ProcessingState, V17MemoryItem
from utils.memory.short_term_lifecycle import DEFAULT_SHORT_TERM_TTL_DAYS
from utils.mcp_memories import search_v17_default_mcp_memories


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


def _read_capabilities(uid='u1', *, enabled=True):
    return V17Capabilities(
        uid=uid,
        mode=V17Mode.read if enabled else V17Mode.off,
        legacy_only=not enabled,
        shadow_artifacts_enabled=enabled,
        v17_writes_enabled=enabled,
        v17_reads_enabled=enabled,
        legacy_reads_authoritative=not enabled,
    )


def _evidence(source_id='conv1'):
    return MemoryEvidence(
        evidence_id=f'ev-{source_id}',
        source_id=source_id,
        source_type='conversation',
        source_version='v1',
        quote_refs=[{'text': 'User prefers deterministic MCP memory reads.'}],
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
        'processing_state': ProcessingState.pending if tier == MemoryTier.short_term else ProcessingState.processed,
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
    return V17MemoryItem(**data)


def _stored_item(item):
    return item.model_dump(mode='json')


def test_mcp_default_v17_memory_adapter_uses_product_search_when_read_rollout_enabled():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    fresh_short_term = _memory_item('fresh-short-term', now=now, content='coffee fresh short term')
    stale_short_term = _memory_item(
        'stale-short-term', now=now, captured_at=now - timedelta(days=45), content='coffee stale short term'
    )
    long_term = _memory_item('long-term', tier=MemoryTier.long_term, now=now, content='coffee long term')
    archive = _memory_item('archive', tier=MemoryTier.archive, now=now, content='coffee archive memory')
    db_client = _FirestoreFake(
        {
            f'users/u1/memory_items/{item.memory_id}': _stored_item(item)
            for item in [archive, stale_short_term, fresh_short_term, long_term]
        }
    )

    results = search_v17_default_mcp_memories(
        uid='u1',
        query='coffee',
        limit=10,
        db_client=db_client,
        rollout_capabilities=_read_capabilities(),
        now=now,
    )

    assert db_client.collection_paths == ['users/u1/memory_items']
    assert [item['id'] for item in results] == ['fresh-short-term', 'long-term']
    assert [item['content'] for item in results] == ['coffee fresh short term', 'coffee long term']
    assert all(item['category'] == 'other' for item in results)
    assert all(item['v17_default_memory'] is True for item in results)
    assert all(item['archive_default_visible'] is False for item in results)
    assert all(item['policy']['consumer'] == 'mcp' for item in results)
    assert all(item['policy']['archive_capability'] is False for item in results)


def test_mcp_default_v17_memory_adapter_returns_none_when_rollout_or_default_grant_disabled():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    fresh_short_term = _memory_item('fresh-short-term', now=now, content='coffee fresh short term')
    db_client = _FirestoreFake({f'users/u1/memory_items/{fresh_short_term.memory_id}': _stored_item(fresh_short_term)})

    assert (
        search_v17_default_mcp_memories(
            uid='u1',
            query='coffee',
            limit=10,
            db_client=db_client,
            rollout_capabilities=_read_capabilities(enabled=False),
            now=now,
        )
        is None
    )
    assert (
        search_v17_default_mcp_memories(
            uid='u1',
            query='coffee',
            limit=10,
            db_client=db_client,
            rollout_capabilities=_read_capabilities(),
            app_has_default_memory_grant=False,
            now=now,
        )
        is None
    )
    assert db_client.collection_paths == []
