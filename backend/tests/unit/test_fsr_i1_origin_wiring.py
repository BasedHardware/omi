"""I1: origin decorators keep FastAPI's original dependency signatures visible."""

import inspect

import pytest
from fastapi.routing import APIRoute

import desktop_backend
import llm_gateway.main as llm_gateway_main
import pusher.main as pusher_main
from database.firestore_tier_context import FirestoreTierMiddleware
from routers import candidate_integration_sweep, dream_sweep, feedback_admin, sync
from utils.cloud_tasks import verify_cloud_tasks_oidc


def _route(router, path: str) -> APIRoute:
    return next(route for route in router.routes if isinstance(route, APIRoute) and route.path == path)


@pytest.mark.parametrize(
    'router,path,dependency_name,dependency',
    [
        (
            sync.router,
            '/v2/sync-backfill-sequencer/sweep',
            '_retry_count',
            verify_cloud_tasks_oidc,
        ),
        (
            dream_sweep.router,
            '/v2/dream-agent/canary',
            '_retry_count',
            verify_cloud_tasks_oidc,
        ),
        (
            dream_sweep.router,
            '/v2/dream-agent/sweep',
            '_retry_count',
            verify_cloud_tasks_oidc,
        ),
        (
            candidate_integration_sweep.router,
            '/v2/candidate-integrations/sweep',
            '_retry_count',
            verify_cloud_tasks_oidc,
        ),
        (
            feedback_admin.router,
            '/v1/admin/feedback/reports/{report_date}/generate',
            'admin_id',
            feedback_admin._verify_admin_key,
        ),
        (
            feedback_admin.router,
            '/v1/admin/feedback/reports/generate-yesterday',
            'admin_id',
            feedback_admin._verify_admin_key,
        ),
    ],
)
def test_origin_decorated_route_preserves_dependency_signature(router, path, dependency_name, dependency):
    route = _route(router, path)
    parameter = inspect.signature(route.endpoint).parameters[dependency_name]

    assert parameter.default.dependency is dependency
    assert any(item.name == dependency_name and item.call is dependency for item in route.dependant.dependencies)


def test_owned_asgi_entrypoints_install_firestore_tier_middleware():
    apps = (pusher_main.app, desktop_backend._build_app(), llm_gateway_main.app)
    assert all(any(middleware.cls is FirestoreTierMiddleware for middleware in app.user_middleware) for app in apps)
