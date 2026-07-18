import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from config.memory_rollout import MemoryRolloutMode
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
    WriteConvergencePolicy,
    assert_legacy_memory_write_allowed_for_default_read_decision,
    legacy_safe_default_read_rollout_decision,
    read_default_read_rollout,
)

_DEVELOPER_QUOTE_TEXT = 'User prefers concrete developer memory reads.'


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


def test_developer_route_wires_adapter_before_legacy_memory_reads():
    developer_py = Path(__file__).resolve().parents[2] / 'routers' / 'developer.py'
    contents = developer_py.read_text(encoding='utf-8')
    rollout_call = "read_default_read_rollout(uid=uid, db_client=db, consumer='developer_api')"
    adapter_call = 'search_memory_default_developer_memories('
    legacy_call = 'memories_db.get_memories(uid, limit, offset, [c.value for c in category_list])'
    assert rollout_call in contents
    assert adapter_call in contents
    assert legacy_call in contents
    assert contents.index(rollout_call) < contents.index(adapter_call) < contents.index(legacy_call)


def test_developer_vector_route_wires_app_key_scope_grant_before_memory_vector_reads():
    route_source = _function_source_for_route('/v1/dev/user/memories/vector/search', 'get')
    auth_context_dependency = (
        'auth_context: ProductAuthorizationContext = Depends(get_developer_memory_default_memory_read_context)'
    )
    uid_from_context = 'uid = auth_context.uid'
    app_key_grant_call = 'app_key_grant = authorize_memory_external_default_memory_read(auth_context, db_client=db)'
    app_key_deny_check = 'if not app_key_grant.allowed:'
    rollout_call = "read_default_read_rollout(uid=uid, db_client=db, consumer='developer_api')"
    vector_adapter_call = 'search_memory_default_developer_memories_vector('
    vector_side_effect = 'fetch_default_vector_memory_search('
    assert auth_context_dependency in route_source
    assert app_key_grant_call in route_source
    assert vector_adapter_call in route_source
    assert vector_side_effect not in route_source[: route_source.index(vector_adapter_call)]
    assert (
        route_source.index(auth_context_dependency)
        < route_source.index(uid_from_context)
        < route_source.index(app_key_grant_call)
        < route_source.index(app_key_deny_check)
        < route_source.index(rollout_call)
        < route_source.index(vector_adapter_call)
    )


def test_developer_create_route_checks_split_brain_guard_before_legacy_write():
    memory_service_py = Path(__file__).resolve().parents[2] / 'utils' / 'memory' / 'memory_service.py'
    route_source = _function_source_for_route('/v1/dev/user/memories', 'post')
    service_contents = memory_service_py.read_text(encoding='utf-8')
    pin_call = 'pin_memory_system(uid, db_client=db)'
    external_create = '.create_external_memory('
    guard_call = 'guard_legacy_memory_write('
    assert pin_call in route_source
    assert external_create in route_source
    assert guard_call in service_contents
    assert route_source.index(pin_call) < route_source.index(external_create)


def test_developer_batch_create_route_checks_split_brain_guard_before_categorization_and_legacy_writes():
    memory_service_py = Path(__file__).resolve().parents[2] / 'utils' / 'memory' / 'memory_service.py'
    route_source = _function_source_for_route('/v1/dev/user/memories/batch', 'post')
    service_contents = memory_service_py.read_text(encoding='utf-8')
    pin_call = 'pin_memory_system(uid, db_client=db)'
    categorization = 'identify_category_for_memory(mem_req.content.strip())'
    external_batch = '.create_external_memory_batch('
    guard_call = 'guard_legacy_memory_write('
    legacy_write = 'memory_write_payload(memory, MemoryApiExposure.LEGACY)'
    vector_write = 'upsert_memory_vectors_batch('
    assert pin_call in route_source
    assert categorization in route_source
    assert external_batch in route_source
    assert guard_call in service_contents
    assert legacy_write in service_contents
    assert vector_write in service_contents
    assert route_source.index(categorization) < route_source.index(pin_call)
    assert route_source.index(pin_call) < route_source.index(external_batch)
    guard_index = service_contents.index(guard_call)
    assert guard_index < service_contents.index(legacy_write)
    assert service_contents.index(legacy_write) < service_contents.index(vector_write)


def test_developer_delete_route_checks_split_brain_guard_before_reads_and_legacy_delete():
    memory_service_py = Path(__file__).resolve().parents[2] / 'utils' / 'memory' / 'memory_service.py'
    route_source = _function_source_for_route('/v1/dev/user/memories/{memory_id}', 'delete')
    service_contents = memory_service_py.read_text(encoding='utf-8')
    pin_call = 'pin_memory_system(uid, db_client=db)'
    external_delete = '.delete_external_memory('
    guard_call = 'guard_legacy_memory_write('
    legacy_read = 'memory = memories_db.get_memory(uid, memory_id)'
    legacy_delete = 'memories_db.delete_memory(uid, memory_id)'
    assert pin_call in route_source
    assert external_delete in route_source
    assert guard_call in service_contents
    assert legacy_read in service_contents
    assert legacy_delete in service_contents
    assert route_source.index(pin_call) < route_source.index(external_delete)
    guard_index = service_contents.index(guard_call)
    assert guard_index < service_contents.index(legacy_read) < service_contents.index(legacy_delete)


def test_developer_update_route_checks_split_brain_guard_before_reads_and_legacy_mutations():
    route_source = _function_source_for_route('/v1/dev/user/memories/{memory_id}', 'patch')
    guard_call = 'guard_legacy_memory_write('
    legacy_read = 'memory = memories_db.get_memory(uid, memory_id)'
    legacy_edit = 'memories_db.edit_memory(uid, memory_id, request.content.strip())'
    legacy_update = 'memories_db.update_memory_fields(uid, memory_id, update_data)'
    assert guard_call in route_source
    assert legacy_read in route_source
    assert legacy_edit in route_source
    assert legacy_update in route_source
    guard_index = route_source.index(guard_call)
    assert guard_index < route_source.index(legacy_read)
    assert guard_index < route_source.index(legacy_edit) < route_source.index(legacy_update)


def test_developer_routes_only_reach_legacy_after_explicit_legacy_safe_decision():
    developer_py = Path(__file__).resolve().parents[2] / 'routers' / 'developer.py'
    contents = developer_py.read_text(encoding='utf-8')
    denied_check = 'if memory_result.read_decision in {MemoryReadDecision.DENY_MEMORY, MemoryReadDecision.SHADOW_ONLY}:'
    legacy_safe_check = 'if memory_result.should_use_legacy_fallback:'
    legacy_call = 'memories_db.get_memories(uid, limit, offset, [c.value for c in category_list])'
    assert denied_check in contents
    assert legacy_safe_check in contents
    assert legacy_call in contents
    assert contents.index(denied_check) < contents.index(legacy_safe_check) < contents.index(legacy_call)
    vector_route_source = _function_source_for_route('/v1/dev/user/memories/vector/search', 'get')
    assert vector_route_source.index(denied_check) < vector_route_source.index(legacy_safe_check)


def test_developer_category_filters_do_not_force_legacy_when_memory_can_decide_safely():
    developer_py = Path(__file__).resolve().parents[2] / 'routers' / 'developer.py'
    contents = developer_py.read_text(encoding='utf-8')
    category_legacy_reason = 'developer_category_legacy_safe_fallback_explicit'
    category_filter_argument = 'categories=[c.value for c in category_list]'
    assert category_filter_argument in contents
    assert category_legacy_reason not in contents


def test_developer_default_memory_adapter_filters_categories_without_legacy_fallback():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
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


def test_developer_rollout_reader_fails_closed_without_memory_item_reads_for_missing_malformed_or_grantless_state():
    missing = _FirestoreFake()
    assert (
        read_default_read_rollout(
            uid='u1', db_client=missing, consumer='developer_api'
        ).memory_default_developer_enabled
        is False
    )
    assert missing.collection_paths == []
    malformed = _FirestoreFake(
        {'users/u1/memory_control/state': {'schema_version': 1, 'uid': 'u1', 'mode': 'read', 'stage_gates': 'bad'}}
    )
    malformed_decision = read_default_read_rollout(uid='u1', db_client=malformed, consumer='developer_api')
    assert malformed_decision.memory_default_developer_enabled is False
    assert malformed_decision.app_has_default_memory_grant is False
    assert malformed.collection_paths == []
    no_grant = _FirestoreFake(
        {'users/u1/memory_control/state': _enabled_rollout_doc() | {'grants': {'developer_api': {}}}}
    )
    no_grant_decision = read_default_read_rollout(uid='u1', db_client=no_grant, consumer='developer_api')
    assert no_grant_decision.rollout_capabilities.memory_reads_enabled is True
    assert no_grant_decision.app_has_default_memory_grant is False
    assert no_grant_decision.memory_default_developer_enabled is False
    assert no_grant.collection_paths == []


def test_split_brain_guard_blocks_memory_enabled_developer_legacy_write_without_mutation():
    read_decision = read_default_read_rollout(
        uid='u1',
        db_client=_FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()}),
        consumer='developer_api',
    )
    decision = assert_legacy_memory_write_allowed_for_default_read_decision(read_decision, operation='create_memory')
    assert decision.allowed is False
    assert decision.status_code == 409
    assert decision.detail == {
        'enabled': False,
        'reason': 'memory_default_read_legacy_write_blocked',
        'consumer': 'developer_api',
        'operation': 'create_memory',
        'read_decision': MemoryReadDecision.USE_MEMORY.value,
        'source_path': 'users/u1/memory_control/state',
        'convergence_reason': None,
    }


def test_split_brain_guard_blocks_memory_enabled_developer_batch_create_without_mutation():
    read_decision = read_default_read_rollout(
        uid='u1',
        db_client=_FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()}),
        consumer='developer_api',
    )
    decision = assert_legacy_memory_write_allowed_for_default_read_decision(
        read_decision, operation='batch_create_memories'
    )
    assert decision.allowed is False
    assert decision.status_code == 409
    assert decision.detail['reason'] == 'memory_default_read_legacy_write_blocked'
    assert decision.detail['consumer'] == 'developer_api'
    assert decision.detail['operation'] == 'batch_create_memories'
    assert decision.detail['read_decision'] == MemoryReadDecision.USE_MEMORY.value


def test_split_brain_guard_blocks_memory_enabled_developer_edit_and_delete_without_mutation():
    read_decision = read_default_read_rollout(
        uid='u1',
        db_client=_FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()}),
        consumer='developer_api',
    )
    for operation in ['update_memory', 'delete_memory']:
        decision = assert_legacy_memory_write_allowed_for_default_read_decision(read_decision, operation=operation)
        assert decision.allowed is False
        assert decision.status_code == 409
        assert decision.detail['reason'] == 'memory_default_read_legacy_write_blocked'
        assert decision.detail['consumer'] == 'developer_api'
        assert decision.detail['operation'] == operation
        assert decision.detail['read_decision'] == MemoryReadDecision.USE_MEMORY.value


def test_split_brain_guard_blocks_missing_or_malformed_developer_config_fail_safe():
    missing = read_default_read_rollout(uid='u1', db_client=_FirestoreFake(), consumer='developer_api')
    malformed = read_default_read_rollout(
        uid='u1',
        db_client=_FirestoreFake(
            {'users/u1/memory_control/state': {'schema_version': 1, 'uid': 'u1', 'mode': 'read', 'stage_gates': 'bad'}}
        ),
        consumer='developer_api',
    )
    for read_decision in [missing, malformed]:
        decision = assert_legacy_memory_write_allowed_for_default_read_decision(
            read_decision, operation='create_memory'
        )
        assert decision.allowed is False
        assert decision.status_code == 409
        assert decision.detail['reason'] == 'memory_default_read_legacy_write_blocked'


def test_split_brain_guard_allows_disabled_but_blocks_when_convergence_policy_not_ready():
    disabled = read_default_read_rollout(
        uid='u1',
        db_client=_FirestoreFake(
            {'users/u1/memory_control/state': _enabled_rollout_doc() | {'mode': MemoryRolloutMode.off.value}}
        ),
        consumer='developer_api',
    )
    enabled = read_default_read_rollout(
        uid='u1',
        db_client=_FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()}),
        consumer='developer_api',
    )
    disabled_allowed = assert_legacy_memory_write_allowed_for_default_read_decision(disabled, operation='create_memory')
    not_ready_blocked = assert_legacy_memory_write_allowed_for_default_read_decision(
        enabled,
        operation='create_memory',
        write_convergence_policy=WriteConvergencePolicy(
            source_path='memory_control/write_convergence_gate', ready=False, reason='convergence_not_ready'
        ),
    )
    assert disabled_allowed.allowed is True
    assert not_ready_blocked.allowed is False
    assert not_ready_blocked.detail['convergence_reason'] == 'convergence_not_ready'


def test_developer_default_memory_adapter_uses_product_search_and_excludes_stale_short_term_and_archive():
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
    assert [item['id'] for item in results] == ['fresh-short-term', 'long-term']
    assert [item['content'] for item in results] == ['coffee fresh short term', 'coffee long term']
    assert all((item['category'] == 'other' for item in results))
    assert all((item['visibility'] == 'private' for item in results))
    assert all((item['memory_default_memory'] is True for item in results))
    assert all((item['archive_default_visible'] is False for item in results))
    assert all((item['policy']['consumer'] == 'developer_api' for item in results))
    assert all((item['policy']['archive_capability'] is False for item in results))


def test_developer_default_memory_adapter_excludes_pending_admission_text():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
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


def test_developer_default_memory_response_shape_marks_compatibility_defaults_without_silent_fabrication():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
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
    assert memory['visibility_source'] == 'memory_item.visibility'
    assert memory['category'] == 'other'
    assert memory['category_source'] == 'developer_memory_compatibility_default_no_source_category'
    assert memory['reviewed'] is False
    assert memory['reviewed_source'] == 'developer_memory_compatibility_default_no_review_state'
    assert memory['edited'] is False
    assert memory['edited_source'] == 'developer_memory_compatibility_default_no_edit_state'


def test_developer_default_memory_adapter_returns_denied_decision_when_rollout_or_grant_disabled_without_firestore_read():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    fresh_short_term = _memory_item('fresh-short-term', now=now, content='coffee fresh short term')
    db_client = _FirestoreFake({f'users/u1/memory_items/{fresh_short_term.memory_id}': _stored_item(fresh_short_term)})
    disabled_decision = read_default_read_rollout(
        uid='u1',
        db_client=_FirestoreFake(
            {'users/u1/memory_control/state': _enabled_rollout_doc() | {'mode': MemoryRolloutMode.off.value}}
        ),
        consumer='developer_api',
    )
    grantless_decision = read_default_read_rollout(
        uid='u1',
        db_client=_FirestoreFake(
            {'users/u1/memory_control/state': _enabled_rollout_doc() | {'grants': {'developer_api': {}}}}
        ),
        consumer='developer_api',
    )
    disabled_result = search_memory_default_developer_memories(
        uid='u1', query='coffee', limit=10, offset=0, db_client=db_client, rollout_decision=disabled_decision, now=now
    )
    grantless_result = search_memory_default_developer_memories(
        uid='u1', query='coffee', limit=10, offset=0, db_client=db_client, rollout_decision=grantless_decision, now=now
    )
    assert disabled_result.memories == []
    assert disabled_result.read_decision == MemoryReadDecision.DENY_MEMORY
    assert disabled_result.fallback_reason == 'memory_reads_disabled'
    assert grantless_result.memories == []
    assert grantless_result.read_decision == MemoryReadDecision.DENY_MEMORY
    assert grantless_result.fallback_reason == 'missing_developer_default_memory_grant'
    assert db_client.collection_paths == []


def test_developer_default_memory_adapter_classifies_explicit_legacy_safe_without_firestore_read():
    db_client = _FirestoreFake()
    legacy_safe = legacy_safe_default_read_rollout_decision(
        uid='u1',
        source_path='users/u1/memory_control/state',
        consumer='developer_api',
        reason='developer_category_legacy_safe_fallback_explicit',
    )
    result = search_memory_default_developer_memories(
        uid='u1', query='', limit=10, offset=0, db_client=db_client, rollout_decision=legacy_safe
    )
    assert result.memories == []
    assert result.read_decision == MemoryReadDecision.USE_LEGACY_SAFE
    assert result.fallback_reason == 'developer_category_legacy_safe_fallback_explicit'
    assert result.should_use_legacy_fallback is True
    assert db_client.collection_paths == []


def test_developer_vector_adapter_uses_hydrated_vector_service_and_preserves_ranking_without_archive_default():
    now = datetime.now(timezone.utc)
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
    assert [item['id'] for item in results] == ['long-term', 'fresh-short-term']
    assert [item['relevance_score'] for item in results] == [0.92, 0.8]
    assert all((item['memory_default_memory'] is True for item in results))
    assert all((item['archive_default_visible'] is False for item in results))
    assert all((item['policy']['consumer'] == 'developer_api' for item in results))
    assert all((item['policy']['archive_capability'] is False for item in results))


def test_developer_vector_adapter_returns_denied_decision_before_vector_or_memory_reads_when_rollout_or_grant_disabled():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    fresh_short_term = _memory_item('fresh-short-term', now=now, content='coffee fresh short term')
    db_client = _FirestoreFake({f'users/u1/memory_items/{fresh_short_term.memory_id}': _stored_item(fresh_short_term)})
    vector_calls = []

    def vector_query(uid, query, *, mode, limit):
        vector_calls.append({'uid': uid, 'query': query, 'mode': mode, 'limit': limit})
        return _VectorCandidateResult([_hit(fresh_short_term, score=0.9)])

    disabled_decision = read_default_read_rollout(
        uid='u1',
        db_client=_FirestoreFake(
            {'users/u1/memory_control/state': _enabled_rollout_doc() | {'mode': MemoryRolloutMode.off.value}}
        ),
        consumer='developer_api',
    )
    grantless_decision = read_default_read_rollout(
        uid='u1',
        db_client=_FirestoreFake(
            {'users/u1/memory_control/state': _enabled_rollout_doc() | {'grants': {'developer_api': {}}}}
        ),
        consumer='developer_api',
    )
    disabled_result = search_memory_default_developer_memories_vector(
        uid='u1',
        query='coffee',
        limit=10,
        db_client=db_client,
        rollout_decision=disabled_decision,
        vector_query=vector_query,
    )
    grantless_result = search_memory_default_developer_memories_vector(
        uid='u1',
        query='coffee',
        limit=10,
        db_client=db_client,
        rollout_decision=grantless_decision,
        vector_query=vector_query,
    )
    assert disabled_result.memories == []
    assert disabled_result.read_decision == MemoryReadDecision.DENY_MEMORY
    assert disabled_result.fallback_reason == 'memory_reads_disabled'
    assert grantless_result.memories == []
    assert grantless_result.read_decision == MemoryReadDecision.DENY_MEMORY
    assert grantless_result.fallback_reason == 'missing_developer_default_memory_grant'
    assert vector_calls == []
    assert db_client.collection_paths == []


def test_developer_vector_adapter_classifies_explicit_legacy_safe_without_vector_or_memory_reads():
    db_client = _FirestoreFake()
    vector_calls = []

    def vector_query(uid, query, *, mode, limit):
        vector_calls.append({'uid': uid, 'query': query, 'mode': mode, 'limit': limit})
        return _VectorCandidateResult([])

    legacy_safe = legacy_safe_default_read_rollout_decision(
        uid='u1',
        source_path='users/u1/memory_control/state',
        consumer='developer_api',
        reason='developer_vector_legacy_safe_fallback_explicit',
    )
    result = search_memory_default_developer_memories_vector(
        uid='u1', query='coffee', limit=10, db_client=db_client, rollout_decision=legacy_safe, vector_query=vector_query
    )
    assert result.memories == []
    assert result.read_decision == MemoryReadDecision.USE_LEGACY_SAFE
    assert result.fallback_reason == 'developer_vector_legacy_safe_fallback_explicit'
    assert result.should_use_legacy_fallback is True
    assert vector_calls == []
    assert db_client.collection_paths == []
