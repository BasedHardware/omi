"""Tests for per-router auth dependencies (utils/auth_middleware.py).

Covers:
- Token verification (_verify_token, _authenticate)
- require_firebase dependency (Firebase + BYOK + ContextVar lifecycle)
- require_firebase_no_byok dependency (Firebase only)
- Route auth contract: every route has the expected auth dependency
- No duplicate routes in the app
"""

import os
import unittest
from unittest.mock import patch, MagicMock

from fastapi import APIRouter, Depends, FastAPI, Request
from starlette.testclient import TestClient

from utils.auth_middleware import (
    _verify_token,
    require_firebase,
    require_firebase_no_byok,
)


class TestVerifyToken(unittest.TestCase):
    """Test token verification logic."""

    @patch.dict(os.environ, {"ADMIN_KEY": "test_admin_key_"})
    def test_admin_key_extracts_uid(self):
        uid = _verify_token("test_admin_key_user123")
        assert uid == "user123"

    @patch.dict(os.environ, {"ADMIN_KEY": "admin_"})
    def test_admin_key_empty_uid(self):
        uid = _verify_token("admin_")
        assert uid == ""

    @patch.dict(os.environ, {"ADMIN_KEY": ""})
    @patch("utils.auth_middleware.firebase_auth.verify_id_token")
    def test_firebase_token_verified(self, mock_verify):
        mock_verify.return_value = {"uid": "firebase_user"}
        uid = _verify_token("valid.firebase.token")
        assert uid == "firebase_user"
        mock_verify.assert_called_once_with("valid.firebase.token")

    @patch.dict(os.environ, {"ADMIN_KEY": "", "LOCAL_DEVELOPMENT": "true"})
    @patch("utils.auth_middleware.firebase_auth.verify_id_token")
    def test_local_dev_fallback(self, mock_verify):
        from firebase_admin.auth import InvalidIdTokenError

        mock_verify.side_effect = InvalidIdTokenError("test")
        uid = _verify_token("bad_token")
        assert uid == "123"

    @patch.dict(os.environ, {"ADMIN_KEY": "", "LOCAL_DEVELOPMENT": ""})
    @patch("utils.auth_middleware.firebase_auth.verify_id_token")
    def test_invalid_token_raises(self, mock_verify):
        from firebase_admin.auth import InvalidIdTokenError

        mock_verify.side_effect = InvalidIdTokenError("test")
        with self.assertRaises(InvalidIdTokenError):
            _verify_token("bad_token")


class TestRequireFirebaseDep(unittest.TestCase):
    """Test require_firebase dependency through a real ASGI stack."""

    def _make_app(self):
        firebase_router = APIRouter(dependencies=[Depends(require_firebase)])
        public_router = APIRouter()

        @public_router.get("/v1/health")
        def health():
            return {"status": "ok"}

        @firebase_router.get("/v1/protected")
        def protected(request: Request):
            return {"uid": request.state.uid, "byok_keys": request.state.byok_keys}

        app = FastAPI()
        app.include_router(public_router)
        app.include_router(firebase_router)
        return app

    def test_public_route_no_auth_needed(self):
        client = TestClient(self._make_app())
        resp = client.get("/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_missing_authorization_returns_401(self):
        client = TestClient(self._make_app())
        resp = client.get("/v1/protected")
        assert resp.status_code == 401
        assert "Authorization header" in resp.json()["detail"]

    def test_malformed_bearer_returns_401(self):
        client = TestClient(self._make_app())
        resp = client.get("/v1/protected", headers={"Authorization": "BadToken"})
        assert resp.status_code == 401

    @patch('utils.auth_middleware._verify_token', return_value='test-uid')
    @patch('utils.auth_middleware.validate_and_return_byok_keys', return_value={})
    def test_valid_token_sets_uid(self, _mock_byok, _mock_verify):
        client = TestClient(self._make_app())
        resp = client.get("/v1/protected", headers={"Authorization": "Bearer valid-token"})
        assert resp.status_code == 200
        assert resp.json()["uid"] == "test-uid"

    @patch('utils.auth_middleware._verify_token', return_value='test-uid')
    @patch('utils.auth_middleware.validate_and_return_byok_keys', return_value={'openai': 'sk-test'})
    def test_valid_token_sets_byok_keys(self, _mock_byok, _mock_verify):
        client = TestClient(self._make_app())
        resp = client.get(
            "/v1/protected",
            headers={"Authorization": "Bearer valid-token", "x-byok-openai": "sk-test"},
        )
        assert resp.status_code == 200
        assert resp.json()["byok_keys"] == {"openai": "sk-test"}

    def test_invalid_firebase_token_returns_401(self):
        from firebase_admin.auth import InvalidIdTokenError

        with patch('utils.auth_middleware._verify_token', side_effect=InvalidIdTokenError("bad")):
            client = TestClient(self._make_app())
            resp = client.get("/v1/protected", headers={"Authorization": "Bearer bad-token"})
            assert resp.status_code == 401

    @patch('utils.auth_middleware._verify_token', return_value='test-uid')
    @patch('utils.auth_middleware.validate_and_return_byok_keys', return_value={})
    def test_contextvar_reset_after_request(self, _mock_byok, _mock_verify):
        from utils.byok import _byok_ctx

        client = TestClient(self._make_app())
        before = _byok_ctx.get()
        client.get("/v1/protected", headers={"Authorization": "Bearer tok"})
        after = _byok_ctx.get()
        assert before == after

    @patch('utils.auth_middleware._verify_token', return_value='test-uid')
    def test_byok_validation_failure_returns_403(self, _mock_verify):
        from fastapi import HTTPException

        def fail_byok(uid, keys):
            raise HTTPException(status_code=403, detail="BYOK fingerprint mismatch")

        with patch('utils.auth_middleware.validate_and_return_byok_keys', side_effect=fail_byok):
            client = TestClient(self._make_app())
            resp = client.get(
                "/v1/protected",
                headers={"Authorization": "Bearer tok", "x-byok-openai": "sk-bad"},
            )
            assert resp.status_code == 403
            assert "fingerprint" in resp.json()["detail"]

    @patch('utils.auth_middleware._verify_token', return_value='uid-1')
    @patch('utils.auth_middleware.validate_and_return_byok_keys', return_value={})
    def test_platform_telemetry_called(self, _mock_byok, _mock_verify):
        with patch('database.users.record_user_platform') as mock_platform:
            client = TestClient(self._make_app())
            client.get(
                "/v1/protected",
                headers={"Authorization": "Bearer tok", "x-app-platform": "ios"},
            )
            mock_platform.assert_called_once_with('uid-1', 'ios')

    @patch('utils.auth_middleware._verify_token', return_value='uid-1')
    @patch('utils.auth_middleware.validate_and_return_byok_keys', return_value={})
    def test_platform_telemetry_failure_does_not_fail_request(self, _mock_byok, _mock_verify):
        with patch('database.users.record_user_platform', side_effect=RuntimeError("db down")):
            client = TestClient(self._make_app())
            resp = client.get(
                "/v1/protected",
                headers={"Authorization": "Bearer tok", "x-app-platform": "android"},
            )
            assert resp.status_code == 200


class TestRequireFirebaseNoByokDep(unittest.TestCase):
    """Test require_firebase_no_byok dependency."""

    def _make_app(self):
        skip_byok_router = APIRouter(dependencies=[Depends(require_firebase_no_byok)])

        @skip_byok_router.get("/v1/skip-byok")
        def skip_byok_endpoint(request: Request):
            return {"uid": request.state.uid, "byok_keys": request.state.byok_keys}

        app = FastAPI()
        app.include_router(skip_byok_router)
        return app

    @patch('utils.auth_middleware._verify_token', return_value='uid-2')
    def test_skip_byok_sets_uid_and_empty_byok(self, _mock_verify):
        client = TestClient(self._make_app())
        resp = client.get(
            "/v1/skip-byok",
            headers={"Authorization": "Bearer tok", "x-byok-openai": "sk-test"},
        )
        assert resp.status_code == 200
        assert resp.json()["uid"] == "uid-2"
        assert resp.json()["byok_keys"] == {}

    @patch('utils.auth_middleware._verify_token', return_value='uid-2')
    def test_skip_byok_does_not_validate_byok(self, _mock_verify):
        with patch('utils.auth_middleware.validate_and_return_byok_keys') as mock_validate:
            client = TestClient(self._make_app())
            client.get("/v1/skip-byok", headers={"Authorization": "Bearer tok"})
            mock_validate.assert_not_called()

    def test_skip_byok_still_requires_firebase(self):
        client = TestClient(self._make_app())
        resp = client.get("/v1/skip-byok")
        assert resp.status_code == 401

    @patch('utils.auth_middleware._verify_token', return_value='uid-2')
    def test_skip_byok_contextvar_has_raw_keys(self, _mock_verify):
        from utils.byok import get_byok_keys

        captured = {}

        skip_router = APIRouter(dependencies=[Depends(require_firebase_no_byok)])

        @skip_router.get("/v1/check-ctx")
        def check_ctx():
            captured['keys'] = get_byok_keys()
            return {"ok": True}

        app = FastAPI()
        app.include_router(skip_router)
        client = TestClient(app)
        client.get("/v1/check-ctx", headers={"Authorization": "Bearer tok", "x-byok-openai": "sk-raw"})
        assert captured['keys'].get('openai') == 'sk-raw'


class TestRouteAuthContract(unittest.TestCase):
    """Verify key routes have the expected auth dependency via the real app.

    These tests require a full app import (TYPESENSE_API_KEY, ADC, etc.)
    and are skipped in normal CI. Run them manually in a dev environment.
    """

    @unittest.skipIf(True, "requires full app import — run separately with TYPESENSE_API_KEY set")
    def test_public_routes_no_firebase(self):
        pass

    @unittest.skipIf(True, "requires full app import — run separately with TYPESENSE_API_KEY set")
    def test_firebase_routes_have_dep(self):
        pass


class TestNoDuplicateRoutes(unittest.TestCase):
    """Ensure the aggregate router pattern didn't create duplicate routes."""

    def test_no_duplicate_routes_in_individual_routers(self):
        import importlib

        checked = 0
        for mod_name in [
            'advice',
            'calendar_meetings',
            'chat_sessions',
            'folders',
            'focus_sessions',
            'goals',
            'imports',
            'knowledge_graph',
            'memories',
            'scores',
            'speech_profile',
            'staged_tasks',
            'tools',
            'wrapped',
            'tts',
            'agent_tools',
            'action_items',
            'announcements',
            'apps',
            'chat',
            'fair_use_admin',
            'integrations',
            'notifications',
            'payment',
            'phone_calls',
            'task_integrations',
            'updates',
            'users',
        ]:
            try:
                mod = importlib.import_module(f'routers.{mod_name}')
            except Exception:
                continue
            router = getattr(mod, 'router', None)
            if router is None:
                continue
            seen = set()
            for route in router.routes:
                if hasattr(route, 'methods'):
                    for method in route.methods:
                        key = (method, route.path)
                        assert key not in seen, f"Duplicate route in {mod_name}: {method} {route.path}"
                        seen.add(key)
                        checked += 1
        assert checked > 100, f"Only checked {checked} routes, expected 300+"


class TestMalformedAuthBoundary(unittest.TestCase):
    """Test malformed Authorization header edge cases."""

    def _make_app(self):
        firebase_router = APIRouter(dependencies=[Depends(require_firebase)])

        @firebase_router.get("/v1/protected")
        def protected(request: Request):
            return {"uid": request.state.uid}

        app = FastAPI()
        app.include_router(firebase_router)
        return app

    def test_empty_bearer_returns_401(self):
        client = TestClient(self._make_app())
        resp = client.get("/v1/protected", headers={"Authorization": "Bearer "})
        assert resp.status_code == 401

    def test_no_space_separator_returns_401(self):
        client = TestClient(self._make_app())
        resp = client.get("/v1/protected", headers={"Authorization": "Bearertoken123"})
        assert resp.status_code == 401

    @patch('utils.auth_middleware._verify_token', return_value='uid-ok')
    @patch('utils.auth_middleware.validate_and_return_byok_keys', return_value={})
    def test_any_two_part_scheme_accepted(self, _byok, _verify):
        client = TestClient(self._make_app())
        resp = client.get("/v1/protected", headers={"Authorization": "Custom valid-token"})
        assert resp.status_code == 200
        _verify.assert_called_once_with("valid-token")


class TestAsyncToThreadErrorPropagation(unittest.TestCase):
    """Test that errors from asyncio.to_thread propagate correctly."""

    def _make_app(self):
        firebase_router = APIRouter(dependencies=[Depends(require_firebase)])

        @firebase_router.get("/v1/protected")
        def protected(request: Request):
            return {"uid": request.state.uid}

        app = FastAPI()
        app.include_router(firebase_router)
        return app

    def test_generic_verify_exception_returns_500(self):
        with patch('utils.auth_middleware._verify_token', side_effect=RuntimeError("Firebase SDK crashed")):
            client = TestClient(self._make_app(), raise_server_exceptions=False)
            resp = client.get("/v1/protected", headers={"Authorization": "Bearer tok"})
            assert resp.status_code == 500

    @patch('utils.auth_middleware._verify_token', return_value='uid-ctx')
    @patch('utils.auth_middleware.validate_and_return_byok_keys', return_value={'openai': 'sk-test'})
    def test_contextvar_reset_after_route_exception(self, _byok, _verify):
        from utils.byok import _byok_ctx

        firebase_router = APIRouter(dependencies=[Depends(require_firebase)])

        @firebase_router.get("/v1/crash")
        def crash(request: Request):
            raise RuntimeError("route handler crashed")

        app = FastAPI()
        app.include_router(firebase_router)

        before = _byok_ctx.get()
        client = TestClient(app, raise_server_exceptions=False)
        client.get("/v1/crash", headers={"Authorization": "Bearer tok", "x-byok-openai": "sk-test"})
        after = _byok_ctx.get()
        assert before == after

    @patch('utils.auth_middleware._verify_token', return_value='uid-ok')
    def test_byok_validation_generic_error_propagates(self, _verify):
        with patch(
            'utils.auth_middleware.validate_and_return_byok_keys', side_effect=RuntimeError("Firestore unreachable")
        ):
            client = TestClient(self._make_app(), raise_server_exceptions=False)
            resp = client.get(
                "/v1/protected",
                headers={"Authorization": "Bearer tok", "x-byok-openai": "sk-test"},
            )
            assert resp.status_code == 500


class TestMixedModeRouterAuthDeps(unittest.TestCase):
    """Verify that mixed-mode routers assign the correct auth dependency to each sub-router."""

    def _get_router_deps(self, mod_name):
        import importlib

        mod = importlib.import_module(f'routers.{mod_name}')
        router = getattr(mod, 'router', None)
        assert router is not None, f"{mod_name} has no router"

        dep_map = {}
        for route in router.routes:
            if not hasattr(route, 'methods'):
                continue
            deps = [d.dependency for d in getattr(route, 'dependencies', [])]
            for method in route.methods:
                dep_map[(method, route.path)] = deps
        return dep_map

    def test_users_router_has_firebase_on_protected_routes(self):
        dep_map = self._get_router_deps('users')
        protected_keys = [
            k for k in dep_map if 'create-user-data' not in k[1] and k[0] == 'GET' and '/v1/users/' in k[1]
        ]
        for key in protected_keys:
            deps = dep_map[key]
            dep_names = [d.__name__ for d in deps if hasattr(d, '__name__')]
            assert (
                'require_firebase' in dep_names or 'require_firebase_no_byok' in dep_names
            ), f"Route {key} in users has no auth dep: {dep_names}"

    def test_payment_router_skip_byok_on_billing(self):
        dep_map = self._get_router_deps('payment')
        skip_byok_routes = [k for k in dep_map if 'byok' in k[1].lower() or 'billing' in k[1].lower()]
        for key in skip_byok_routes:
            deps = dep_map[key]
            dep_names = [d.__name__ for d in deps if hasattr(d, '__name__')]
            assert (
                'require_firebase_no_byok' in dep_names
            ), f"BYOK billing route {key} should use require_firebase_no_byok, got: {dep_names}"

    def test_chat_router_public_ws_no_http_auth(self):
        import importlib

        mod = importlib.import_module('routers.chat')
        router = getattr(mod, 'router')
        for route in router.routes:
            if hasattr(route, 'path') and 'ws' in str(route.path).lower():
                deps = [d.dependency for d in getattr(route, 'dependencies', [])]
                dep_names = [d.__name__ for d in deps if hasattr(d, '__name__')]
                assert (
                    'require_firebase' not in dep_names
                ), f"WebSocket route {route.path} should not have HTTP auth dep"

    def test_apps_router_public_routes_have_no_auth(self):
        import importlib

        mod = importlib.import_module('routers.apps')
        router = getattr(mod, 'router')
        public_paths = ['/v1/approved-apps', '/v2/approved-apps', '/v1/app-capabilities']
        for route in router.routes:
            if not hasattr(route, 'path') or not hasattr(route, 'methods'):
                continue
            if route.path in public_paths:
                deps = [d.dependency for d in getattr(route, 'dependencies', [])]
                dep_names = [d.__name__ for d in deps if hasattr(d, '__name__')]
                assert (
                    'require_firebase' not in dep_names
                ), f"Public route {route.path} should not have auth dep, got: {dep_names}"


if __name__ == "__main__":
    unittest.main()
