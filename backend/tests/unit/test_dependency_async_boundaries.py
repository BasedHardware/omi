import asyncio
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Iterator, Optional

import pytest
from fastapi import HTTPException

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _module(name: str, **attributes: Any) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


class _ProductAuthorizationContext:
    def __init__(self, **values: Any):
        self.__dict__.update(values)


@dataclass(frozen=True)
class _McpVerifiedAuth:
    uid: str
    app_id: Optional[str] = None
    key_id: Optional[str] = None
    scopes: tuple[str, ...] = ()


def _build_mcp_context(auth: _McpVerifiedAuth, *, surface: str) -> _ProductAuthorizationContext:
    return _ProductAuthorizationContext(
        uid=auth.uid,
        consumer='mcp',
        surface=surface,
        app_id=auth.app_id,
        key_id=auth.key_id,
        scopes=auth.scopes,
    )


@contextmanager
def _loaded_dependencies() -> Iterator[tuple[ModuleType, ModuleType, ModuleType, ModuleType]]:
    firebase_auth = _module('firebase_admin.auth', verify_id_token=lambda _token: {'uid': 'user-1'})
    mcp_api_key_db = _module(
        'database.mcp_api_key',
        get_api_key_auth_result=lambda _token: SimpleNamespace(context=None, repairs=frozenset()),
    )
    dev_api_key_db = _module(
        'database.dev_api_key',
        get_api_key_auth_result=lambda _token: SimpleNamespace(context=None, repairs=frozenset()),
    )
    endpoints = _module('utils.other.endpoints', check_api_key_rate_limit=lambda **_kwargs: None)
    mcp_memories = _module(
        'utils.mcp_memories',
        McpVerifiedAuth=_McpVerifiedAuth,
        build_mcp_default_memory_read_context=lambda auth: _build_mcp_context(auth, surface='mcp_default_memory_read'),
        build_mcp_default_memory_write_context=lambda auth: _build_mcp_context(
            auth, surface='mcp_default_memory_write'
        ),
    )
    product_authorization = _module(
        'utils.memory.product_authorization',
        ProductAuthorizationContext=_ProductAuthorizationContext,
    )

    with stub_modules(
        {
            'firebase_admin.auth': firebase_auth,
            'database.mcp_api_key': mcp_api_key_db,
            'database.dev_api_key': dev_api_key_db,
            'utils.other.endpoints': endpoints,
            'utils.mcp_memories': mcp_memories,
            'utils.memory.product_authorization': product_authorization,
        }
    ):
        dependencies = load_module_fresh('dependencies', str(BACKEND_DIR / 'dependencies.py'))
        yield dependencies, firebase_auth, mcp_api_key_db, dev_api_key_db


async def _assert_loop_responsive_while_worker_waits(
    awaitable: Any,
    entered: asyncio.Event,
    release: threading.Event,
) -> Any:
    task = asyncio.create_task(awaitable)
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        loop_tick = asyncio.Event()
        asyncio.get_running_loop().call_soon(loop_tick.set)
        await asyncio.wait_for(loop_tick.wait(), timeout=1)
        assert not task.done()
    finally:
        release.set()
    return await asyncio.wait_for(task, timeout=2)


def test_firebase_verification_uses_the_critical_executor() -> None:
    with _loaded_dependencies() as (dependencies, firebase_auth, _mcp_db, _dev_db):
        calls: list[tuple[Any, Any, tuple[Any, ...], dict[str, Any]]] = []

        def verify_id_token(token: str) -> dict[str, str]:
            assert token == 'firebase-token'
            return {'uid': 'user-1'}

        async def tracking_run_blocking(executor: Any, fn: Any, *args: Any, **kwargs: Any) -> Any:
            calls.append((executor, fn, args, kwargs))
            return fn(*args, **kwargs)

        firebase_auth.verify_id_token = verify_id_token
        dependencies.run_blocking = tracking_run_blocking

        result = asyncio.run(dependencies.get_current_user_id(SimpleNamespace(credentials='firebase-token')))

        assert result == 'user-1'
        assert calls == [(dependencies.critical_executor, verify_id_token, ('firebase-token',), {})]


def test_mcp_and_developer_key_lookups_use_the_critical_executor() -> None:
    with _loaded_dependencies() as (dependencies, _firebase_auth, mcp_api_key_db, dev_api_key_db):
        calls: list[tuple[Any, Any, tuple[Any, ...], dict[str, Any]]] = []
        rate_limit_calls: list[dict[str, Any]] = []

        def lookup_mcp(token: str) -> SimpleNamespace:
            assert token == 'omi_mcp_secret'
            return SimpleNamespace(
                context={'user_id': 'mcp-user', 'scopes': [], 'app_id': 'mcp-app', 'key_id': 'mcp-key'},
                repairs=frozenset(),
            )

        def lookup_dev(token: str) -> SimpleNamespace:
            assert token == 'omi_dev_secret'
            return SimpleNamespace(
                context={'user_id': 'dev-user', 'scopes': [], 'app_id': 'dev-app', 'key_id': 'dev-key'},
                repairs=frozenset(),
            )

        def check_rate_limit(**kwargs: Any) -> None:
            rate_limit_calls.append(kwargs)

        async def tracking_run_blocking(executor: Any, fn: Any, *args: Any, **kwargs: Any) -> Any:
            calls.append((executor, fn, args, kwargs))
            return fn(*args, **kwargs)

        mcp_api_key_db.get_api_key_auth_result = lookup_mcp
        dev_api_key_db.get_api_key_auth_result = lookup_dev
        dependencies.check_api_key_rate_limit = check_rate_limit
        dependencies.run_blocking = tracking_run_blocking

        mcp_uid = asyncio.run(dependencies.get_uid_from_mcp_api_key('Bearer omi_mcp_secret'))
        dev_auth = asyncio.run(dependencies.get_api_key_auth('Bearer omi_dev_secret'))

        assert mcp_uid == 'mcp-user'
        assert dev_auth.uid == 'dev-user'
        assert [(executor, fn) for executor, fn, _args, _kwargs in calls] == [
            (dependencies.critical_executor, lookup_mcp),
            (dependencies.critical_executor, check_rate_limit),
            (dependencies.critical_executor, lookup_dev),
        ]
        assert rate_limit_calls == [
            {
                'prefix': 'mcp',
                'uid': 'mcp-user',
                'app_id': 'mcp-app',
                'key_id': 'mcp-key',
                'policy_name': 'mcp:read',
            }
        ]


def test_auth_repair_metadata_is_emitted_from_the_dependency_layer() -> None:
    with _loaded_dependencies() as (dependencies, _firebase_auth, mcp_api_key_db, _dev_db):
        mcp_api_key_db.get_api_key_auth_result = lambda _token: SimpleNamespace(
            context={'user_id': 'mcp-user', 'scopes': [], 'app_id': 'mcp-app', 'key_id': 'mcp-key'},
            repairs=frozenset({'cache_write'}),
        )
        events: list[dict[str, Any]] = []
        dependencies.record_api_key_repairs = lambda **kwargs: events.append(kwargs)

        auth = asyncio.run(dependencies.get_mcp_api_key_auth('Bearer omi_mcp_secret'))

        assert auth.uid == 'mcp-user'
        assert events == [
            {
                'key_kind': 'mcp',
                'operation': 'auth',
                'repairs': frozenset({'cache_write'}),
                'log': dependencies.logger,
            }
        ]


def test_all_api_key_scope_dependencies_route_rate_limits_through_the_critical_executor() -> None:
    with _loaded_dependencies() as (dependencies, _firebase_auth, _mcp_db, _dev_db):
        executor_calls: list[tuple[Any, Any]] = []
        policies: list[str] = []

        def check_rate_limit(**kwargs: Any) -> None:
            policies.append(kwargs['policy_name'])

        async def tracking_run_blocking(executor: Any, fn: Any, *args: Any, **kwargs: Any) -> Any:
            executor_calls.append((executor, fn))
            return fn(*args, **kwargs)

        dependencies.check_api_key_rate_limit = check_rate_limit
        dependencies.run_blocking = tracking_run_blocking
        auth = dependencies.ApiKeyAuth(
            uid='user-1',
            scopes=[
                'memories.read',
                'memories.write',
                dependencies.Scopes.CONVERSATIONS_READ,
                dependencies.Scopes.CONVERSATIONS_WRITE,
                dependencies.Scopes.MEMORIES_READ,
                dependencies.Scopes.MEMORIES_WRITE,
                dependencies.Scopes.ACTION_ITEMS_READ,
                dependencies.Scopes.ACTION_ITEMS_WRITE,
                dependencies.Scopes.GOALS_READ,
                dependencies.Scopes.GOALS_WRITE,
            ],
            app_id='app-1',
            key_id='key-1',
        )

        async def exercise() -> None:
            assert (await dependencies.get_mcp_memory_default_memory_read_context(auth)).surface == (
                'mcp_default_memory_read'
            )
            assert (await dependencies.get_mcp_memory_default_memory_write_context(auth)).surface == (
                'mcp_default_memory_write'
            )
            assert await dependencies.get_auth_with_conversations_read(auth) is auth
            assert await dependencies.get_auth_with_conversation_detail_read(auth) is auth
            assert await dependencies.get_auth_with_conversations_write(auth) is auth
            assert await dependencies.get_auth_with_memories_read(auth) is auth
            assert await dependencies.get_auth_with_memories_write(auth) is auth
            assert await dependencies.get_auth_with_action_items_read(auth) is auth
            assert await dependencies.get_auth_with_action_items_write(auth) is auth
            assert await dependencies.get_auth_with_goals_read(auth) is auth
            assert await dependencies.get_auth_with_goals_write(auth) is auth

            read_context = await dependencies.get_developer_memory_default_memory_read_context(auth)
            assert read_context.surface == 'developer_default_memory_read'
            write_context = dependencies.get_developer_memory_default_memory_write_auth_context(auth)
            assert write_context.surface == 'developer_default_memory_write'
            assert await dependencies.get_developer_memory_default_memory_write_context(write_context) is write_context
            assert (
                await dependencies.get_developer_memory_default_memory_batch_write_context(write_context)
                is write_context
            )

        asyncio.run(exercise())

        assert policies == [
            'mcp:memories_read',
            'mcp:memories_write',
            'dev:conversations_read',
            'dev:conversation_detail_read',
            'dev:conversations',
            'dev:memories_read',
            'dev:memories',
            'dev:action_items_read',
            'dev:action_items_write',
            'dev:goals_read',
            'dev:goals_write',
            'dev:memories_read',
            'dev:memories',
            'dev:memories_batch',
        ]
        assert len(executor_calls) == len(policies)
        assert all(executor is dependencies.critical_executor for executor, _fn in executor_calls)
        assert {fn for _executor, fn in executor_calls} == {
            check_rate_limit,
            dependencies._check_dev_api_key_rate_limit,
        }


def test_firebase_verification_keeps_the_event_loop_responsive() -> None:
    with _loaded_dependencies() as (dependencies, firebase_auth, _mcp_db, _dev_db):

        async def exercise() -> None:
            entered = asyncio.Event()
            release = threading.Event()
            loop = asyncio.get_running_loop()

            def blocking_verify(_token: str) -> dict[str, str]:
                loop.call_soon_threadsafe(entered.set)
                assert release.wait(timeout=2)
                return {'uid': 'user-1'}

            firebase_auth.verify_id_token = blocking_verify
            safety_release = threading.Timer(1, release.set)
            safety_release.start()
            try:
                result = await _assert_loop_responsive_while_worker_waits(
                    dependencies.get_current_user_id(SimpleNamespace(credentials='firebase-token')),
                    entered,
                    release,
                )
            finally:
                safety_release.cancel()

            assert result == 'user-1'

        asyncio.run(exercise())


def test_persisted_api_key_lookup_keeps_the_event_loop_responsive() -> None:
    with _loaded_dependencies() as (dependencies, _firebase_auth, mcp_api_key_db, _dev_db):

        async def exercise() -> None:
            entered = asyncio.Event()
            release = threading.Event()
            loop = asyncio.get_running_loop()

            def blocking_lookup(_token: str) -> SimpleNamespace:
                loop.call_soon_threadsafe(entered.set)
                assert release.wait(timeout=2)
                return SimpleNamespace(
                    context={'user_id': 'user-1', 'scopes': [], 'app_id': 'app-1', 'key_id': 'key-1'},
                    repairs=frozenset(),
                )

            mcp_api_key_db.get_api_key_auth_result = blocking_lookup
            dependencies.check_api_key_rate_limit = lambda **_kwargs: None
            safety_release = threading.Timer(1, release.set)
            safety_release.start()
            try:
                result = await _assert_loop_responsive_while_worker_waits(
                    dependencies.get_uid_from_mcp_api_key('Bearer omi_mcp_secret'),
                    entered,
                    release,
                )
            finally:
                safety_release.cancel()

            assert result == 'user-1'

        asyncio.run(exercise())


def test_api_key_rate_limit_keeps_the_event_loop_responsive_and_propagates_http_errors() -> None:
    with _loaded_dependencies() as (dependencies, _firebase_auth, _mcp_db, _dev_db):
        auth = dependencies.ApiKeyAuth(
            uid='user-1',
            scopes=[dependencies.Scopes.ACTION_ITEMS_WRITE],
            app_id='app-1',
            key_id='key-1',
        )

        async def exercise_responsiveness() -> None:
            entered = asyncio.Event()
            release = threading.Event()
            loop = asyncio.get_running_loop()

            def blocking_rate_limit(**_kwargs: Any) -> None:
                loop.call_soon_threadsafe(entered.set)
                assert release.wait(timeout=2)

            dependencies.check_api_key_rate_limit = blocking_rate_limit
            safety_release = threading.Timer(1, release.set)
            safety_release.start()
            try:
                result = await _assert_loop_responsive_while_worker_waits(
                    dependencies.get_auth_with_action_items_write(auth),
                    entered,
                    release,
                )
            finally:
                safety_release.cancel()

            assert result is auth

        asyncio.run(exercise_responsiveness())

        def reject_rate_limit(**_kwargs: Any) -> None:
            raise HTTPException(status_code=429, detail='rate limited')

        dependencies.check_api_key_rate_limit = reject_rate_limit
        with pytest.raises(HTTPException) as exc:
            asyncio.run(dependencies.get_auth_with_action_items_write(auth))
        assert exc.value.status_code == 429
        assert exc.value.detail == 'rate limited'


def test_authentication_and_scope_failures_preserve_public_http_semantics() -> None:
    with _loaded_dependencies() as (dependencies, firebase_auth, _mcp_db, _dev_db):
        firebase_auth.verify_id_token = lambda _token: (_ for _ in ()).throw(ValueError('invalid token'))
        with pytest.raises(HTTPException) as firebase_exc:
            asyncio.run(dependencies.get_current_user_id(SimpleNamespace(credentials='bad-token')))
        assert firebase_exc.value.status_code == 401
        assert firebase_exc.value.detail == 'Invalid authentication credentials'

        with pytest.raises(HTTPException) as header_exc:
            asyncio.run(dependencies.get_api_key_auth('not-a-bearer-token'))
        assert header_exc.value.status_code == 401
        assert "Must be 'Bearer API_KEY'" in header_exc.value.detail

        no_scope = dependencies.ApiKeyAuth(uid='user-1', scopes=[], app_id='app-1', key_id='key-1')
        dependencies.check_api_key_rate_limit = lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError('scope failure must happen before rate limiting')
        )
        with pytest.raises(HTTPException) as scope_exc:
            asyncio.run(dependencies.get_auth_with_goals_write(no_scope))
        assert scope_exc.value.status_code == 403
        assert dependencies.Scopes.GOALS_WRITE in scope_exc.value.detail
