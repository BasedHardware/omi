"""Real search core with injected indexes/storage; no provider or credential IO."""

from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND = Path(__file__).resolve().parents[2]


def module(name, **attrs):
    result = ModuleType(name)
    result.__dict__.update(attrs)
    return result


@pytest.fixture
def core():
    db = module('database.conversations', get_mcp_conversations_by_id=Mock(return_value=[]))
    vector = module(
        'database.vector_db',
        query_vectors=Mock(return_value=[]),
        embeddings=SimpleNamespace(embed_query=Mock(return_value=[1.0])),
    )
    search = module(
        'utils.conversations.search',
        keyword_search_conversation_ids=Mock(return_value=['keyword']),
        conversation_matches_date_range=lambda row, start, end: (
            start is None or row['created_at'].timestamp() >= start
        )
        and (end is None or row['created_at'].timestamp() <= end),
    )
    telemetry = Mock()
    with stub_modules(
        {
            'database.conversations': db,
            'database.vector_db': vector,
            'database.mcp_conversation_pages': module('database.mcp_conversation_pages'),
            'utils.conversations.search': search,
            'utils.conversations.render': module(
                'utils.conversations.render', redact_conversation_for_list=lambda row: row
            ),
            'utils.memory.product_authorization': module(
                'utils.memory.product_authorization', ProductAuthorizationContext=object
            ),
            'utils.mcp_memories': module(
                'utils.mcp_memories',
                parse_mcp_int=lambda value, field, default, minimum, maximum: max(
                    minimum, min(int(value if value is not None else default), maximum)
                ),
            ),
            'utils.observability.fallback': module('utils.observability.fallback', record_fallback=telemetry),
        }
    ):
        handler = load_module_fresh(
            'utils.mcp_server.handlers.conversations', str(BACKEND / 'utils/mcp_server/handlers/conversations.py')
        )
        yield handler, db, vector, search, telemetry


def row(cid='keyword', dt=None):
    return {'id': cid, 'created_at': dt or datetime(2026, 10, 1, tzinfo=timezone.utc), 'transcript_segments': []}


def test_empty_vectors_recover_keyword_matches(core):
    handler, db, vector, search, telemetry = core
    db.get_mcp_conversations_by_id.return_value = [row()]
    assert (
        handler.search_conversations_core('owner', 'budget', limit=10, start_dt=None, end_dt=None)[0]['id'] == 'keyword'
    )
    search.keyword_search_conversation_ids.assert_called_once_with(
        'owner', 'budget', limit=10, start_date=None, end_date=None, raise_on_error=True
    )
    vector.embeddings.embed_query.assert_called_once()
    telemetry.assert_called_once()


def test_empty_embedding_does_not_query_vector_provider(core):
    handler, db, vector, search, _ = core
    vector.embeddings.embed_query.return_value = []
    db.get_mcp_conversations_by_id.return_value = [row()]
    assert handler.search_conversations_core('owner', 'budget', limit=10, start_dt=None, end_dt=None)
    vector.query_vectors.assert_not_called()


def test_stale_vector_hydration_recovers_keywords(core):
    handler, db, vector, _, _ = core
    vector.query_vectors.return_value = ['deleted']
    db.get_mcp_conversations_by_id.side_effect = [[], [row()]]
    assert (
        handler.search_conversations_core('owner', 'budget', limit=10, start_dt=None, end_dt=None)[0]['id'] == 'keyword'
    )


def test_index_failure_is_actionable_and_not_silent_empty(core):
    handler, _, vector, search, _ = core
    vector.query_vectors.side_effect = RuntimeError('unavailable')
    search.keyword_search_conversation_ids.side_effect = RuntimeError('unavailable')
    with pytest.raises(handler.ToolExecutionError) as exc:
        handler.search_conversations_core('owner', 'budget', limit=10, start_dt=None, end_dt=None)
    assert exc.value.http_status == 503
    assert 'get_conversations' in exc.value.message


def test_hydrated_dates_filter_stale_index_and_keep_end_day_fraction(core):
    handler, db, vector, search, _ = core
    vector.query_vectors.return_value = ['outside', 'inside']
    end = datetime(2026, 10, 1, 23, 59, 59, 999999, tzinfo=timezone.utc)
    db.get_mcp_conversations_by_id.return_value = [
        row('outside', datetime(2026, 10, 2, tzinfo=timezone.utc)),
        row('inside', end),
    ]
    rows = handler.search_conversations_core('owner', 'budget', limit=10, start_dt=None, end_dt=end)
    assert [r['id'] for r in rows] == ['inside']
    search.keyword_search_conversation_ids.assert_not_called()


def test_shared_search_can_return_cards_without_hydrating_transcripts(core):
    handler, db, vector, _, _ = core
    vector.query_vectors.return_value = ['inside']
    db.get_mcp_conversations_by_id.return_value = [row('inside')]
    handler.search_conversations_core('owner', 'budget', limit=10, start_dt=None, end_dt=None, include_transcript=False)
    assert db.get_mcp_conversations_by_id.call_args.kwargs['include_transcript'] is False


def test_offset_page_emits_keyset_cursor_and_does_not_skip_lookahead(core):
    handler, _, _, _, _ = core
    handler.mcp_conversation_pages.get_mcp_conversation_cards = Mock(return_value=[row('a'), row('b')])
    result = handler.get_conversations('owner', {'limit': 1, 'offset': 5})
    assert result['has_more'] is True and result['effective_limit'] == 1
    position = handler.decode_cursor(
        result['next_cursor'],
        kind='get_conversations',
        uid='owner',
        filters={'categories': [], 'start': None, 'end': None},
    )
    assert position['id'] == 'a'
    assert result['conversations'][0]['id'] == 'a'


def test_participants_are_stored_mappings_not_prose(core):
    handler, _, _, _, _ = core
    conversation = row()
    conversation['transcript_segments'] = [{'speaker_id': 1, 'person_id': 'known', 'is_user': False}] * 2 + [
        {'speaker_id': [], 'person_id': {}},
        'legacy-corrupt',
    ]
    card = handler.conversation_card(conversation)
    assert card['participants_included'] is True
    assert card['person_ids'] == ['known'] and len(card['participants']) == 1
    conversation.pop('transcript_segments')
    assert handler.conversation_card(conversation)['participants_included'] is False


def test_shared_search_treats_naive_dates_as_utc_even_with_aware_end(core):
    handler, db, vector, search, _ = core
    vector.query_vectors.return_value = ['inside']
    db.get_mcp_conversations_by_id.return_value = [row('inside')]
    rows = handler.search_conversations_core(
        'owner', 'budget', limit=10, start_dt=datetime(2026, 10, 1), end_dt=datetime(2026, 10, 2, tzinfo=timezone.utc)
    )
    assert [r['id'] for r in rows] == ['inside']
    assert vector.query_vectors.call_args.kwargs['starts_at'] == int(
        datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp()
    )


@pytest.fixture
def memory_core():
    service_instance = SimpleNamespace(
        search_mcp=Mock(return_value=[]),
        read_page=Mock(
            return_value=SimpleNamespace(
                memories=[],
                next_cursor=None,
                truncated=False,
            )
        ),
    )
    service_cls = Mock(return_value=service_instance)
    telemetry = Mock()
    with stub_modules(
        {
            'database._client': module(
                'database._client', db=object(), document_id_from_seed=lambda *args, **kwargs: 'doc-id'
            ),
            'testing.parity_pack_v0.live_capture': module(
                'testing.parity_pack_v0.live_capture', capture_memory_write=Mock()
            ),
            'utils.llm.memories': module('utils.llm.memories', identify_category_for_memory=Mock()),
            'utils.memory.memory_api_contract': module(
                'utils.memory.memory_api_contract',
                MemoryApiExposure=SimpleNamespace(CANONICAL='canonical'),
                memory_api_payload=lambda m, _: m,
            ),
            'utils.memory.memory_service': module('utils.memory.memory_service', MemoryService=service_cls),
            'utils.memory.memory_system': module(
                'utils.memory.memory_system', MemorySystem=SimpleNamespace(CANONICAL='canonical')
            ),
            'utils.memory.default_read_rollout': module(
                'utils.memory.default_read_rollout', MemoryReadDecision=SimpleNamespace(USE_MEMORY='use_memory')
            ),
            'utils.memory.product_authorization': module(
                'utils.memory.product_authorization',
                ProductAuthorizationContext=object,
                authorize_memory_external_default_memory_read=Mock(return_value=SimpleNamespace(allowed=True)),
                authorize_memory_external_default_memory_write=Mock(return_value=SimpleNamespace(allowed=True)),
            ),
            'utils.observability.fallback': module('utils.observability.fallback', record_fallback=telemetry),
            'utils.other.endpoints': module(
                'utils.other.endpoints',
                check_rate_limit_context=Mock(),
                check_rate_limit_inline=Mock(),
            ),
        }
    ):
        handler = load_module_fresh(
            'utils.mcp_server.handlers.memories', str(BACKEND / 'utils/mcp_server/handlers/memories.py')
        )
        yield handler, service_instance, telemetry


def _memory_item(mid: str, content: str, *, category: str = 'system', is_locked: bool = False, tags=None):
    return SimpleNamespace(
        model_dump=lambda mode='json': {
            'id': mid,
            'content': content,
            'category': category,
            'is_locked': is_locked,
            'tags': tags or [],
        }
    )


def test_empty_memory_vectors_recover_lexical_matches_without_outage_telemetry(memory_core):
    handler, service, telemetry = memory_core
    service.read_page.return_value = SimpleNamespace(
        memories=[
            _memory_item('locked-hit', 'User quarterly budget target is 50k', is_locked=True),
            _memory_item('activity-hit', 'Focused on quarterly budget spreadsheet', tags=['activity']),
            _memory_item('lexical-hit', 'Agreed quarterly budget cap with finance team', category='work'),
        ],
        next_cursor='page-2',
        truncated=False,
    )
    result = handler.search_memories_core('owner', 'quarterly budget', limit=10)
    assert [m['id'] for m in result['memories']] == ['lexical-hit']
    assert result['memories'][0]['relevance_score'] == 1.0
    assert result['search_coverage'] == 'eligible_indexed_memories_with_lexical_recovery'
    assert 'message' not in result
    # Healthy-index no-hit must not fire outage fallback telemetry and scans at most 1 page.
    telemetry.assert_not_called()
    assert service.read_page.call_count == 1


def test_memory_index_outage_emits_typed_fallback_telemetry_and_coverage(memory_core):
    handler, service, telemetry = memory_core
    service.search_mcp.side_effect = RuntimeError('vector unavailable')
    service.read_page.return_value = SimpleNamespace(
        memories=[_memory_item('lexical-hit', 'Agreed quarterly budget cap with finance team', category='work')],
        next_cursor=None,
        truncated=False,
    )
    result = handler.search_memories_core('owner', 'quarterly budget', limit=10)
    assert [m['id'] for m in result['memories']] == ['lexical-hit']
    assert result['search_coverage'] == 'lexical_fallback_only'
    telemetry.assert_called_once()
    assert telemetry.call_args.kwargs['component'] == 'agent_tools'
    assert telemetry.call_args.kwargs['from_mode'] == 'indexed_memories'
    assert telemetry.call_args.kwargs['to_mode'] == 'lexical_scan'
    assert telemetry.call_args.kwargs['reason'] == 'unavailable'
    assert telemetry.call_args.kwargs['outcome'] == 'degraded'


def test_memory_index_programming_error_is_not_masked_as_outage(memory_core):
    handler, service, telemetry = memory_core
    service.search_mcp.side_effect = TypeError('bad payload shape')
    with pytest.raises(TypeError, match='bad payload shape'):
        handler.search_memories_core('owner', 'budget', limit=10)
    telemetry.assert_not_called()
    service.read_page.assert_not_called()


def test_memory_index_failure_and_lexical_failure_is_actionable(memory_core):
    handler, service, _ = memory_core
    service.search_mcp.side_effect = RuntimeError('vector unavailable')
    service.read_page.side_effect = RuntimeError('store unavailable')
    with pytest.raises(handler.ToolExecutionError) as exc:
        handler.search_memories_core('owner', 'budget', limit=10)
    assert exc.value.http_status == 503
    assert 'get_memories' in exc.value.message


def test_search_memories_rejects_blank_query(memory_core):
    handler, service, _ = memory_core
    with pytest.raises(handler.ToolExecutionError) as exc:
        handler.search_memories('owner', {'query': '   '}, auth_context=object())
    assert exc.value.code == -32602
    service.search_mcp.assert_not_called()


