import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import routers.memory_platform as memory_platform
from models.memories import Memory, MemoryCategory
from utils.memory.memory_system import MemorySystem


def _request(headers=None):
    return SimpleNamespace(headers=headers or {})


class _JsonRequest:
    """Request double whose `json()` returns a canned raw payload."""

    def __init__(self, payload):
        self.headers = {}
        self._payload = payload

    async def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


@pytest.fixture(autouse=True)
def _hermetic_firestore_client(monkeypatch):
    """Resolve Firestore through the supported getter without building a real client."""
    monkeypatch.setattr(memory_platform.db_client_module, 'get_firestore_client', lambda: object())


def _authorization():
    policy = SimpleNamespace(
        consumer=SimpleNamespace(value='omi_chat'),
        app_has_default_memory_grant=True,
        archive_capability=False,
        raw_provenance_capability=False,
    )
    gate = SimpleNamespace(
        source_path='memory_control/global_read_gate',
        read_decision=SimpleNamespace(value='USE_MEMORY'),
        fallback_reason=None,
        reason='enabled',
    )
    return SimpleNamespace(policy=policy, global_gate=gate, observability={'surface': 'platform_search'})


def test_platform_search_is_bounded_and_uses_canonical_product_reader(monkeypatch):
    calls = []
    firestore_client = object()

    monkeypatch.setattr(memory_platform.db_client_module, 'get_firestore_client', lambda: firestore_client)
    monkeypatch.setattr(
        memory_platform, '_require_product_authorization', lambda uid, *, firestore_client: _authorization()
    )

    def fake_search(**kwargs):
        calls.append(kwargs)
        return {
            'uid': kwargs['uid'],
            'query': kwargs['query'],
            'items': [],
            'total_count': 0,
            'returned_count': 0,
            'limit': kwargs['limit'],
            'offset': kwargs['offset'],
        }

    monkeypatch.setattr(memory_platform, 'fetch_default_product_memory_search', fake_search)

    result = memory_platform.search_memory_platform(query='launch', limit=3, offset=4, uid='user-1')

    assert len(calls) == 1
    assert calls[0]['uid'] == 'user-1'
    assert calls[0]['query'] == 'launch'
    assert calls[0]['db_client'] is firestore_client
    assert calls[0]['limit'] == 3
    assert calls[0]['offset'] == 4
    assert result['uid'] == 'user-1'
    assert result['archive_default_visible'] is False


def test_platform_search_rejects_out_of_bounds_query(monkeypatch):
    with pytest.raises(HTTPException) as error:
        memory_platform.search_memory_platform(query='x' * 501, limit=1, offset=0, uid='user-1')

    assert error.value.status_code == 400


def test_platform_search_fails_closed_when_memory_system_is_not_canonical(monkeypatch):
    monkeypatch.setattr(memory_platform, 'resolve_memory_system', lambda uid: MemorySystem.LEGACY)

    def unreachable(*args, **kwargs):
        raise AssertionError('non-canonical principal must not reach rollout authorization or canonical reads')

    monkeypatch.setattr(memory_platform, 'authorize_memory_product_memory_route', unreachable)
    monkeypatch.setattr(memory_platform, 'fetch_default_product_memory_search', unreachable)

    with pytest.raises(HTTPException) as error:
        memory_platform.search_memory_platform(query='launch', limit=1, offset=0, uid='user-1')

    assert error.value.status_code == 503
    assert error.value.detail['reason'] == 'canonical_memory_system_required'


def test_platform_ingest_uses_canonical_memory_service(monkeypatch):
    created = SimpleNamespace(id='memory-1')
    calls = []

    monkeypatch.setattr(
        memory_platform,
        'canonical_write_decision',
        lambda uid, db_client: SimpleNamespace(memory_system=MemorySystem.CANONICAL, enabled=True, reason='enabled'),
    )

    class FakeMemoryService:
        def __init__(self, db_client):
            calls.append(('init', db_client))

        def create_external_memory(self, *args, **kwargs):
            calls.append((args, kwargs))
            return created

    monkeypatch.setattr(memory_platform, 'MemoryService', FakeMemoryService)

    result = asyncio.run(
        memory_platform.ingest_memory_platform(
            _request(),
            Memory(content='The backend is authoritative.', category=MemoryCategory.manual),
            uid='user-1',
        )
    )

    assert result.memory_id == 'memory-1'
    assert result.status == 'created'
    assert calls[1][1]['memory_system'] is MemorySystem.CANONICAL
    assert calls[1][1]['require_canonical_promotion'] is True


def test_platform_ingest_preserves_capture_device_provenance(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        memory_platform,
        'canonical_write_decision',
        lambda uid, db_client: SimpleNamespace(memory_system=MemorySystem.CANONICAL, enabled=True, reason='enabled'),
    )

    class FakeMemoryService:
        def __init__(self, db_client):
            pass

        def create_external_memory(self, uid, memory_db, **kwargs):
            captured['memory_db'] = memory_db
            return SimpleNamespace(id=memory_db.id)

    monkeypatch.setattr(memory_platform, 'MemoryService', FakeMemoryService)

    asyncio.run(
        memory_platform.ingest_memory_platform(
            _request({'x-app-platform': 'macos', 'x-device-id-hash': 'abcd1234'}),
            Memory(content='Captured on this laptop.'),
            uid='user-1',
        )
    )

    memory_db = captured['memory_db']
    assert [evidence.client_device_id for evidence in memory_db.evidence] == ['macos_abcd1234']


def test_platform_ingest_marks_explicit_submission_user_asserted(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        memory_platform,
        'canonical_write_decision',
        lambda uid, db_client: SimpleNamespace(memory_system=MemorySystem.CANONICAL, enabled=True, reason='enabled'),
    )

    class FakeMemoryService:
        def __init__(self, db_client):
            pass

        def create_external_memory(self, uid, memory_db, **kwargs):
            captured['memory_db'] = memory_db
            return SimpleNamespace(id=memory_db.id)

    monkeypatch.setattr(memory_platform, 'MemoryService', FakeMemoryService)

    # Category is omitted, so it defaults to `interesting` — the caller still
    # explicitly submitted this memory and it must be treated as user asserted,
    # otherwise canonical consolidation's unknown_source_subject_promotion
    # check keeps it short-term forever.
    asyncio.run(
        memory_platform.ingest_memory_platform(
            _request(),
            Memory(content='The user prefers email over calls.'),
            uid='user-1',
        )
    )

    assert captured['memory_db'].manually_added is True


def test_platform_ingest_blocks_import_marked_payload_in_enforce_mode(monkeypatch):
    monkeypatch.setenv('MEMORY_IMPORT_WRITE_BLOCK_MODE', 'enforce')

    def unreachable(*args, **kwargs):
        raise AssertionError('import-marked ingest must not reach the canonical write decision')

    monkeypatch.setattr(memory_platform, 'canonical_write_decision', unreachable)

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            memory_platform.ingest_memory_platform(
                _JsonRequest({'content': 'Copied from Apple Notes.', 'source_type': 'apple_notes'}),
                Memory(content='Copied from Apple Notes.'),
                uid='user-1',
            )
        )

    assert error.value.status_code == 409
    assert error.value.detail['error'] == 'import_must_use_evidence_ingress'


def test_platform_ingest_logs_but_persists_import_marked_payload_in_log_mode(monkeypatch):
    monkeypatch.setenv('MEMORY_IMPORT_WRITE_BLOCK_MODE', 'log')

    monkeypatch.setattr(
        memory_platform,
        'canonical_write_decision',
        lambda uid, db_client: SimpleNamespace(memory_system=MemorySystem.CANONICAL, enabled=True, reason='enabled'),
    )

    class FakeMemoryService:
        def __init__(self, db_client):
            pass

        def create_external_memory(self, uid, memory_db, **kwargs):
            return SimpleNamespace(id=memory_db.id)

    monkeypatch.setattr(memory_platform, 'MemoryService', FakeMemoryService)

    result = asyncio.run(
        memory_platform.ingest_memory_platform(
            _JsonRequest({'content': 'Copied from Apple Notes.', 'source_type': 'apple_notes'}),
            Memory(content='Copied from Apple Notes.'),
            uid='user-1',
        )
    )

    assert result.status == 'created'


def test_platform_ingest_drops_per_file_local_import_items_without_persisting(monkeypatch):
    monkeypatch.setenv('MEMORY_IMPORT_WRITE_BLOCK_MODE', 'log')

    def unreachable(*args, **kwargs):
        raise AssertionError('per-file import items must not be persisted')

    monkeypatch.setattr(memory_platform, 'canonical_write_decision', unreachable)
    monkeypatch.setattr(memory_platform, 'MemoryService', unreachable)

    result = asyncio.run(
        memory_platform.ingest_memory_platform(
            _JsonRequest({'content': 'resume.pdf fact', 'tags': ['local_files', 'onboarding', 'projects']}),
            Memory(content='resume.pdf fact'),
            uid='user-1',
        )
    )

    assert result.status == 'dropped'
    assert result.memory_id == memory_platform.document_id_from_seed('resume.pdf fact')


@pytest.mark.parametrize('blank_content', ['', '   ', '\n\t '])
def test_platform_ingest_rejects_blank_content_as_client_input(monkeypatch, blank_content):
    def unreachable(*args, **kwargs):
        raise AssertionError('blank ingest must not reach the canonical write decision')

    monkeypatch.setattr(memory_platform, 'canonical_write_decision', unreachable)

    with pytest.raises(HTTPException) as error:
        asyncio.run(memory_platform.ingest_memory_platform(_request(), Memory(content=blank_content), uid='user-1'))

    assert error.value.status_code == 400


def test_platform_ingest_fails_closed_when_canonical_write_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        memory_platform,
        'canonical_write_decision',
        lambda uid, db_client: SimpleNamespace(memory_system=MemorySystem.LEGACY, enabled=False, reason='disabled'),
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(memory_platform.ingest_memory_platform(_request(), Memory(content='not written'), uid='user-1'))

    assert error.value.status_code == 503
