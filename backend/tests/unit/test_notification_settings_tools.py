"""Hermetic unit tests for ``manage_daily_summary_tool``.

Covers the crash classes reported in issue #23095:

* ``hour`` arriving as a string from model tool-calling
  (``TypeError: '<=' not supported between instances of 'int' and 'str'``),
* ``action`` arriving as ``None``
  (``AttributeError: 'NoneType' object has no attribute 'lower'``),
* storage/database failures escaping the tool instead of being sanitized.

No Firestore, no credentials, no network: ``database.notifications`` and
``utils.retrieval.agentic`` are replaced with in-memory stubs before the tool
module is imported.
"""

from __future__ import annotations

import contextvars
import importlib.util
import sys
import types
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest

# tests/unit/<this file> -> backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_TOOL_PATH = _BACKEND_ROOT / 'utils' / 'retrieval' / 'tools' / 'notification_settings_tools.py'
_MODULE_NAME = '_test_notification_settings_tools'


class FakeNotificationDB:
    """Minimal in-memory stand-in for ``database.notifications``."""

    def __init__(self) -> None:
        self.enabled: bool = False
        self.hour: Optional[int] = 22
        self.enabled_calls: list[tuple[str, bool]] = []
        self.hour_calls: list[tuple[str, int]] = []
        self.raise_on: Optional[str] = None

    def _maybe_raise(self, name: str) -> None:
        if self.raise_on == name:
            raise RuntimeError(f'{name} transport timeout')

    def set_daily_summary_enabled(self, uid: str, enabled: bool) -> None:
        self._maybe_raise('set_daily_summary_enabled')
        self.enabled_calls.append((uid, enabled))
        self.enabled = enabled

    def get_daily_summary_enabled(self, uid: str) -> bool:
        self._maybe_raise('get_daily_summary_enabled')
        return self.enabled

    def set_daily_summary_hour_local(self, uid: str, hour: int) -> None:
        self._maybe_raise('set_daily_summary_hour_local')
        self.hour_calls.append((uid, hour))
        self.hour = hour

    def get_daily_summary_hour_local(self, uid: str) -> Optional[int]:
        self._maybe_raise('get_daily_summary_hour_local')
        return self.hour


@pytest.fixture()
def env(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Import the tool module against stubbed collaborators."""
    fake_db = FakeNotificationDB()

    # Stub the `database` package too: `database/__init__.py` pulls in Firestore.
    database_stub = types.ModuleType('database')
    notifications_stub = types.ModuleType('database.notifications')
    notifications_stub.set_daily_summary_enabled = fake_db.set_daily_summary_enabled  # type: ignore[attr-defined]
    notifications_stub.get_daily_summary_enabled = fake_db.get_daily_summary_enabled  # type: ignore[attr-defined]
    notifications_stub.set_daily_summary_hour_local = fake_db.set_daily_summary_hour_local  # type: ignore[attr-defined]
    notifications_stub.get_daily_summary_hour_local = fake_db.get_daily_summary_hour_local  # type: ignore[attr-defined]
    database_stub.notifications = notifications_stub  # type: ignore[attr-defined]

    agent_config_var: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar(
        'agent_config_test', default=None
    )
    agentic_stub = types.ModuleType('utils.retrieval.agentic')
    agentic_stub.agent_config_context = agent_config_var  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, 'database', database_stub)
    monkeypatch.setitem(sys.modules, 'database.notifications', notifications_stub)
    monkeypatch.setitem(sys.modules, 'utils.retrieval.agentic', agentic_stub)

    # Load the module straight from its file so `utils.retrieval.tools.__init__`
    # (which imports every other agent tool) is not dragged into the test.
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, _MODULE_NAME, module)
    spec.loader.exec_module(module)

    # The tool module must have bound *our* stubs, not the real Firestore helpers.
    assert module.notification_db is notifications_stub
    assert module.agent_config_context is agent_config_var

    mock_logger = MagicMock()
    setattr(module, 'logger', mock_logger)

    yield types.SimpleNamespace(
        module=module,
        tool=module.manage_daily_summary_tool,
        db=fake_db,
        config_var=agent_config_var,
        logger=mock_logger,
    )

    sys.modules.pop(_MODULE_NAME, None)


def _call(tool_obj: Any, **kwargs: Any) -> str:
    """Invoke the tool's underlying function regardless of langchain wrapping."""
    func = getattr(tool_obj, 'func', None) or tool_obj
    return func(**kwargs)


def _config(uid: Optional[str] = 'user-1') -> Dict[str, Any]:
    return {'configurable': {'user_id': uid}}


# --------------------------------------------------------------------------- #
# _format_hour
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ('hour', 'expected'),
    [
        (0, '12:00 AM (midnight)'),
        (8, '8:00 AM'),
        (11, '11:00 AM'),
        (12, '12:00 PM (noon)'),
        (21, '9:00 PM'),
        (22, '10:00 PM'),
        (23, '11:00 PM'),
    ],
)
def test_format_hour_ints(env: Any, hour: int, expected: str) -> None:
    assert env.module._format_hour(hour) == expected


@pytest.mark.parametrize(
    ('hour', 'expected'),
    [
        ('8', '8:00 AM'),
        ('12', '12:00 PM (noon)'),
        ('22', '10:00 PM'),
        (' 22 ', '10:00 PM'),
    ],
)
def test_format_hour_accepts_numeric_strings(env: Any, hour: str, expected: str) -> None:
    """Regression: ``elif hour < 12`` raised TypeError for str input."""
    assert env.module._format_hour(hour) == expected


@pytest.mark.parametrize('hour', [None, 'ten', '10 PM', [], {}, object()])
def test_format_hour_never_raises(env: Any, hour: Any) -> None:
    assert isinstance(env.module._format_hour(hour), str)


def test_coerce_hour_rejects_non_numeric(env: Any) -> None:
    assert env.module._coerce_hour('22') == 22
    assert env.module._coerce_hour(22) == 22
    assert env.module._coerce_hour('ten') is None
    assert env.module._coerce_hour(None) is None
    assert env.module._coerce_hour(True) is None


# --------------------------------------------------------------------------- #
# action handling
# --------------------------------------------------------------------------- #


def test_action_none_does_not_raise(env: Any) -> None:
    """Regression: ``action.lower()`` raised AttributeError on None."""
    result = _call(env.tool, action=None, config=_config())
    assert result.startswith('Unknown action')
    assert env.db.enabled_calls == []
    assert env.db.hour_calls == []


@pytest.mark.parametrize('action', [None, 42, ['enable'], {'a': 1}])
def test_non_string_action_is_rejected_without_crashing(env: Any, action: Any) -> None:
    result = _call(env.tool, action=action, config=_config())
    assert result.startswith('Unknown action')
    assert env.db.enabled_calls == []


def test_blank_action_is_rejected(env: Any) -> None:
    result = _call(env.tool, action='   ', config=_config())
    assert result.startswith('Error:')
    assert env.db.enabled_calls == []


def test_action_is_case_and_whitespace_insensitive(env: Any) -> None:
    result = _call(env.tool, action='  ENABLE  ', config=_config())
    assert result.startswith('Daily summary notifications enabled')
    assert env.db.enabled_calls == [('user-1', True)]


def test_unknown_action_message(env: Any) -> None:
    result = _call(env.tool, action='explode', config=_config())
    assert 'Unknown action: explode' in result


# --------------------------------------------------------------------------- #
# set_time
# --------------------------------------------------------------------------- #


def test_set_time_accepts_string_hour(env: Any) -> None:
    """Regression: ``0 <= hour <= 23`` raised TypeError for str input."""
    env.db.enabled = True
    result = _call(env.tool, action='set_time', hour='22', config=_config())
    assert env.db.hour_calls == [('user-1', 22)]
    assert '10:00 PM' in result
    assert env.db.enabled_calls == []


def test_set_time_string_hour_formats_before_noon(env: Any) -> None:
    env.db.enabled = True
    result = _call(env.tool, action='set_time', hour='8', config=_config())
    assert env.db.hour_calls == [('user-1', 8)]
    assert '8:00 AM' in result


def test_set_time_enables_when_currently_disabled(env: Any) -> None:
    env.db.enabled = False
    result = _call(env.tool, action='set_time', hour=21, config=_config())
    assert env.db.hour_calls == [('user-1', 21)]
    assert env.db.enabled_calls == [('user-1', True)]
    assert 'enabled' in result


@pytest.mark.parametrize('hour', ['25', '-1', 24, -3, '999'])
def test_set_time_out_of_range_string_hour_is_rejected(env: Any, hour: Any) -> None:
    result = _call(env.tool, action='set_time', hour=hour, config=_config())
    assert result.startswith('Error: Hour must be between 0 and 23')
    assert env.db.hour_calls == []


@pytest.mark.parametrize('hour', ['ten', '10 PM', 'abc', [], {}])
def test_set_time_non_numeric_hour_is_rejected(env: Any, hour: Any) -> None:
    result = _call(env.tool, action='set_time', hour=hour, config=_config())
    assert result.startswith('Error:')
    assert env.db.hour_calls == []


def test_set_time_without_hour_is_rejected(env: Any) -> None:
    result = _call(env.tool, action='set_time', config=_config())
    assert result.startswith('Error: Please specify the hour')
    assert env.db.hour_calls == []


# --------------------------------------------------------------------------- #
# enable / disable / get_settings
# --------------------------------------------------------------------------- #


def test_enable_uses_default_hour_when_unset(env: Any) -> None:
    env.db.hour = None
    result = _call(env.tool, action='enable', config=_config())
    assert env.db.enabled_calls == [('user-1', True)]
    assert '10:00 PM' in result


def test_enable_tolerates_string_hour_from_storage(env: Any) -> None:
    env.db.hour = '9'  # type: ignore[assignment]
    result = _call(env.tool, action='enable', config=_config())
    assert '9:00 AM' in result


def test_disable(env: Any) -> None:
    result = _call(env.tool, action='disable', config=_config())
    assert env.db.enabled_calls == [('user-1', False)]
    assert result == 'Daily summary notifications disabled.'


def test_get_settings_enabled(env: Any) -> None:
    env.db.enabled = True
    env.db.hour = 21
    result = _call(env.tool, action='get_settings', config=_config())
    assert 'enabled' in result
    assert '9:00 PM' in result


def test_get_settings_disabled(env: Any) -> None:
    env.db.enabled = False
    env.db.hour = 7
    result = _call(env.tool, action='get_settings', config=_config())
    assert 'currently disabled' in result
    assert '7:00 AM' in result


# --------------------------------------------------------------------------- #
# config resolution
# --------------------------------------------------------------------------- #


def test_missing_config_returns_error(env: Any) -> None:
    result = _call(env.tool, action='enable')
    assert result == 'Error: Configuration not available'
    assert env.db.enabled_calls == []


def test_falls_back_to_agent_config_context(env: Any) -> None:
    env.config_var.set(_config('ctx-user'))
    _call(env.tool, action='disable')
    assert env.db.enabled_calls == [('ctx-user', False)]


def test_uid_falls_back_to_top_level_config_key(env: Any) -> None:
    """Defensive fallback: user_id at the top level instead of under configurable."""
    result = _call(env.tool, action='disable', config={'user_id': 'top-level-user'})
    assert env.db.enabled_calls == [('top-level-user', False)]
    assert result == 'Daily summary notifications disabled.'


def test_missing_uid_returns_error(env: Any) -> None:
    result = _call(env.tool, action='enable', config={'configurable': {}})
    assert result == 'Error: User ID not found'
    assert env.db.enabled_calls == []


def test_non_dict_configurable_falls_back(env: Any) -> None:
    _call(env.tool, action='disable', config={'configurable': None, 'user_id': 'fallback-user'})
    assert env.db.enabled_calls == [('fallback-user', False)]


# --------------------------------------------------------------------------- #
# storage error boundary
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ('action', 'hour', 'failing_call'),
    [
        ('enable', None, 'set_daily_summary_enabled'),
        ('disable', None, 'set_daily_summary_enabled'),
        ('set_time', 22, 'set_daily_summary_hour_local'),
        ('get_settings', None, 'get_daily_summary_enabled'),
    ],
)
def test_storage_failures_are_sanitized(
    env: Any, action: str, hour: Optional[int], failing_call: str
) -> None:
    env.db.raise_on = failing_call
    result = _call(env.tool, action=action, hour=hour, config=_config())

    assert result == (
        'Error: Unable to access daily summary settings right now. Please try again later.'
    )
    # Raw transport detail must not leak to the model.
    assert 'transport timeout' not in result
    env.logger.error.assert_called_once()
    assert env.logger.error.call_args.kwargs.get('exc_info') is True


def test_error_boundary_keeps_logger_call_on_read_failure(env: Any) -> None:
    env.db.raise_on = 'get_daily_summary_hour_local'
    result = _call(env.tool, action='enable', config=_config())
    assert result.startswith('Error: Unable to access daily summary settings')
    env.logger.error.assert_called_once()
