"""Regression test for calendar_tools.update_calendar_event_tool reschedule support.

The tool's docstring advertises that it can change an event's start/end time, and
update_google_calendar_event() fully supports start_time / end_time parameters. But the
tool never passed them through to either update_google_calendar_event call (the primary
call nor the post-token-refresh retry), so a reschedule request silently did nothing -
the event time was never updated.

The fix adds dedicated new_start_time / new_end_time parameters, validates them with the
same ISO + timezone check used by create_calendar_event_tool (parse_iso_with_tz), and
threads them into update_google_calendar_event as start_time=new_start_dt /
end_time=new_end_dt.

This test loads calendar_tools.py directly (heavy sibling tool modules and database deps
stubbed) and drives the tool coroutine. It is red before the fix (update_google_calendar_event
is called with start_time=None / end_time=None) and green after (it receives the parsed
tz-aware datetimes).
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

# Heavy leaf deps to stub out. We deliberately keep utils.retrieval.tools.integration_base
# (parse_iso_with_tz) and the google_utils / http_client / log_sanitizer chain REAL so the
# ISO + timezone validation under test runs for real.
_STUB = (
    'database',
    'firebase_admin',
    'google',
    'pinecone',
    'redis',
    'typesense',
    'cachetools',
)


def _is(name):
    return any(name == p or name.startswith(p + '.') for p in _STUB)


class _AutoMockModule(types.ModuleType):
    __path__ = []

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


class _StubFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        if _is(name):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMockModule(spec.name)

    def exec_module(self, module):
        pass


def _load_calendar_tools():
    finder = _StubFinder()
    saved = {n: m for n, m in sys.modules.items() if _is(n)}
    for n in list(sys.modules):
        if _is(n):
            sys.modules.pop(n, None)
    sys.meta_path.insert(0, finder)
    tools_pkg = 'utils.retrieval.tools'
    saved_pkg = sys.modules.get(tools_pkg)
    saved_mod = sys.modules.get('utils.retrieval.tools.calendar_tools')
    try:
        # Import the light parent packages, then load calendar_tools.py by file so the
        # heavy utils/retrieval/tools/__init__.py (which eagerly imports every tool module)
        # never runs.
        import utils  # noqa: F401
        import utils.retrieval  # noqa: F401

        # Resolve the tools dir from this test file's location (backend/tests/unit/<this>)
        # rather than utils.retrieval.__file__, which can be None for a namespace package.
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        pkg_path = os.path.join(backend_dir, 'utils', 'retrieval', 'tools')
        pkg = types.ModuleType(tools_pkg)
        pkg.__path__ = [pkg_path]
        pkg.__package__ = tools_pkg
        sys.modules[tools_pkg] = pkg

        spec = importlib.util.spec_from_file_location(
            'utils.retrieval.tools.calendar_tools',
            os.path.join(pkg_path, 'calendar_tools.py'),
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules['utils.retrieval.tools.calendar_tools'] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.meta_path.remove(finder)
        for n in list(sys.modules):
            if _is(n) and n not in saved:
                sys.modules.pop(n, None)
        sys.modules.update(saved)
        if saved_pkg is not None:
            sys.modules[tools_pkg] = saved_pkg
        else:
            sys.modules.pop(tools_pkg, None)
        if saved_mod is not None:
            sys.modules['utils.retrieval.tools.calendar_tools'] = saved_mod
        else:
            sys.modules.pop('utils.retrieval.tools.calendar_tools', None)


mod = _load_calendar_tools()

# The tool is wrapped by langchain's @tool decorator; the original coroutine is on .coroutine.
_update_tool = mod.update_calendar_event_tool.coroutine


async def _fake_get_event(_token, event_id):
    return {'id': event_id, 'summary': 'Standup', 'attendees': []}


def _make_get_event(event):
    async def _fetch(_token, event_id):
        return dict(event, id=event_id)

    return _fetch


def _run_update(update_mock, fetch=None, refresh_token=None, **kwargs):
    """Drive update_calendar_event_tool.coroutine with prepare_access / fetch stubbed.

    event_id is supplied so the search branch is skipped. ``fetch`` overrides the
    get_google_calendar_event stub (e.g. to supply existing start/end), and
    ``refresh_token`` patches refresh_google_token for the auth-retry path. Returns the
    tool's result string.
    """
    fetch = fetch or _fake_get_event
    refresh_mock = AsyncMock(return_value=refresh_token)
    with patch.object(mod, 'prepare_access', return_value=('uid-1', {'id': 'cal'}, 'tok-abc', None)), patch.object(
        mod, 'get_google_calendar_event', side_effect=fetch
    ), patch.object(mod, 'update_google_calendar_event', update_mock), patch.object(
        mod, 'refresh_google_token', refresh_mock
    ):
        return asyncio.run(_update_tool(event_id='evt-1', config={'configurable': {}}, **kwargs))


def test_new_times_are_passed_to_update_google_calendar_event():
    """A reschedule request must thread start_time/end_time into update_google_calendar_event.

    Red before the fix: the call receives start_time=None / end_time=None (reschedule no-ops).
    """
    update_mock = AsyncMock(return_value={'id': 'evt-1', 'summary': 'Standup', 'htmlLink': 'http://x'})
    result = _run_update(
        update_mock,
        new_start_time='2024-01-20T14:00:00-08:00',
        new_end_time='2024-01-20T15:00:00-08:00',
    )

    assert isinstance(result, str)
    assert update_mock.called
    kwargs = update_mock.call_args.kwargs
    assert kwargs.get('start_time') is not None, "start_time was not passed to update_google_calendar_event"
    assert kwargs.get('end_time') is not None, "end_time was not passed to update_google_calendar_event"
    # Parsed values must be tz-aware and reflect the requested times.
    assert kwargs['start_time'].tzinfo is not None
    assert kwargs['end_time'].tzinfo is not None
    assert kwargs['start_time'].hour == 14
    assert kwargs['end_time'].hour == 15


def test_only_new_start_time_passes_start_not_end():
    """Supplying only new_start_time threads start_time through; end_time stays None."""
    update_mock = AsyncMock(return_value={'id': 'evt-1', 'summary': 'Standup'})
    _run_update(update_mock, new_start_time='2024-01-20T09:30:00+00:00')

    kwargs = update_mock.call_args.kwargs
    assert kwargs.get('start_time') is not None
    assert kwargs.get('end_time') is None


def test_new_time_without_timezone_is_rejected():
    """A naive (no offset) new_start_time returns an error and never calls update."""
    update_mock = AsyncMock(return_value={})
    result = _run_update(update_mock, new_start_time='2024-01-20T14:00:00')

    assert result.startswith('Error')
    assert not update_mock.called, "update_google_calendar_event must not run on invalid time input"


def test_retry_after_token_refresh_returns_reschedule_details():
    """The auth-refresh retry path must keep the reschedule confirmation in its output.

    The first update raises a 401 GoogleAPIError; after refresh_google_token yields a new
    token, the retry succeeds. The returned string must still surface the new Start/End
    (red before the fix: the retry path only echoed attendees and dropped the times).
    """
    update_mock = AsyncMock(
        side_effect=[
            mod.GoogleAPIError(401, 'invalid_credentials'),
            {'id': 'evt-1', 'summary': 'Standup', 'htmlLink': 'http://x'},
        ]
    )
    result = _run_update(
        update_mock,
        refresh_token='tok-refreshed',
        new_start_time='2024-01-20T14:00:00-08:00',
        new_end_time='2024-01-20T15:00:00-08:00',
    )

    # Both calls happened (original + retry) and the retry used the refreshed token.
    assert update_mock.call_count == 2
    assert update_mock.call_args.kwargs.get('access_token') == 'tok-refreshed'
    # The confirmation payload still reports the rescheduled times.
    assert 'Successfully updated' in result
    assert 'Start:' in result, "retry-path response dropped the new start time"
    assert 'End:' in result, "retry-path response dropped the new end time"


def test_partial_reschedule_inverting_existing_end_is_rejected():
    """Moving only the start past the existing end must be rejected, not silently sent.

    Existing event runs 14:00-15:00. A start-only update to 16:00 would invert the event;
    the tool must return an error and never call update_google_calendar_event.
    """
    existing = {
        'summary': 'Standup',
        'attendees': [],
        'start': {'dateTime': '2024-01-20T14:00:00Z'},
        'end': {'dateTime': '2024-01-20T15:00:00Z'},
    }
    update_mock = AsyncMock(return_value={})
    result = _run_update(
        update_mock,
        fetch=_make_get_event(existing),
        new_start_time='2024-01-20T16:00:00+00:00',
    )

    assert result.startswith('Error')
    assert not update_mock.called, "an inverted partial reschedule must not be sent to Google Calendar"


def test_partial_reschedule_within_existing_bounds_is_sent():
    """A start-only update that stays before the existing end is threaded through normally."""
    existing = {
        'summary': 'Standup',
        'attendees': [],
        'start': {'dateTime': '2024-01-20T14:00:00Z'},
        'end': {'dateTime': '2024-01-20T15:00:00Z'},
    }
    update_mock = AsyncMock(return_value={'id': 'evt-1', 'summary': 'Standup'})
    _run_update(
        update_mock,
        fetch=_make_get_event(existing),
        new_start_time='2024-01-20T14:30:00+00:00',
    )

    kwargs = update_mock.call_args.kwargs
    assert kwargs.get('start_time') is not None
    assert kwargs.get('end_time') is None
