"""Regression test: the async fair-use classifier must offload its blocking
Firestore read off the event loop.

`classify_user_purpose` is an ``async def`` but `_prepare_conversation_summaries`
runs the synchronous Firestore SDK (`database.conversations.get_conversations`).
Calling it directly blocks the event loop. The fix offloads it via
``await run_blocking(db_executor, _prepare_conversation_summaries, uid)`` from
``utils.executors``.

This test drives ``classify_user_purpose`` with ``run_blocking`` and
``_prepare_conversation_summaries`` patched, and asserts the summaries are
produced through ``run_blocking`` (i.e. offloaded) rather than by a direct
in-loop call.

Without the fix, ``run_blocking`` is never invoked -> the assertions fail (RED).
"""

import json
import sys
import types
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub heavy dependencies before importing the module under test
# ---------------------------------------------------------------------------
_db_client = types.ModuleType('database._client')
_db_client.db = MagicMock()
sys.modules.setdefault('database._client', _db_client)

_redis_mod = types.ModuleType('database.redis_db')
_redis_mod.r = MagicMock()
sys.modules.setdefault('database.redis_db', _redis_mod)

sys.modules.setdefault('google.cloud.firestore', MagicMock())
sys.modules.setdefault('google.cloud.firestore_v1', MagicMock())

# Stub database.conversations (the blocking Firestore read lives here)
_conversations_db = types.ModuleType('database.conversations')
_conversations_db.get_conversations = MagicMock(return_value=[])
sys.modules.setdefault('database.conversations', _conversations_db)

# Stub llm clients
_llm_clients = types.ModuleType('utils.llm.clients')
_llm_clients.llm_mini = MagicMock()
sys.modules.setdefault('utils.llm.clients', _llm_clients)

_langchain_openai = types.ModuleType('langchain_openai')
_langchain_openai.ChatOpenAI = MagicMock(return_value=_llm_clients.llm_mini)
sys.modules['langchain_openai'] = _langchain_openai

_USAGE_TRACKER_MODULE = 'utils.llm.usage_tracker'
_original_usage_tracker = sys.modules.get(_USAGE_TRACKER_MODULE)
_usage_tracker = types.ModuleType('utils.llm.usage_tracker')
_usage_tracker.get_usage_callback = MagicMock(return_value=MagicMock())
sys.modules[_USAGE_TRACKER_MODULE] = _usage_tracker

try:
    import utils.llm.fair_use_classifier as classifier_mod
finally:
    if _original_usage_tracker is None:
        sys.modules.pop(_USAGE_TRACKER_MODULE, None)
    else:
        sys.modules[_USAGE_TRACKER_MODULE] = _original_usage_tracker

_classifier_llm = classifier_mod._classifier_llm


class TestClassifierOffloadsBlockingRead:
    """`classify_user_purpose` must offload `_prepare_conversation_summaries`
    via `run_blocking(db_executor, ...)` instead of calling it on the loop."""

    @pytest.mark.asyncio
    async def test_prepare_summaries_is_offloaded_via_run_blocking(self):
        sentinel_summaries = [{'conversation_id': 'c1', 'title': 'Meeting', 'duration_minutes': 30}]

        async def fake_run_blocking(executor, fn, *args, **kwargs):
            # run_blocking offloads `fn` to a thread pool; emulate the result.
            return fn(*args, **kwargs)

        # Make the underlying sync function return our sentinel so we can verify
        # the offloaded result is what flows into the rest of classify_user_purpose.
        prep_mock = MagicMock(return_value=sentinel_summaries)

        llm_response = MagicMock()
        llm_response.content = json.dumps(
            {'misuse_score': 0.1, 'usage_type': 'none', 'confidence': 0.9, 'evidence': [], 'reasoning': 'ok'}
        )
        _classifier_llm.ainvoke = AsyncMock(return_value=llm_response)

        with patch.object(
            classifier_mod, 'run_blocking', side_effect=fake_run_blocking
        ) as mock_run_blocking, patch.object(classifier_mod, '_prepare_conversation_summaries', prep_mock):
            result = await classifier_mod.classify_user_purpose('user1')

        # The blocking read MUST be performed through run_blocking (offloaded),
        # on the db_executor pool, with the uid as the argument.
        assert mock_run_blocking.call_count == 1, "blocking Firestore read was not offloaded via run_blocking"
        call_args = mock_run_blocking.call_args.args
        assert call_args[0] is classifier_mod.db_executor, "must offload onto db_executor"
        # The function reference passed to run_blocking is the (patched) summaries fn.
        assert call_args[1] is prep_mock, "run_blocking must wrap _prepare_conversation_summaries"
        assert call_args[2] == 'user1', "uid must be passed through to the offloaded call"

        # And the function must keep working end-to-end through the offloaded result.
        assert result['usage_type'] == 'none'
        prep_mock.assert_called_once_with('user1')

    @pytest.mark.asyncio
    async def test_offloaded_empty_summaries_short_circuits(self):
        """When the offloaded read yields nothing, the classifier returns the
        default result without ever calling the LLM -- proving the offloaded
        value is the one actually consumed."""

        async def fake_run_blocking(executor, fn, *args, **kwargs):
            return fn(*args, **kwargs)

        _classifier_llm.ainvoke = AsyncMock()  # must NOT be awaited

        with patch.object(
            classifier_mod, 'run_blocking', side_effect=fake_run_blocking
        ) as mock_run_blocking, patch.object(
            classifier_mod, '_prepare_conversation_summaries', MagicMock(return_value=[])
        ):
            result = await classifier_mod.classify_user_purpose('user2')

        mock_run_blocking.assert_called_once()
        assert result['misuse_score'] == 0.0
        assert result['usage_type'] == 'none'
        _classifier_llm.ainvoke.assert_not_called()
