from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import sys

TESTS_DIR = Path(__file__).resolve().parents[1]
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
import conftest as backend_conftest


class _Reporter:
    def __init__(self):
        self.messages: list[str] = []

    def section(self, message):
        self.messages.append(message)

    def line(self, message):
        self.messages.append(message)


class _PluginManager:
    def __init__(self, reporter):
        self._reporter = reporter

    def get_plugin(self, name):
        return self._reporter if name == 'terminalreporter' else None


class _Config:
    def __init__(self, reporter):
        self.pluginmanager = _PluginManager(reporter)


class _Session:
    def __init__(self, reporter):
        self.config = _Config(reporter)
        self.exitstatus = 0


def test_fast_unit_duration_guard_warns_without_failing_below_fail_threshold(monkeypatch):
    reporter = _Reporter()
    session = _Session(reporter)

    monkeypatch.setenv('BACKEND_FAST_UNIT_WARN_SECONDS', '0.1')
    monkeypatch.setenv('BACKEND_FAST_UNIT_FAIL_SECONDS', '0.25')
    monkeypatch.setattr(backend_conftest, '_collected_unit_files', {'tests/unit/test_example.py'})
    monkeypatch.setattr(
        backend_conftest,
        '_test_item_cpu',
        defaultdict(float, {'tests/unit/test_example.py::test_near_target': 0.14}),
    )
    monkeypatch.setattr(backend_conftest, '_read_duration_allowlist', lambda: set())

    backend_conftest._enforce_fast_unit_duration_guard(session)

    assert session.exitstatus == 0
    assert any('warnings' in message for message in reporter.messages)
    assert not any('failures' in message for message in reporter.messages)


def test_fast_unit_duration_guard_fails_above_fail_threshold(monkeypatch):
    reporter = _Reporter()
    session = _Session(reporter)

    monkeypatch.setenv('BACKEND_FAST_UNIT_WARN_SECONDS', '0.1')
    monkeypatch.setenv('BACKEND_FAST_UNIT_FAIL_SECONDS', '0.12')
    monkeypatch.setattr(backend_conftest, '_collected_unit_files', {'tests/unit/test_example.py'})
    monkeypatch.setattr(
        backend_conftest,
        '_test_item_cpu',
        defaultdict(float, {'tests/unit/test_example.py::test_slow': 0.14}),
    )
    monkeypatch.setattr(backend_conftest, '_read_duration_allowlist', lambda: set())

    backend_conftest._enforce_fast_unit_duration_guard(session)

    assert session.exitstatus == 1
    assert any('failures' in message for message in reporter.messages)


def test_fast_unit_duration_guard_rejects_fail_threshold_below_warn_threshold(monkeypatch):
    reporter = _Reporter()
    session = _Session(reporter)

    monkeypatch.setenv('BACKEND_FAST_UNIT_WARN_SECONDS', '0.2')
    monkeypatch.setenv('BACKEND_FAST_UNIT_FAIL_SECONDS', '0.1')
    monkeypatch.setattr(backend_conftest, '_collected_unit_files', {'tests/unit/test_example.py'})
    monkeypatch.setattr(
        backend_conftest,
        '_test_item_cpu',
        defaultdict(float, {'tests/unit/test_example.py::test_fast': 0.01}),
    )

    backend_conftest._enforce_fast_unit_duration_guard(session)

    assert session.exitstatus == 1
    assert any('configuration error' in message for message in reporter.messages)
