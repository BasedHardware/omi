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
