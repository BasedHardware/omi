import asyncio
import threading
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Iterator

import pytest
from fastapi import HTTPException

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _module(name: str, **attributes: Any) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


class _InvalidIdTokenError(Exception):
    pass


class _App:
    def __init__(self, **values: Any):
        self.id = values.get('id', 'app-1')
        self.name = values.get('name', 'Test App')
        self.image = None
        self.capabilities = []
        self.private = False
        self.uid = None
        self.is_paid = False
        self.external_integration = SimpleNamespace(
            app_home_url='https://app.test/complete',
            setup_completed_url=None,
            actions=[],
            triggers_on=None,
        )
        self.proactive_notification = None

    def works_externally(self) -> bool:
        return False


@contextmanager
def _loaded_oauth_router() -> Iterator[tuple[ModuleType, ModuleType, ModuleType]]:
    firebase_auth = _module(
        'firebase_admin.auth',
        # Accept **kwargs: the neutral FirebaseAuthProvider calls verify_id_token(bearer,
        # check_revoked=...) (ADR-0034), so a single-arg stub raises TypeError -> InvalidToken -> 401.
        verify_id_token=lambda _token, **_kwargs: {'uid': 'user-1'},
        InvalidIdTokenError=_InvalidIdTokenError,
    )
    firebase_admin = _module('firebase_admin', auth=firebase_auth)
    firebase_admin.__path__ = []  # type: ignore[attr-defined]
    apps_db = _module('database.apps', get_app_by_id_db=lambda _app_id: {'id': 'app-1'})
    redis_db = _module(
        'database.redis_db',
        enable_app=lambda _uid, _app_id: None,
        increase_app_installs_count=lambda _app_id: None,
    )
    apps = _module(
        'utils.apps',
        is_user_app_enabled=lambda _uid, _app_id: True,
        get_is_user_paid_app=lambda _app_id, _uid: True,
        is_tester=lambda _uid: False,
    )
    app_model = _module(
        'models.app',
        App=_App,
        ActionType=SimpleNamespace(
            CREATE_MEMORY=SimpleNamespace(value='create_memory'),
            CREATE_FACTS=SimpleNamespace(value='create_facts'),
            READ_CONVERSATIONS=SimpleNamespace(value='read_conversations'),
            READ_MEMORIES=SimpleNamespace(value='read_memories'),
            READ_TASKS=SimpleNamespace(value='read_tasks'),
        ),
    )

    class _UnsafeWebhookURLError(Exception):
        pass

    http_client = _module(
        'utils.http_client',
        get_auth_client=lambda: None,
        # Passthrough: none of this file's tests exercise the setup_completed_url
        # branch (default is_user_app_enabled=True skips it), so this only needs
        # to satisfy the import and match safe_request_target's (url, extra) shape.
        safe_request_target=lambda url: (url, {'headers': {}, 'extensions': {}}),
        UnsafeWebhookURLError=_UnsafeWebhookURLError,
    )

    with stub_modules(
        {
            'firebase_admin': firebase_admin,
            'firebase_admin.auth': firebase_auth,
            'database.apps': apps_db,
            'database.redis_db': redis_db,
            'utils.apps': apps,
            'utils.http_client': http_client,
            'models.app': app_model,
        }
    ):
        oauth = load_module_fresh('routers.oauth', str(BACKEND_DIR / 'routers' / 'oauth.py'))
        yield oauth, firebase_auth, apps_db


def test_oauth_token_routes_auth_and_app_reads_to_owned_executors() -> None:
    with _loaded_oauth_router() as (oauth, firebase_auth, apps_db):
        calls: list[tuple[Any, Any, tuple[Any, ...]]] = []

        async def tracking_run_blocking(executor: Any, func: Any, *args: Any, **kwargs: Any) -> Any:
            calls.append((executor, func, args))
            return func(*args, **kwargs)

        oauth.run_blocking = tracking_run_blocking

        result = asyncio.run(
            oauth.oauth_token(
                firebase_id_token='token',
                app_id='app-1',
                state='opaque',
                csrf_token='matching-csrf-token',
                oauth_csrf_cookie='matching-csrf-token',
            )
        )

        assert result == {
            'uid': 'user-1',
            'redirect_url': 'https://app.test/complete',
            'state': 'opaque',
        }
        # Auth verification is offloaded to the critical executor — now the neutral port's verify_token
        # (oauth.py goes through utils.auth, ADR-0034), not the raw firebase SDK function. Compare by
        # function name so the assertion is identity-agnostic while still pinning each executor boundary.
        assert [(executor, getattr(func, '__name__', '')) for executor, func, _args in calls] == [
            (oauth.critical_executor, 'verify_token'),
            (oauth.db_executor, apps_db.get_app_by_id_db.__name__),
            (oauth.db_executor, oauth.is_user_app_enabled.__name__),
        ]


def test_oauth_token_verification_keeps_the_event_loop_responsive() -> None:
    with _loaded_oauth_router() as (oauth, firebase_auth, _apps_db):

        async def exercise() -> None:
            entered = asyncio.Event()
            release = threading.Event()
            loop = asyncio.get_running_loop()

            def blocking_verify(_token: str, **_kwargs) -> dict[str, str]:
                # **_kwargs: the neutral port passes check_revoked= through to the firebase SDK call.
                loop.call_soon_threadsafe(entered.set)
                assert release.wait(timeout=2)
                return {'uid': 'user-1'}

            firebase_auth.verify_id_token = blocking_verify
            task = asyncio.create_task(
                oauth.oauth_token(
                    firebase_id_token='token',
                    app_id='app-1',
                    csrf_token='matching-csrf-token',
                    oauth_csrf_cookie='matching-csrf-token',
                )
            )
            try:
                await asyncio.wait_for(entered.wait(), timeout=2)
                tick = asyncio.Event()
                loop.call_soon(tick.set)
                await asyncio.wait_for(tick.wait(), timeout=1)
                assert not task.done()
            finally:
                release.set()

            assert (await asyncio.wait_for(task, timeout=2))['uid'] == 'user-1'

        asyncio.run(exercise())


def test_oauth_token_preserves_invalid_token_status() -> None:
    with _loaded_oauth_router() as (oauth, firebase_auth, _apps_db):
        firebase_auth.verify_id_token = lambda _token: (_ for _ in ()).throw(_InvalidIdTokenError('invalid'))

        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                oauth.oauth_token(
                    firebase_id_token='bad',
                    app_id='app-1',
                    csrf_token='matching-csrf-token',
                    oauth_csrf_cookie='matching-csrf-token',
                )
            )

        assert exc.value.status_code == 401
        assert 'Invalid sign-in token' in exc.value.detail
