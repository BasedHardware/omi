"""Test that upsert_persona_from_twitter_profile offloads its blocking
Firestore writes to db_executor via run_blocking instead of calling the
sync functions directly on the event loop (issue #6369 async-blocker class).

Red without the fix: upsert_app_to_db / create_memories_from_twitter_tweets
are called directly (run_blocking never used for them).
Green with the fix: both are dispatched through run_blocking(db_executor, ...).
"""

import asyncio
import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

# Heavy/missing packages and the heavy intra-repo subtrees pulled in by
# utils.social. We deliberately keep the real `utils` parent package, the real
# `utils.executors`, and the real `utils.social` so the offload wiring under
# test executes for real; only the heavy leaves below are stubbed.
_STUB = (
    'database',
    'firebase_admin',
    'google',
    'pinecone',
    'opuslib',
    'pydub',
    'redis',
    'langchain',
    'langchain_core',
    'stripe',
    'openai',
    'anthropic',
    'modal',
    'ulid',
    'sentry_sdk',
    'requests',
    'typesense',
    'pusher',
    'models',
    'utils.llm',
    'utils.conversations',
)


def _is_stubbed(n):
    return any(n == p or n.startswith(p + '.') for p in _STUB)


class _AutoMock(types.ModuleType):
    __path__ = []

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        m = MagicMock()
        setattr(self, name, m)
        return m


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        return importlib.machinery.ModuleSpec(name, self, is_package=True) if _is_stubbed(name) else None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


_f = _Finder()
_saved = {n: m for n, m in sys.modules.items() if _is_stubbed(n)}
for n in list(sys.modules):
    if _is_stubbed(n):
        sys.modules.pop(n, None)
sys.meta_path.insert(0, _f)
try:
    from utils import social as mod
finally:
    sys.meta_path.remove(_f)
    for n in list(sys.modules):
        if _is_stubbed(n) and n not in _saved:
            sys.modules.pop(n, None)
    sys.modules.update(_saved)


def _make_timeline():
    tweet = mod.TwitterTweet(text='hello world', created_at='2024-01-01', id='t1')
    return mod.TwitterTimeline(timeline=[tweet])


class TestUpsertPersonaAsyncOffload:
    def test_upsert_app_to_db_offloaded_via_run_blocking(self):
        """upsert_app_to_db must be dispatched through run_blocking(db_executor, ...),
        not called directly on the event loop."""
        profile = mod.TwitterProfile(
            name='Jane',
            profile='jane',
            rest_id='1',
            avatar='https://x/a.jpg',
            desc='bio',
            friends=1,
            sub_count=2,
            id='1',
        )
        timeline = _make_timeline()

        captured = []

        async def _fake_run_blocking(executor, func, *args, **kwargs):
            captured.append(func)
            return func(*args, **kwargs)

        with patch.object(mod, 'run_blocking', side_effect=_fake_run_blocking) as run_blocking_mock, patch.object(
            mod, 'get_twitter_profile', new=AsyncMock(return_value=profile)
        ), patch.object(mod, 'get_twitter_timeline', new=AsyncMock(return_value=timeline)), patch.object(
            mod, '_create_or_update_persona', return_value={'id': 'p1', 'name': 'Jane'}
        ), patch.object(
            mod, 'generate_twitter_persona_prompt', return_value='prompt'
        ), patch.object(
            mod, 'upsert_app_to_db'
        ) as upsert_mock, patch.object(
            mod, 'create_memories_from_twitter_tweets'
        ) as memories_mock, patch.object(
            mod, 'save_username'
        ), patch.object(
            mod, 'delete_generic_cache'
        ):
            asyncio.run(mod.upsert_persona_from_twitter_profile('jane', 'jane', 'uid-1'))

        # run_blocking must have been used, and it must have wrapped the two
        # blocking Firestore-backed functions. Compare against the patched mock
        # objects themselves (the references that existed inside the `with`).
        assert run_blocking_mock.called, "run_blocking was never used (blocking calls run on the event loop)"
        assert upsert_mock in captured, "upsert_app_to_db was not offloaded via run_blocking"
        assert memories_mock in captured, "create_memories_from_twitter_tweets was not offloaded via run_blocking"

        # db_executor pool used for the upsert offload.
        executors_used = [call.args[0] for call in run_blocking_mock.call_args_list]
        assert mod.db_executor in executors_used

        # The functions still ran exactly once (offload, not skipped).
        upsert_mock.assert_called_once()
        memories_mock.assert_called_once()

    def test_blocking_fns_not_called_directly(self):
        """When run_blocking is a no-op (does NOT invoke func), the blocking fns
        must NOT have been called directly. This fails on unpatched code where
        the fns are invoked inline regardless of run_blocking."""
        profile = mod.TwitterProfile(
            name='Jane',
            profile='jane',
            rest_id='1',
            avatar='https://x/a.jpg',
            desc='bio',
            friends=1,
            sub_count=2,
            id='1',
        )
        timeline = _make_timeline()

        async def _noop_run_blocking(executor, func, *args, **kwargs):
            return None

        with patch.object(mod, 'run_blocking', side_effect=_noop_run_blocking), patch.object(
            mod, 'get_twitter_profile', new=AsyncMock(return_value=profile)
        ), patch.object(mod, 'get_twitter_timeline', new=AsyncMock(return_value=timeline)), patch.object(
            mod, '_create_or_update_persona', return_value={'id': 'p1', 'name': 'Jane'}
        ), patch.object(
            mod, 'generate_twitter_persona_prompt', return_value='prompt'
        ), patch.object(
            mod, 'upsert_app_to_db'
        ) as upsert_mock, patch.object(
            mod, 'create_memories_from_twitter_tweets'
        ) as memories_mock, patch.object(
            mod, 'save_username'
        ), patch.object(
            mod, 'delete_generic_cache'
        ):
            asyncio.run(mod.upsert_persona_from_twitter_profile('jane', 'jane', 'uid-1'))

        # Because run_blocking is a no-op here, the offloaded fns must not run.
        # On unpatched (buggy) code they are called inline -> these assertions fail.
        upsert_mock.assert_not_called()
        memories_mock.assert_not_called()
