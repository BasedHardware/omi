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
import inspect
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


def _run_update(update_mock, **kwargs):
    """Drive update_calendar_event_tool.coroutine with prepare_access / fetch stubbed.

    event_id is supplied so the search branch is skipped. Returns the tool's result string.
    """
    with patch.object(mod, 'prepare_access', return_value=('uid-1', {'id': 'cal'}, 'tok-abc', None)), patch.object(
        mod, 'get_google_calendar_event', side_effect=_fake_get_event
    ), patch.object(mod, 'update_google_calendar_event', update_mock):
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


def test_source_threads_new_times_into_update_calls():
    """Source-assert: both update_google_calendar_event calls receive the parsed new times."""
    src = inspect.getsource(_update_tool)
    assert src.count('start_time=new_start_dt') >= 2, "new_start_dt not threaded into both update calls"
    assert src.count('end_time=new_end_dt') >= 2, "new_end_dt not threaded into both update calls"
