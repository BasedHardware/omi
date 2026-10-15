"""Search charges the hit the model sees, and unreadable rows stay on the page."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from config.dream_session import SessionLimits
from models.agent_tools import Read, Search
from utils.agent_capabilities import reads, search
from utils.agent_capabilities.session import Session, rejection, serialized_bytes


def _bind(monkeypatch, rows, history):
    monkeypatch.setattr(search.dream_history, 'history_page', history)

    async def load(self, ref, request=None):
        key = ref.partition('/')[2]
        row = rows[key]
        if isinstance(row, Exception):
            raise row
        return row

    monkeypatch.setattr(search.OwnerSearch, 'read', load)
    monkeypatch.setattr(search.OwnerSearch, 'hydrate', load)
    return search.OwnerSearch('synthetic-search-owner')


def test_preview_masks_transcript_when_a_title_exists(monkeypatch):
    seen = {}

    def snapshot(uid, key, *, field_paths=None, firestore_client=None):
        seen['fields'] = field_paths
        return {
            'id': key,
            'status': 'completed',
            'structured': {'title': 'Synthetic title', 'overview': 'Synthetic overview'},
            'transcript_segments': [{'text': 'x' * 50000}],
        }

    monkeypatch.setattr(reads.conversations, 'get_conversation_raw_snapshot', snapshot)
    monkeypatch.setattr(reads.conversations, 'is_visible_conversation', lambda raw: True)
    row = reads.preview_record('synthetic-search-owner', 'conversations/titled')
    assert seen['fields'] is not None and 'transcript_segments' not in seen['fields']
    assert row['structured']['title'] == 'Synthetic title'
    assert 'transcript_segments' not in row
    assert serialized_bytes(row) < 2000


@pytest.mark.asyncio
async def test_large_records_leave_read_budget_for_a_later_read(monkeypatch):
    rows = {f'big-{index}': {'content': 'x' * 100000} for index in range(4)}
    rows['useful'] = {'content': 'Synthetic useful fact'}
    source = _bind(monkeypatch, rows, lambda *args, **kwargs: list(rows))
    session = Session('synthetic-search-owner', source, SessionLimits(read_bytes=512000), {}, authority='user')
    before = session.read_bytes
    result = await session.search(Search(collections=['memory_items'], limit=8))
    assert [hit['ref'] for hit in result['results']][-1] == 'memory_items/useful'
    charged = session.read_bytes - before
    assert charged == serialized_bytes(result['results'])
    assert charged < serialized_bytes(rows['big-0'])
    loaded = await session.read(Read(refs=['memory_items/useful']))
    assert loaded['records']['memory_items/useful'] == rows['useful']
    assert session.read_bytes < 80000


@pytest.mark.asyncio
async def test_none_and_raising_rows_keep_the_rest_of_the_page(monkeypatch):
    rows = {
        'first': {'content': 'Synthetic first fact'},
        'missing': None,
        'raising': RuntimeError('Synthetic unreadable row'),
        'last': {'content': 'Synthetic last fact'},
    }
    fallbacks = []
    monkeypatch.setattr(search, 'keyword_search_conversation_ids', lambda **kwargs: list(rows))
    monkeypatch.setattr(search, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))
    source = _bind(monkeypatch, rows, lambda *args, **kwargs: [])
    result = await source.search(Search(query='Synthetic', collections=['conversations'], limit=4), byte_budget=8000)
    assert [hit['ref'] for hit in result['results']] == ['conversations/first', 'conversations/last']
    assert result['unavailable_refs'] == ['conversations/missing', 'conversations/raising']
    assert result['counts']['failed_paths'] == 0 and result['counts']['unavailable'] == 2
    assert result['complete'] is True and fallbacks == []


@pytest.mark.asyncio
async def test_provider_fault_still_fails_the_path(monkeypatch):
    fallbacks = []

    def fault(**kwargs):
        raise RuntimeError('Synthetic search provider')

    monkeypatch.setattr(search, 'keyword_search_conversation_ids', fault)
    monkeypatch.setattr(search, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))
    source = search.OwnerSearch('synthetic-search-owner')
    result = await source.search(Search(query='Synthetic', collections=['conversations']), byte_budget=8000)
    assert result['results'] == [] and result['counts']['failed_paths'] == 1 and result['complete'] is False
    assert fallbacks and fallbacks[0]['outcome'] == 'degraded'


@pytest.mark.asyncio
async def test_history_pages_past_a_full_page_of_dead_ids(monkeypatch):
    def history_page(uid, collection, *, after=None, limit=40, firestore_client=None):
        assert collection == 'memory_items'
        if after is None:
            return [f'dead-{index:02d}' for index in range(40)]
        assert after == 'dead-39'
        return ['raising', 'live']

    rows = {f'dead-{index:02d}': None for index in range(40)}
    rows['raising'] = RuntimeError('Synthetic unreadable memory')
    rows['live'] = {'content': 'Synthetic live memory'}
    source = _bind(monkeypatch, rows, history_page)
    result = await source.search(Search(collections=['memory_items'], limit=8), byte_budget=8000)
    assert result['results'] == [{'ref': 'memory_items/live', 'snippet': 'Synthetic live memory'}]
    assert 'memory_items/raising' in result['unavailable_refs']
    assert len([ref for ref in result['unavailable_refs'] if '/dead-' in ref]) == 40
    assert result['counts']['failed_paths'] == 0 and result['cursors']['memory_items'] == 'live'


@pytest.mark.asyncio
async def test_read_reports_unavailable_and_keeps_the_sibling():
    class Source:
        async def read(self, ref):
            if ref.endswith('/bad'):
                raise RuntimeError('Synthetic storage fault')
            if ref.endswith('/gone'):
                return None
            return {'content': 'Synthetic sibling'}

    session = Session(
        'synthetic-search-owner',
        Source(),
        SessionLimits(read_bytes=8000),
        {'targets': ['conversations/bad', 'conversations/gone', 'conversations/ok']},
        authority='user',
    )
    loaded = await session.read(Read(refs=['conversations/bad', 'conversations/gone', 'conversations/ok']))
    assert loaded['errors']['conversations/bad']['code'] == 'agent_read_unavailable'
    assert loaded['errors']['conversations/bad']['retryable'] is False
    assert loaded['errors']['conversations/gone'] == {
        'code': 'agent_record_unavailable',
        'field': 'refs',
        'ref': 'conversations/gone',
        'expected': 'Use an available owner record',
        'retryable': False,
    }
    assert loaded['records']['conversations/ok'] == {'content': 'Synthetic sibling'}


def test_memory_http_exception_is_unavailable_and_visible_memory_remains(monkeypatch):
    monkeypatch.setattr(reads, 'read_canonical_memory_item', lambda uid, key: None)

    def fetch(self, uid, key):
        raise HTTPException(404 if key == 'gone' else 503, 'Synthetic memory lifecycle')

    monkeypatch.setattr(reads.MemoryService, 'fetch', fetch)
    assert reads.read_record('synthetic-search-owner', 'memory_items/gone') is None
    assert reads.read_record('synthetic-search-owner', 'memory_items/fault') is None

    class Visible:
        user_review = True
        visibility = 'private'
        invalid_at = None
        is_locked = False

        def model_dump(self, mode='python'):
            return {'content': 'Synthetic visible memory', 'visibility': 'private'}

    class Locked(Visible):
        is_locked = True

    monkeypatch.setattr(reads, 'filter_canonical_default_visible_items', lambda items, **kwargs: items)
    monkeypatch.setattr(reads, 'memory_item_to_memorydb', lambda item: Locked() if item == 'locked' else Visible())
    monkeypatch.setattr(reads, 'read_canonical_memory_item', lambda uid, key: 'locked' if key == 'locked' else object())
    assert reads.read_record('synthetic-search-owner', 'memory_items/visible')['content'] == 'Synthetic visible memory'
    assert reads.read_record('synthetic-search-owner', 'memory_items/locked') is None


def test_seed_skips_dead_and_raising_dirty_ids(monkeypatch):
    from utils import dream_seed

    class Snapshot:
        def __init__(self, payload):
            self.payload = payload

        def to_dict(self):
            return self.payload

    class Query:
        def order_by(self, *args, **kwargs):
            return self

        def select(self, *args, **kwargs):
            return self

        def limit(self, *args, **kwargs):
            return self

        def stream(self):
            return []

    monkeypatch.setattr(dream_seed.dream_history, 'history_count', lambda *args, **kwargs: 0)
    monkeypatch.setattr(dream_seed.users, 'get_user_profile', lambda uid: {})
    monkeypatch.setattr(dream_seed.dream_store, 'vocabulary', lambda uid: [])
    monkeypatch.setattr(dream_seed.dream_store, 'own_runs', lambda uid, limit=1: [])
    monkeypatch.setattr(dream_seed.review_store, 'user', lambda uid: SimpleNamespace(collection=lambda name: Query()))
    monkeypatch.setattr(
        dream_seed.dream_store,
        'dirty_refs',
        lambda uid, limit=32, newest=False: [
            Snapshot({'collection': 'conversations', 'id': 'dead'}),
            Snapshot({'collection': 'conversations', 'id': 'raising'}),
            Snapshot({'collection': 'conversations', 'id': 'live'}),
        ],
    )

    def read_record(uid, ref):
        if ref.endswith('/dead'):
            return None
        if ref.endswith('/raising'):
            raise RuntimeError('Synthetic unreadable seed')
        return {'id': 'live', 'structured': {'title': 'Synthetic live capture'}}

    monkeypatch.setattr(dream_seed, 'read_record', read_record)
    seed, records, _dirty, _limits = dream_seed.load('synthetic-search-owner', SimpleNamespace(tokens=1000, edits=1))
    assert seed['targets'] == ['conversations/live']
    assert seed['unavailable_targets']['conversations/dead'] is False
    assert seed['unavailable_targets']['conversations/raising'] is True
    assert records['conversations/live']['id'] == 'live'


def test_memories_alias_is_memory_items_and_unknown_collections_stay_invalid():
    from database.dream_history import history_collection

    class Node:
        def __init__(self, name=None):
            self.name = name

        def collection(self, name):
            return Node(name)

        def document(self, key):
            return self

    assert history_collection('synthetic-search-owner', 'memories', firestore_client=Node()).name == 'memory_items'
    with pytest.raises(ValueError, match='dream_history_collection'):
        history_collection('synthetic-search-owner', 'folders', firestore_client=Node())
    assert Search(collections=['memories']).collections == ['memory_items']
    with pytest.raises(ValidationError) as caught:
        Search(collections=['folders'])
    assert rejection(caught.value)['reason'] == 'schema' and rejection(caught.value)['retryable'] is True
