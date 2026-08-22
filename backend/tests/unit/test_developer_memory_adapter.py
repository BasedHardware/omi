import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from models.memory_search_gateway import SearchMode
from models.product_memory import MemoryTier, ProcessingState
from tests.unit.fixtures.memory_adapter_fakes import (
    FirestoreFake as _FirestoreFake,
    VectorCandidateResult as _VectorCandidateResult,
    enabled_rollout_doc,
    memory_item,
    stored_item as _stored_item,
    vector_hit as _hit,
)
from utils.memory.developer_memory_adapter import (
    DeveloperMemorySearchResult,
    search_memory_default_developer_memories,
    search_memory_default_developer_memories_vector,
)
from utils.memory.default_read_rollout import (
    MemoryReadDecision,
    read_default_read_rollout,
)

_DEVELOPER_QUOTE_TEXT = 'User prefers concrete developer memory reads.'


@pytest.fixture(autouse=True)
def _empty_historical_store(monkeypatch):
    """These adapter cases seed canonical items only; mixed-origin reads live elsewhere."""
    import utils.memory.memory_service as memory_service

    monkeypatch.setattr(memory_service.memories_db, 'get_memories', lambda *args, **kwargs: [])
    monkeypatch.setattr(memory_service.memories_db, 'list_memory_updated_or_created_index', lambda *args, **kwargs: [])
    monkeypatch.setattr(memory_service.memories_db, 'get_memories_by_ids', lambda *args, **kwargs: [])


def _developer_source() -> str:
    developer_py = Path(__file__).resolve().parents[2] / 'routers' / 'developer.py'
    return developer_py.read_text(encoding='utf-8')


def _function_source_for_route(path: str, method: str) -> str:
    contents = _developer_source()
    module = ast.parse(contents)
    lines = contents.splitlines(keepends=True)
    for node in module.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if not (
                isinstance(func, ast.Attribute)
                and func.attr == method
                and isinstance(func.value, ast.Name)
                and func.value.id == 'router'
            ):
                continue
            if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
                continue
            if decorator.args[0].value != path:
                continue
            return ''.join(lines[node.lineno - 1 : node.end_lineno])
    raise AssertionError(f'route not found: {method.upper()} {path}')


def _compact_python(source: str) -> str:
    """Make formatter-only line wrapping irrelevant to source contract checks."""
    return "".join(source.split())


def _memory_item(memory_id: str, *, tier=MemoryTier.short_term, now=None, captured_at=None, content=None, **overrides):
    return memory_item(
        memory_id,
        tier=tier,
        now=now,
        captured_at=captured_at,
        content=content,
        quote_text=_DEVELOPER_QUOTE_TEXT,
        **overrides,
    )


def _enabled_rollout_doc(uid='u1'):
    return enabled_rollout_doc(uid, grant_consumer='developer_api')


def test_developer_route_reads_use_universal_service_without_legacy_fallback():
    contents = _developer_source()
    assert 'service = MemoryService(db_client=db)' in contents
    assert 'memories = service.read(uid, limit=limit, offset=offset, include_pending_processing=True)' in contents
    assert 'MemoryService(db_client=db).search(uid, query, limit=min(limit, 20))' in contents
    assert 'read_default_read_rollout' not in contents
    assert 'search_memory_default_developer_memories(' not in contents
    assert 'memories_db' not in contents


def test_developer_vector_route_wires_app_key_scope_grant_before_memory_vector_reads():
    route_source = _function_source_for_route("/v1/dev/user/memories/vector/search", "get")
    compact = _compact_python(route_source)
    auth_context_dependency = (
        "auth_context:ProductAuthorizationContext=Depends(get_developer_memory_default_memory_read_context)"
    )
    uid_from_context = "uid=auth_context.uid"
    app_key_grant_call = "app_key_grant=authorize_memory_external_default_memory_read(auth_context,db_client=db)"
    app_key_deny_check = "ifnotapp_key_grant.allowed:"
    assert auth_context_dependency in compact
    assert app_key_grant_call in compact
    assert "MemoryService(db_client=db).search(uid,query,limit=min(limit,20))" in compact
    assert "read_default_read_rollout" not in route_source
    assert "search_memory_default_developer_memories_vector(" not in route_source
    assert (
        compact.index(auth_context_dependency)
        < compact.index(uid_from_context)
        < compact.index(app_key_grant_call)
        < compact.index(app_key_deny_check)
        < compact.index("MemoryService(db_client=db).search")
    )


def test_developer_create_route_checks_scope_before_universal_write():
    route_source = _compact_python(_function_source_for_route("/v1/dev/user/memories", "post"))
    external_create = ".create_external_memory("
    grant_call = "authorize_memory_external_default_memory_write(auth_context,db_client=db)"
    assert grant_call in route_source
    assert external_create in route_source
    assert "MemorySystem.CANONICAL" in route_source
    assert route_source.index(grant_call) < route_source.index(external_create)


def test_developer_batch_create_route_checks_scope_before_universal_write():
    route_source = _compact_python(_function_source_for_route("/v1/dev/user/memories/batch", "post"))
    categorization = "identify_category_for_memory(mem_req.content.strip())"
    external_batch = ".create_external_memory_batch("
    grant_call = "authorize_memory_external_default_memory_write(auth_context,db_client=db)"
    assert grant_call in route_source
    assert categorization in route_source
    assert external_batch in route_source
    assert "MemorySystem.CANONICAL" in route_source
    assert route_source.index(grant_call) < route_source.index(categorization)
    assert route_source.index(categorization) < route_source.index(external_batch)


def test_developer_delete_route_checks_scope_before_universal_delete():
    route_source = _compact_python(_function_source_for_route("/v1/dev/user/memories/{memory_id}", "delete"))
    external_delete = ".delete_external_memory("
    grant_call = "authorize_memory_external_default_memory_write(auth_context,db_client=db)"
    assert grant_call in route_source
    assert external_delete in route_source
    assert "MemorySystem.CANONICAL" in route_source
    assert "memories_db" not in route_source
    assert route_source.index(grant_call) < route_source.index(external_delete)


def test_developer_update_route_checks_scope_before_universal_mutations():
    route_source = _compact_python(_function_source_for_route("/v1/dev/user/memories/{memory_id}", "patch"))
    grant_call = "authorize_memory_external_default_memory_write(auth_context,db_client=db)"
    assert grant_call in route_source
    assert "MemoryService(db_client=db)" in route_source
    assert "memories_db" not in route_source
    assert route_source.index(grant_call) < route_source.index("MemoryService(db_client=db)")


def test_developer_routes_never_reach_legacy_after_universal_cutover():
    contents = _developer_source()
    for marker in ('memories_db', 'read_default_read_rollout', 'pin_memory_system', 'resolve_memory_system'):
        assert marker not in contents


def test_developer_category_filters_do_not_force_legacy_when_memory_can_decide_safely():
    developer_py = Path(__file__).resolve().parents[2] / 'routers' / 'developer.py'
    contents = developer_py.read_text(encoding='utf-8')
    category_legacy_reason = 'developer_category_legacy_safe_fallback_explicit'
    category_filter_argument = 'categories=[c.value for c in category_list]'
    assert category_filter_argument in contents
    assert category_legacy_reason not in contents


def test_developer_default_memory_adapter_filters_categories_without_legacy_fallback():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    source_unknown = _memory_item('source-unknown', now=now, content='coffee source unknown')
    db_client = _FirestoreFake({f'users/u1/memory_items/{source_unknown.memory_id}': _stored_item(source_unknown)})
    decision = read_default_read_rollout(
        uid='u1',
        db_client=_FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()}),
        consumer='developer_api',
    )
    other_result = search_memory_default_developer_memories(
        uid='u1',
        query='',
        limit=10,
        offset=0,
        db_client=db_client,
        rollout_decision=decision,
        now=now,
        categories=['other'],
    )
    manual_result = search_memory_default_developer_memories(
        uid='u1',
        query='',
        limit=10,
        offset=0,
        db_client=db_client,
        rollout_decision=decision,
        now=now,
        categories=['manual'],
    )
    assert other_result.read_decision == MemoryReadDecision.USE_MEMORY
    assert other_result.should_use_legacy_fallback is False
    assert [item['id'] for item in other_result.memories] == ['source-unknown']
    assert manual_result.read_decision == MemoryReadDecision.USE_MEMORY
    assert manual_result.should_use_legacy_fallback is False
    assert manual_result.memories == []


def test_developer_rollout_reader_derives_default_memory_grant_without_reading_memory_items():
    db_client = _FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()})
    decision = read_default_read_rollout(uid='u1', db_client=db_client, consumer='developer_api')
    assert db_client.document_get_paths == ['users/u1/memory_control/state']
    assert db_client.collection_paths == []
    assert decision.rollout_capabilities.memory_reads_enabled is True
    assert decision.app_has_default_memory_grant is True
    assert decision.archive_capability is False
    assert decision.memory_default_developer_enabled is True


def test_developer_default_memory_adapter_keeps_expired_unadjudicated_short_term_and_excludes_archive():
    now = datetime.now(timezone.utc).replace(microsecond=0)
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
    decision = read_default_read_rollout(
        uid='u1',
        db_client=_FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()}),
        consumer='developer_api',
    )
    result = search_memory_default_developer_memories(
        uid='u1', query='coffee', limit=10, offset=0, db_client=db_client, rollout_decision=decision, now=now
    )
    assert isinstance(result, DeveloperMemorySearchResult)
    assert result.read_decision == MemoryReadDecision.USE_MEMORY
    assert result.fallback_reason is None
    results = result.memories
    assert db_client.collection_paths == ['users/u1/memory_items']
    assert [item['id'] for item in results] == ['fresh-short-term', 'long-term', 'stale-short-term']
    assert [item['content'] for item in results] == [
        'coffee fresh short term',
        'coffee long term',
        'coffee stale short term',
    ]
    assert all((item['category'] == 'other' for item in results))
    assert all((item['visibility'] == 'private' for item in results))
    assert all((item['memory_default_memory'] is True for item in results))
    assert all((item['archive_default_visible'] is False for item in results))
    assert all((item['policy']['consumer'] == 'developer_api' for item in results))
    assert all((item['policy']['archive_capability'] is False for item in results))


def test_developer_default_memory_adapter_excludes_pending_admission_text():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    pending = _memory_item(
        'pending-explicit',
        now=now,
        content='coffee pending explicit memory',
        processing_state=ProcessingState.pending,
    )
    db_client = _FirestoreFake({f'users/u1/memory_items/{pending.memory_id}': _stored_item(pending)})
    decision = read_default_read_rollout(
        uid='u1',
        db_client=_FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()}),
        consumer='developer_api',
    )

    result = search_memory_default_developer_memories(
        uid='u1', query='coffee', limit=10, offset=0, db_client=db_client, rollout_decision=decision, now=now
    )

    assert result.memories == []


def test_developer_default_memory_response_shape_marks_universal_provenance_and_compatibility_defaults():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    public_item = _memory_item('public-source', now=now, content='coffee public source', visibility='public')
    db_client = _FirestoreFake({f'users/u1/memory_items/{public_item.memory_id}': _stored_item(public_item)})
    decision = read_default_read_rollout(
        uid='u1',
        db_client=_FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()}),
        consumer='developer_api',
    )
    result = search_memory_default_developer_memories(
        uid='u1', query='', limit=10, offset=0, db_client=db_client, rollout_decision=decision, now=now
    )
    assert result.read_decision == MemoryReadDecision.USE_MEMORY
    memory = result.memories[0]
    assert memory['visibility'] == 'public'
    assert memory['visibility_source'] == 'universal_memory_service'
    assert memory['category'] == 'other'
    assert memory['category_source'] == 'developer_memory_compatibility_default_no_source_category'
    assert memory['reviewed'] is False
    assert memory['reviewed_source'] == 'developer_memory_compatibility_default_no_review_state'
    assert memory['edited'] is False
    assert memory['edited_source'] == 'developer_memory_compatibility_default_no_edit_state'


def test_developer_vector_adapter_uses_hydrated_vector_service_and_preserves_ranking_without_archive_default():
    now = datetime.now(timezone.utc).replace(microsecond=0)
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
    decision = read_default_read_rollout(
        uid='u1',
        db_client=_FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()}),
        consumer='developer_api',
    )
    vector_calls = []

    def vector_query(uid, query, *, mode, limit):
        vector_calls.append({'uid': uid, 'query': query, 'mode': mode, 'limit': limit})
        return _VectorCandidateResult(
            hits=[
                _hit(stale_short_term, score=0.99),
                _hit(archive, score=0.98),
                _hit(long_term, score=0.92),
                _hit(fresh_short_term, score=0.8),
            ],
            rejected_count=1,
        )

    result = search_memory_default_developer_memories_vector(
        uid='u1', query='coffee', limit=10, db_client=db_client, rollout_decision=decision, vector_query=vector_query
    )
    assert result.read_decision == MemoryReadDecision.USE_MEMORY
    assert result.fallback_reason is None
    results = result.memories
    assert vector_calls == [{'uid': 'u1', 'query': 'coffee', 'mode': SearchMode.default, 'limit': 30}]
    assert db_client.collection_paths == []
    assert [item['id'] for item in results] == ['stale-short-term', 'long-term', 'fresh-short-term']
    assert [item['relevance_score'] for item in results] == [0.99, 0.92, 0.8]
    assert all((item['memory_default_memory'] is True for item in results))
    assert all((item['archive_default_visible'] is False for item in results))
    assert all((item['policy']['consumer'] == 'developer_api' for item in results))
    assert all((item['policy']['archive_capability'] is False for item in results))


def test_developer_vector_adapter_serves_limits_above_the_default_candidate_budget():
    """A limit inside the route's advertised window must not blow up the request.

    GET /v1/dev/user/memories/vector/search declares `limit: int = Query(10, ge=1, le=100)`
    and the developer_api branch of execute_default_read_vector_search admits up to 100.
    But fetch_default_vector_memory_search defaults max_candidates to
    DEFAULT_MEMORY_VECTOR_MAX_CANDIDATES (50) and rejects max_candidates < limit, so every
    limit in 51..100 raised "max_candidates must be between limit and 100" — an HTTP 500
    on an input the route says is valid.
    """
    now = datetime.now(timezone.utc).replace(microsecond=0)
    items = [_memory_item(f'long-{i}', tier=MemoryTier.long_term, now=now, content=f'coffee {i}') for i in range(3)]
    db_client = _FirestoreFake({f'users/u1/memory_items/{item.memory_id}': _stored_item(item) for item in items})
    decision = read_default_read_rollout(
        uid='u1',
        db_client=_FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()}),
        consumer='developer_api',
    )

    def vector_query(uid, query, *, mode, limit):
        return _VectorCandidateResult(
            hits=[_hit(item, score=0.9 - index * 0.01) for index, item in enumerate(items)],
            rejected_count=0,
        )

    result = search_memory_default_developer_memories_vector(
        uid='u1', query='coffee', limit=60, db_client=db_client, rollout_decision=decision, vector_query=vector_query
    )

    assert result.read_decision == MemoryReadDecision.USE_MEMORY
    assert result.fallback_reason is None
    assert [item['id'] for item in result.memories] == ['long-0', 'long-1', 'long-2']
