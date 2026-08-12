import sys
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.unit.memory_import_isolation import restore_sys_modules, snapshot_sys_modules

_MODULE_NAMES = ('routers.memory_platform', 'utils.other.endpoints')


def _auth_stub() -> types.ModuleType:
    module = types.ModuleType('utils.other.endpoints')
    module.get_current_user_uid = lambda: 'test-user'

    # `with_rate_limit` has to be stubbed too. Omitting it made
    # `_rate_limited_uid` silently fall back to the unrated dependency, so the
    # search route's rate-limit wiring was never exercised by any test here.
    def _with_rate_limit(dependency, policy_name):
        wrapped = lambda: dependency()  # noqa: E731 - keeps the wrapper a distinct callable
        wrapped.rate_limit_policy = policy_name
        wrapped.wrapped_dependency = dependency
        return wrapped

    module.with_rate_limit = _with_rate_limit
    return module


@pytest.fixture(scope='module')
def memory_platform_router():
    saved = snapshot_sys_modules(_MODULE_NAMES)
    auth_module = _auth_stub()
    sys.modules.pop('routers.memory_platform', None)
    sys.modules['utils.other.endpoints'] = auth_module
    other_package = sys.modules.get('utils.other')
    if isinstance(other_package, types.ModuleType):
        other_package.endpoints = auth_module
    try:
        import routers.memory_platform as module

        yield module
    finally:
        restore_sys_modules(saved)


def test_memory_platform_router_registers_authenticated_get(memory_platform_router):
    routes = [route for route in memory_platform_router.router.routes if route.path == '/v1/memory/platform']

    assert len(routes) == 1
    route = routes[0]
    assert route.methods == {'GET'}
    assert route.response_model is memory_platform_router.MemoryPlatformCapability
    assert [dependency.call for dependency in route.dependant.dependencies] == [
        memory_platform_router.auth.get_current_user_uid
    ]


def test_memory_platform_route_returns_stable_secret_free_response(memory_platform_router):
    app = FastAPI()
    app.include_router(memory_platform_router.router)
    app.dependency_overrides[memory_platform_router.auth.get_current_user_uid] = lambda: 'test-user'

    response = TestClient(app).get('/v1/memory/platform')

    assert response.status_code == 200
    assert response.json() == {
        'authority': 'omi_backend',
        'canonical_store': {
            'kind': 'firestore',
            'collection': 'memory_items',
            'apply_control': 'memory_state/apply_control',
        },
        'surfaces': {'rest': 'GET /v1/memory/platform', 'mcp': 'memory_platform'},
        'zkr': {
            'export_format': 1,
            'replica_role': 'mirror',
            'write_mode': 'backend_ingest',
            'sync_implemented': False,
        },
    }
    assert 'secret' not in response.text.lower()
    assert 'credential' not in response.text.lower()


def _client(memory_platform_router):
    app = FastAPI()
    app.include_router(memory_platform_router.router)
    app.dependency_overrides[memory_platform_router.auth.get_current_user_uid] = lambda: 'test-user'
    # Metered routes depend on the rate-limited wrapper, not on the bare uid
    # dependency, so each wrapper needs its own override to reach the handler.
    for route in app.routes:
        for dependency in getattr(getattr(route, 'dependant', None), 'dependencies', []):
            if getattr(dependency.call, 'rate_limit_policy', None) is not None:
                app.dependency_overrides[dependency.call] = lambda: 'test-user'
    return TestClient(app)


def test_metered_search_depends_on_the_rate_limited_uid(memory_platform_router):
    """The search route must be metered by `tools:search`, not the bare uid dependency."""
    routes = [route for route in memory_platform_router.router.routes if route.path == '/v1/memory/platform/search']

    assert len(routes) == 1
    policies = [getattr(dependency.call, 'rate_limit_policy', None) for dependency in routes[0].dependant.dependencies]
    assert policies == ['tools:search']


def test_quota_route_exposes_remaining_platform_allowance(memory_platform_router, monkeypatch):
    monkeypatch.setattr(
        memory_platform_router,
        'get_platform_quota_snapshot',
        lambda _uid: {
            'plan': 'Free',
            'plan_type': 'basic',
            'used': 4,
            'limit': 1000,
            'remaining': 996,
            'allowed': True,
            'reset_at': 1780000000,
        },
    )

    response = _client(memory_platform_router).get('/v1/memory/platform/quota')

    assert response.status_code == 200
    assert response.json() == {
        'plan': 'Free',
        'plan_type': 'basic',
        'unit': 'requests',
        'used': 4,
        'limit': 1000,
        'remaining': 996,
        'allowed': True,
        'reset_at': 1780000000,
    }


def test_search_over_quota_returns_429_naming_the_plan(memory_platform_router, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(memory_platform_router, 'get_firestore_client', lambda: object())
    monkeypatch.setattr(
        memory_platform_router,
        '_require_product_authorization',
        lambda _uid, _db: types.SimpleNamespace(policy=object(), global_gate=object(), observability={}),
    )

    def _over_quota(_uid):
        raise HTTPException(
            status_code=429,
            detail={'error': 'platform_quota_exceeded', 'plan_type': 'basic', 'limit': 1000},
        )

    monkeypatch.setattr(memory_platform_router, 'enforce_platform_quota', _over_quota)

    response = _client(memory_platform_router).get('/v1/memory/platform/search')

    assert response.status_code == 429
    assert response.json()['detail']['plan_type'] == 'basic'
    assert response.json()['detail']['limit'] == 1000


@pytest.mark.parametrize(
    'params',
    [
        {'query': 'x' * 501},
        {'limit': '0'},
        {'limit': '100000'},
        {'offset': '-1'},
        {'offset': '100001'},
    ],
)
def test_search_returns_the_documented_400_for_invalid_bounds(memory_platform_router, monkeypatch, params):
    """Invalid bounds must 400 over real HTTP, not FastAPI's framework 422.

    Declaring the bounds as Query constraints made FastAPI reject the request
    before the handler ran, so the published contract promised a 400 that no real
    client could ever observe.
    """
    monkeypatch.setattr(memory_platform_router, 'get_firestore_client', lambda: object())

    response = _client(memory_platform_router).get('/v1/memory/platform/search', params=params)

    assert response.status_code == 400
    assert 'must be' in str(response.json()['detail'])


def _rollout_observability() -> dict:
    """A real ProductRolloutObservability payload, dumped the way the route emits it."""
    from models.memory_admin import ReadRolloutCapabilities
    from models.memory_product import ProductRolloutObservability

    return ProductRolloutObservability(
        consumer='omi_chat',
        enabled=True,
        reason='memory_reads_enabled',
        read_decision='USE_MEMORY',
        mode='memory_authoritative',
        memory_reads_enabled=True,
        legacy_reads_authoritative=False,
        default_memory_grant=True,
        archive_default_visible=False,
        archive_capability=False,
        fallback_reason=None,
        capabilities=ReadRolloutCapabilities(
            legacy_only=False,
            shadow_artifacts_enabled=False,
            memory_writes_enabled=True,
            memory_reads_enabled=True,
            legacy_reads_authoritative=False,
        ),
        surface='platform_search',
        archive_capability_required=False,
        archive_capability_granted=False,
        explicit_archive_request=False,
        app_context={},
    ).model_dump(mode='json')


def _seeded_search_client(memory_platform_router, monkeypatch):
    """Wire the route to a Firestore fake holding one default-visible memory item.

    Everything from `fetch_default_product_memory_search` outward is production
    code, so the response goes through FastAPI's real `response_model`
    serialization — which is exactly where issue #11438 failed.
    """
    from datetime import datetime, timezone

    from models.product_memory import MemoryAccessPolicy
    from tests.unit.test_product_memory_read_service import _FirestoreFake, _memory_item, _stored_item

    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    item = _memory_item('m1', now=now, content='coffee fresh short term', uid='test-user')
    db_client = _FirestoreFake({'users/test-user/memory_items/m1': _stored_item(item)})

    monkeypatch.setattr(memory_platform_router, 'get_firestore_client', lambda: db_client)
    monkeypatch.setattr(memory_platform_router, '_current_time', lambda: now)
    monkeypatch.setattr(memory_platform_router, 'enforce_platform_quota', lambda _uid: None)
    gate = types.SimpleNamespace(
        source_path='memory_state/read_gate',
        read_decision=types.SimpleNamespace(value='USE_MEMORY'),
        fallback_reason=None,
        reason='memory_reads_enabled',
    )
    monkeypatch.setattr(
        memory_platform_router,
        '_require_product_authorization',
        lambda _uid, _db: types.SimpleNamespace(
            policy=MemoryAccessPolicy.for_omi_chat(),
            global_gate=gate,
            observability=_rollout_observability(),
        ),
    )
    return _client(memory_platform_router)


def test_search_serializes_a_non_empty_page_of_real_projections(memory_platform_router, monkeypatch):
    """Regression for #11438: any matching row used to 500 on response validation.

    The read service returns product projections (`memory_id`, `date`,
    `agent_use`, ...), not authoritative `MemoryItem` documents. While
    `ProductMemorySearchResponse.items` was declared as `List[MemoryItem]`, an
    empty page serialized fine and every non-empty page raised
    `ResponseValidationError`, so the endpoint 500'd on all real data.
    """
    client = _seeded_search_client(memory_platform_router, monkeypatch)

    empty = client.get('/v1/memory/platform/search', params={'query': 'zzzznomatch', 'limit': 20, 'offset': 0})
    assert empty.status_code == 200
    assert empty.json()['items'] == []

    response = client.get('/v1/memory/platform/search', params={'query': 'coffee', 'limit': 20, 'offset': 0})

    assert response.status_code == 200
    body = response.json()
    assert body['total_count'] == 1
    assert body['returned_count'] == 1
    assert [row['memory_id'] for row in body['items']] == ['m1']
    row = body['items'][0]
    assert row['content'] == 'coffee fresh short term'
    assert row['tier'] == 'short_term'
    assert row['memory_layer'] == 'product_memory'
    assert row['agent_use'] == 'default_access_memory'
    assert row['date'] == '2026-06-18T12:00:00+00:00'
    # The projection must not leak the authoritative storage fields.
    assert 'uid' not in row
    assert 'sensitivity_labels' not in row
