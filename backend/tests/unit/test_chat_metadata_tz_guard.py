"""
Regression test for the timezone guard in chat metadata extraction
(utils/llm/chat.py :: retrieve_metadata_fields_from_transcript).

The prompt was built with `created_at.astimezone(ZoneInfo(tz))` directly inside
the f-string, OUTSIDE the try/except that wraps the LLM call. An invalid (or
None) timezone made `ZoneInfo(tz)` raise BEFORE the LLM call, so the function
blew up with an unhandled exception instead of degrading to empty metadata.

Fix: resolve the timezone defensively (mirroring _local_started_at_iso /
extract_action_items), falling back to UTC, before building the prompt.

This test drives the function with an invalid / None timezone and asserts it
does NOT raise and returns the empty-metadata shape.

Red (without fix): ZoneInfoNotFoundError / TypeError escapes the function.
Green (with fix): returns {'people': [], 'topics': [], 'entities': [], 'dates': []}.
"""

import contextlib
import os
import sys
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

# ---------------------------------------------------------------------------
# Stub the heavy dependencies that utils/llm/chat.py imports, BEFORE importing
# the module under test. We deliberately do NOT stub the `utils` / `utils.llm`
# packages themselves, so the real chat.py loads as real code.
# (Mirrors tests/unit/test_fair_use_classifier.py, a sibling in utils/llm/.)
# ---------------------------------------------------------------------------


def _stub(name):
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)
    return sys.modules[name]


_db_client = _stub('database._client')
_db_client.db = MagicMock()

_redis_db = _stub('database.redis_db')
_redis_db.r = MagicMock()
_redis_db.add_filter_category_item = MagicMock()

_users_db = _stub('database.users')
_notifications_db = _stub('database.notifications')
_goals_db = _stub('database.goals')

_auth_db = _stub('database.auth')
_auth_db.get_user_name = MagicMock(return_value='TestUser')

_llm_clients = _stub('utils.llm.clients')
_llm_clients.get_llm = MagicMock()

_usage_tracker = _stub('utils.llm.usage_tracker')
_usage_tracker.track_usage = MagicMock()
_usage_tracker.Features = MagicMock()

_memory_mod = _stub('utils.llms.memory')
_memory_mod.get_prompt_memories = MagicMock(return_value=('TestUser', 'some memories'))

from utils.llm import chat as mod  # noqa: E402

_EMPTY = {'people': [], 'topics': [], 'entities': [], 'dates': []}


def _make_segments():
    # Non-empty so the function reaches the prompt-building / timezone code
    # instead of short-circuiting on empty context.
    return [{'text': 'we should meet tomorrow about the budget'}]


def _noop_usage(*args, **kwargs):
    # Real no-op context manager. `track_usage` is mocked; a bare MagicMock
    # used as a context manager would have its __exit__ return a truthy
    # MagicMock and SILENTLY SUPPRESS the exception raised inside the `with`
    # block, hiding the LLM failure we rely on to reach the degrade path.
    return contextlib.nullcontext()


def test_invalid_timezone_does_not_raise_and_returns_empty_metadata():
    created_at = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Force the LLM call (which sits AFTER the tz line) to fail, so the function
    # exercises its existing degrade-to-empty path. Before the fix, the tz line
    # raises BEFORE we ever reach the LLM call.
    bad_llm = MagicMock(side_effect=RuntimeError('llm offline'))
    with patch.object(mod, 'track_usage', _noop_usage), patch.object(mod, 'get_llm', bad_llm):
        result = mod.retrieve_metadata_fields_from_transcript(
            uid='user-123',
            created_at=created_at,
            transcript_segment=_make_segments(),
            tz='Not/AZone',  # invalid IANA name -> ZoneInfo(tz) raises without the guard
        )

    assert result == _EMPTY


def test_none_timezone_does_not_raise():
    created_at = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

    bad_llm = MagicMock(side_effect=RuntimeError('llm offline'))
    with patch.object(mod, 'track_usage', _noop_usage), patch.object(mod, 'get_llm', bad_llm):
        result = mod.retrieve_metadata_fields_from_transcript(
            uid='user-123',
            created_at=created_at,
            transcript_segment=_make_segments(),
            tz=None,  # None -> ZoneInfo(None) raises TypeError without the guard
        )

    assert result == _EMPTY
