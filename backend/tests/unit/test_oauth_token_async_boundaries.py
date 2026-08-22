import asyncio
import threading
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Iterator

import pytest
from fastapi import HTTPException

from testing.import_isolation import load_module_fresh, stub_modules
from tests.auth_fakes import FakeAuthProvider
from utils.auth.errors import InvalidToken
from utils.auth.ports import Principal

BACKEND_DIR = Path(__file__).resolve().parents[2]
# The bearers the harness accepts. Two, because ``_loaded_oauth_router`` is SHARED:
# tests/unit/test_oauth_firebase_backend_gate.py imports it and posts 'firebase-token'. Registering only
# this file's own token turned that neighbour red — caught by the full sweep, not by the suite I was
# editing, which is precisely why the sweep runs before every commit.
ACCEPTED_TOKENS = ('token', 'firebase-token')
TOKEN = ACCEPTED_TOKENS[0]


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
    # Bare module + the exception CLASS the firebase adapter names at import time. No behaviour: these
    # tests drive the neutral port (see ``_install_provider``), so a stubbed ``verify_id_token`` would be
    # describing a call path they no longer take.
    firebase_auth = _module('firebase_admin.auth', InvalidIdTokenError=_InvalidIdTokenError)
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
    endpoints = _module(
        'utils.other.endpoints',
        enforce_account_deletion_http_access=lambda _uid: None,
    )

    with stub_modules(
        {
            'firebase_admin': firebase_admin,
            'firebase_admin.auth': firebase_auth,
            'database.apps': apps_db,
            'database.redis_db': redis_db,
            'utils.apps': apps,
            'utils.http_client': http_client,
            'utils.other.endpoints': endpoints,
            'models.app': app_model,
        }
    ):
        oauth = load_module_fresh('routers.oauth', str(BACKEND_DIR / 'routers' / 'oauth.py'))
        yield oauth, _install_provider(oauth), apps_db


def _install_provider(oauth: ModuleType) -> Any:
    """Put a NEUTRAL provider behind the route, and assert it is really the one the route resolves.

    What these tests hold is where the auth verification RUNS (an owned executor, off the event loop) and
    what the route does with a rejection — neither of which is Firebase-specific. Driving them by stubbing
    ``firebase_admin.auth`` left the port crossed only by the Firebase adapter, which is BACKLOG L15: an
    OIDC deployment blocks the loop on a JWKS fetch in exactly the same place, and nothing here would have
    noticed. The adapter's own SDK-exception translation is covered separately, in
    tests/unit/test_firebase_translate_unknown_error.py.
    """
    fake = FakeAuthProvider()
    for bearer in ACCEPTED_TOKENS:
        fake.register(bearer, Principal(uid='user-1'))
    oauth.get_auth_provider = lambda: fake
    # Assert the seam rather than trust it: if the router stops binding the name at module level, this
    # assignment reaches nothing and the tests quietly go back to whatever the real provider does.
    assert oauth.get_auth_provider() is fake
    return fake


def test_oauth_token_routes_auth_and_app_reads_to_owned_executors() -> None:
    with _loaded_oauth_router() as (oauth, provider, apps_db):
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
        # Auth verification offloads the neutral provider's verify_token — the bound method of the one
        # provider instance, so identity comparison is stable and backend-independent.
        assert [(executor, func) for executor, func, _args in calls] == [
            (oauth.critical_executor, provider.verify_token),
            (oauth.db_executor, oauth.enforce_account_deletion_http_access),
            (oauth.db_executor, apps_db.get_app_by_id_db),
            (oauth.db_executor, oauth.is_user_app_enabled),
        ]


def test_oauth_token_verification_keeps_the_event_loop_responsive() -> None:
    with _loaded_oauth_router() as (oauth, provider, _apps_db):

        async def exercise() -> None:
            entered = asyncio.Event()
            release = threading.Event()
            loop = asyncio.get_running_loop()

            loop_thread = threading.get_ident()
            ran_on: list[int] = []

            def blocking_verify(_token: str, **_kw: Any) -> Principal:
                ran_on.append(threading.get_ident())
                loop.call_soon_threadsafe(entered.set)
                assert release.wait(timeout=2)
                return Principal(uid='user-1')

            # Blocking inside the PROVIDER, not inside a Firebase stub: on OIDC the same place blocks on
            # a JWKS fetch, and the offload has to hold there too.
            provider.verify_token = blocking_verify
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
            # Where the call ran, stated exactly rather than inferred from a timeout.
            assert ran_on and ran_on[0] != loop_thread, 'token verification ran on the event loop thread'

        asyncio.run(exercise())


def test_oauth_token_preserves_invalid_token_status() -> None:
    with _loaded_oauth_router() as (oauth, provider, _apps_db):
        # A rejection stated in the NEUTRAL taxonomy: what the route must do with it is the same whichever
        # adapter produced it. (SDK-exception -> InvalidToken translation is the adapter's own test.)
        provider.register_error('bad', InvalidToken('invalid'))

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
        # Neutralized message is backend-agnostic ("sign-in token"), not firebase-specific.
        assert 'Invalid sign-in token' in exc.value.detail
