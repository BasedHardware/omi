"""Tests that get_relevant_memories offloads the blocking Firestore read.

utils/llm/notifications.py runs inside async notification flows. The
get_memories() Firestore read must be offloaded to db_executor via
run_blocking instead of being called directly on the event loop.
Red (pre-fix): get_memories is called directly and run_blocking is never used.
Green (post-fix): run_blocking(db_executor, get_memories, uid, limit) is used.
"""

import asyncio
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub the heavy LLM/Firestore siblings of the module under test before
# importing it. utils.llm is kept a real package (so the real notifications.py
# submodule resolves) and utils.executors is kept real (pure stdlib); only the
# heavy leaf modules clients / usage_tracker / database.memories are stubbed.
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def _ensure_real_package(name, path):
    module = sys.modules.get(name)
    if not isinstance(module, types.ModuleType) or not hasattr(module, '__path__'):
        module = types.ModuleType(name)
        sys.modules[name] = module
    module.__path__ = [path]
    return module


_ensure_real_package('utils', os.path.join(_BACKEND_DIR, 'utils'))
_ensure_real_package('utils.llm', os.path.join(_BACKEND_DIR, 'utils', 'llm'))

_clients_mod = types.ModuleType('utils.llm.clients')
_clients_mod.get_llm = MagicMock()
sys.modules.setdefault('utils.llm.clients', _clients_mod)

_usage_mod = types.ModuleType('utils.llm.usage_tracker')
_usage_mod.track_usage = MagicMock()
_usage_mod.Features = MagicMock()
sys.modules.setdefault('utils.llm.usage_tracker', _usage_mod)

_memories_db = types.ModuleType('database.memories')
_memories_db.get_memories = MagicMock(return_value=[])
sys.modules.setdefault('database.memories', _memories_db)

import utils.llm.notifications as notifications_mod


class TestGetRelevantMemoriesAsync:
    """get_relevant_memories must not call the sync Firestore read on the loop."""

    def test_offloads_get_memories_via_run_blocking(self):
        sample = [{'content': 'a', 'is_locked': False}, {'content': 'b', 'is_locked': True}]

        async def _fake_run_blocking(executor, fn, *args, **kwargs):
            return fn(*args, **kwargs)

        mock_run_blocking = MagicMock(side_effect=_fake_run_blocking)

        # create=True so the patch applies whether or not the offload symbols
        # already exist on the module (pre-fix they are absent), turning a
        # missing offload into a clean assertion failure rather than a patch error.
        with patch.object(notifications_mod, 'run_blocking', mock_run_blocking, create=True), patch.object(
            notifications_mod, 'get_memories', return_value=sample
        ) as mock_get_memories:
            result = asyncio.run(notifications_mod.get_relevant_memories('u1'))

        # The blocking read must be offloaded exactly once via run_blocking,
        # rather than get_memories being awaited/called directly on the loop.
        # Pre-fix, run_blocking is never called (call_count == 0) -> this fails.
        assert mock_run_blocking.call_count == 1
        call_args = mock_run_blocking.call_args
        # The function handed to run_blocking must be get_memories itself.
        assert call_args.args[1] is mock_get_memories
        # db_executor is passed as the pool.
        assert call_args.args[0] is notifications_mod.db_executor
        # uid and limit are forwarded positionally.
        assert call_args.args[2] == 'u1'
        assert call_args.args[3] == 100
        # Locked memories are filtered out.
        assert result == [{'content': 'a', 'is_locked': False}]

    def test_passes_explicit_limit_to_run_blocking(self):
        async def _fake_run_blocking(executor, fn, *args, **kwargs):
            return fn(*args, **kwargs)

        mock_run_blocking = MagicMock(side_effect=_fake_run_blocking)

        with patch.object(notifications_mod, 'run_blocking', mock_run_blocking, create=True), patch.object(
            notifications_mod, 'get_memories', return_value=[]
        ):
            asyncio.run(notifications_mod.get_relevant_memories('u1', limit=50))

        assert mock_run_blocking.call_count == 1
        assert mock_run_blocking.call_args.args[3] == 50
