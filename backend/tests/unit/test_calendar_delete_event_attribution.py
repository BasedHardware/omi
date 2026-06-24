"""Regression test for calendar_tools.delete_calendar_event_tool deletion attribution.

When deleting several matching calendar events and one in the MIDDLE fails, the success
message must name the events that actually succeeded -- not the first `deleted_count`
events of the matching list.

Before the fix the summary iterated `matching_events[:deleted_count]`, so with a
non-contiguous failure (e.g. the 2nd of 3 deletes fails) it reported the wrong events:
it listed event #2 (which actually failed) and omitted event #3 (which succeeded).

The fix tracks the actually-deleted event objects in a `deleted_events` list and builds
the summary from those, so the reported set is exactly the set that was removed.

The module is imported with heavy deps stubbed via a meta-path finder; langchain_core is
kept real so the @tool decorator yields a StructuredTool whose `.coroutine` is the raw
async function we drive directly.
"""

import asyncio
import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

# Keep langchain_core real so @tool produces a real StructuredTool (.coroutine), and keep
# fastapi/pydantic/httpx real. Everything else heavy gets stubbed -- including the LLM-client
# subtree (utils.llm) and the langchain integration packages that are pulled in transitively
# by utils/retrieval/tools/__init__.py but are not installed / not needed here. Note: the
# stub entry 'langchain' does NOT match the separate top-level package 'langchain_core'.
_STUB = (
    'database',
    'firebase_admin',
    'google',
    'pinecone',
    'opuslib',
    'pydub',
    'redis',
    'langchain',
    'langchain_openai',
    'langchain_community',
    'langchain_anthropic',
    'langchain_pinecone',
    'tiktoken',
    'stripe',
    'openai',
    'anthropic',
    'modal',
    'ulid',
    'sentry_sdk',
    'requests',
    'typesense',
    'pusher',
    'utils.llm',
)

# utils/retrieval/tools/__init__.py eagerly imports every sibling tool module, several of
# which pull in heavy/uninstalled deps (langchain_openai, pycountry, ...). Stub those exact
# siblings so the package __init__ runs, while keeping calendar_tools (under test) and its
# direct real deps (integration_base, google_utils) genuinely imported.
_SIBLING_STUBS = frozenset(
    'utils.retrieval.tools.' + m
    for m in (
        'conversation_tools',
        'memory_tools',
        'action_item_tools',
        'omi_tools',
        'gmail_tools',
        'apple_health_tools',
        'file_tools',
        'notification_settings_tools',
        'chart_tools',
        'screen_activity_tools',
        'preference_tools',
        'web_tools',
    )
)


def _is(n):
    if n in _SIBLING_STUBS:
        return True
    return any(n == p or n.startswith(p + '.') for p in _STUB)


class _AM(types.ModuleType):
    __path__ = []

    def __getattr__(s, n):
        if n.startswith('__') and n.endswith('__'):
            raise AttributeError(n)
        m = MagicMock()
        setattr(s, n, m)
        return m


class _F(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(s, n, p=None, t=None):
        return importlib.machinery.ModuleSpec(n, s, is_package=True) if _is(n) else None

    def create_module(s, sp):
        return _AM(sp.name)

    def exec_module(s, m):
        pass


_f = _F()
_sav = {n: m for n, m in sys.modules.items() if _is(n)}
for n in list(sys.modules):
    if _is(n):
        sys.modules.pop(n, None)
sys.meta_path.insert(0, _f)
try:
    from utils.retrieval.tools import calendar_tools as mod
finally:
    sys.meta_path.remove(_f)
    for n in list(sys.modules):
        if _is(n) and n not in _sav:
            sys.modules.pop(n, None)
    sys.modules.update(_sav)


# Resolve the raw coroutine behind the @tool wrapper.
_delete_tool = getattr(mod.delete_calendar_event_tool, 'coroutine', mod.delete_calendar_event_tool)


def _run_delete_with_middle_failure():
    """Drive delete_calendar_event_tool with 3 matching events where the 2nd delete fails.

    Returns the result string produced by the tool.
    """
    events = [
        {'id': 'evt-A', 'summary': 'Alpha Standup', 'start': {'dateTime': '2024-01-20T09:00:00Z'}},
        {'id': 'evt-B', 'summary': 'Bravo Review', 'start': {'dateTime': '2024-01-20T10:00:00Z'}},
        {'id': 'evt-C', 'summary': 'Charlie Sync', 'start': {'dateTime': '2024-01-20T11:00:00Z'}},
    ]

    async def _fake_delete(access_token, event_id):
        # The middle event (evt-B) fails; the others succeed.
        if event_id == 'evt-B':
            raise RuntimeError('boom: could not delete evt-B')
        return True

    with patch.object(
        mod,
        'prepare_access',
        return_value=('uid-1', {'type': 'google_calendar'}, 'access-token', None),
    ), patch.object(mod, 'get_google_calendar_events', new=AsyncMock(return_value=events)), patch.object(
        mod, 'delete_google_calendar_event', new=AsyncMock(side_effect=_fake_delete)
    ):
        # No event_title -> every returned event is "matching"; start_date drives the search path.
        return asyncio.run(
            _delete_tool(
                event_title=None,
                start_date='2024-01-20T00:00:00+00:00',
                end_date='2024-01-21T00:00:00+00:00',
                event_id=None,
                config=MagicMock(),
            )
        )


def test_success_message_names_actually_deleted_events():
    result = _run_delete_with_middle_failure()

    # Two of three succeeded.
    assert 'Successfully deleted 2 calendar event(s)' in result, result

    # The success list must name the events that actually succeeded (A and C)...
    assert 'Alpha Standup' in result, result
    assert 'Charlie Sync' in result, result

    # ...and must NOT list the failed middle event (B) among the deleted ones.
    # On the buggy version this asserts false: matching_events[:2] reports Alpha + Bravo
    # and omits Charlie. The success-section is everything before the "Failed" section.
    deleted_section = result.split('Failed to delete')[0]
    assert 'Bravo Review' not in deleted_section, result
    assert 'Charlie Sync' in deleted_section, result


def test_failed_event_reported_in_failure_section():
    result = _run_delete_with_middle_failure()

    # The middle event should still be surfaced as a failure, not silently dropped.
    assert 'Failed to delete 1 event(s)' in result, result
    assert 'Bravo Review' in result, result
