from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import routers.memory_platform as memory_platform
from models.memories import Memory, MemoryCategory
from utils.memory.memory_system import MemorySystem


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

    monkeypatch.setattr(memory_platform, '_require_product_authorization', lambda uid: _authorization())

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
    assert calls[0]['db_client'] is memory_platform.db
    assert calls[0]['limit'] == 3
    assert calls[0]['offset'] == 4
    assert result['uid'] == 'user-1'
    assert result['archive_default_visible'] is False


def test_platform_search_rejects_out_of_bounds_query(monkeypatch):
    with pytest.raises(HTTPException) as error:
        memory_platform.search_memory_platform(query='x' * 501, limit=1, offset=0, uid='user-1')

    assert error.value.status_code == 400


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

    result = memory_platform.ingest_memory_platform(
        Memory(content='The backend is authoritative.', category=MemoryCategory.manual),
        uid='user-1',
    )

    assert result.memory_id == 'memory-1'
    assert result.status == 'created'
    assert calls[1][1]['memory_system'] is MemorySystem.CANONICAL
    assert calls[1][1]['require_canonical_promotion'] is True


@pytest.mark.parametrize('blank_content', ['', '   ', '\n\t '])
def test_platform_ingest_rejects_blank_content_as_client_input(monkeypatch, blank_content):
    def unreachable(*args, **kwargs):
        raise AssertionError('blank ingest must not reach the canonical write decision')

    monkeypatch.setattr(memory_platform, 'canonical_write_decision', unreachable)

    with pytest.raises(HTTPException) as error:
        memory_platform.ingest_memory_platform(Memory(content=blank_content), uid='user-1')

    assert error.value.status_code == 400


def test_platform_ingest_fails_closed_when_canonical_write_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        memory_platform,
        'canonical_write_decision',
        lambda uid, db_client: SimpleNamespace(memory_system=MemorySystem.LEGACY, enabled=False, reason='disabled'),
    )

    with pytest.raises(HTTPException) as error:
        memory_platform.ingest_memory_platform(Memory(content='not written'), uid='user-1')

    assert error.value.status_code == 503
